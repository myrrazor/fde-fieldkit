from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
import sqlite3
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from fieldkit_netwatch.agents import (
    AgentKind,
    PreparedAgent,
    capability_report,
    discover_agents,
)
from fieldkit_netwatch.attach import record_snapshot
from fieldkit_netwatch.destinations import parse_destination
from fieldkit_netwatch.models import Action, EventDecision, Mode, report_to_dict, session_to_dict
from fieldkit_netwatch.policy import Policy, make_rule
from fieldkit_netwatch.proxy import ProxyAddresses
from fieldkit_netwatch.store import Store, default_db_path
from fieldkit_netwatch.supervisor import run_supervised

app = typer.Typer(
    name="netwatch",
    no_args_is_help=True,
    help="Observe and control network access from AI coding agents.",
)
policy_app = typer.Typer(name="policy", no_args_is_help=True, help="Build and test egress policy files.")
app.add_typer(policy_app, name="policy")
console = Console()


@app.command("doctor")
def doctor_command(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Check capture backends and Codex/Claude integrations without opening a socket."""

    payload = capability_report()
    if json_output:
        typer.echo(json.dumps(payload, indent=2))
        return
    table = Table(title="Netwatch coverage on this machine")
    table.add_column("capability")
    table.add_column("status")
    table.add_column("meaning")
    capture = payload["capture"]
    assert isinstance(capture, dict)
    rows = (
        ("HTTP proxy", capture["http_proxy"], "HTTP requests and HTTPS CONNECT destinations"),
        ("SOCKS5 TCP", capture["socks5_tcp"], "TCP destinations from SOCKS-aware clients"),
        ("attach snapshots", capture["attach_snapshot"], "established sockets; observation only"),
        ("TLS decryption", capture["tls_decryption"], "disabled; bodies and HTTPS paths stay private"),
        ("UDP / QUIC", capture["udp_quic"], "not captured"),
        ("whole-machine block", capture["whole_machine_enforcement"], "needs a signed OS extension"),
    )
    for name, available, meaning in rows:
        table.add_row(name, "available" if available else "not available", meaning)
    console.print(table)
    agents = payload["agents"]
    assert isinstance(agents, dict)
    console.print(
        f"Codex network proxy: {_yes_no(bool(agents['codex']['network_proxy']))} · "
        f"Claude strict proxy: {_yes_no(bool(agents['claude']['strict_sandbox_proxy']))}"
    )
    console.print(f"[dim]{payload['coverage_note']}[/dim]")


@app.command("agents")
def agents_command(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output."),
) -> None:
    """Find running Codex and Claude processes."""

    try:
        processes = discover_agents()
    except RuntimeError as exc:
        _fail(exc)
    rows = [
        {
            "pid": process.pid,
            "ppid": process.ppid,
            "agent": process.agent.value,
            "executable": process.executable,
            "command": process.command,
        }
        for process in processes
    ]
    if json_output:
        typer.echo(json.dumps({"agents": rows}, indent=2))
        return
    table = Table(title="Running AI coding agents")
    table.add_column("pid", justify="right")
    table.add_column("agent")
    table.add_column("executable")
    for row in rows:
        table.add_row(str(row["pid"]), str(row["agent"]), str(row["executable"]))
    console.print(table)
    if not rows:
        console.print("[dim]no running Codex or Claude process found[/dim]")


@app.command(
    "run",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def run_command(
    ctx: typer.Context,
    command: list[str] = typer.Argument(None, help="Command after --, e.g. -- codex"),
    mode: Mode = typer.Option(Mode.AUDIT, "--mode", help="Audit or enforce policy."),
    policy: Path | None = typer.Option(None, "--policy", dir_okay=False, help="Policy JSON."),
    db: Path | None = typer.Option(None, "--db", dir_okay=False, help="Evidence database."),
    agent: AgentKind = typer.Option(AgentKind.AUTO, "--agent", help="Agent integration."),
) -> None:
    """Run a command through the local capture and policy proxies."""

    argv = [*(command or []), *ctx.args]
    if argv[:1] == ["--"]:
        argv = argv[1:]
    if not argv:
        _fail(ValueError("missing command; use: fieldkit netwatch run -- <command>"), code=2)
    db_path = db or default_db_path()
    try:
        selected_policy = _policy_for_run(mode, policy)

        def on_ready(
            session_id: str,
            addresses: ProxyAddresses,
            prepared: PreparedAgent,
        ) -> None:
            console.print(f"[bold]netwatch session[/bold] {session_id}")
            console.print(
                f"HTTP {addresses.http_url} · SOCKS {addresses.socks_url} · "
                f"{mode.value} · {prepared.agent.value}"
            )
            for warning in prepared.warnings:
                console.print(f"[yellow]coverage:[/yellow] {warning}")

        result = asyncio.run(
            run_supervised(
                argv,
                mode=mode,
                policy=selected_policy,
                policy_path=policy,
                db_path=db_path,
                agent=agent,
                on_ready=on_ready,
            )
        )
    except (OSError, ValueError, sqlite3.Error) as exc:
        _fail(exc)
    _print_report(result.report)
    if result.exit_code:
        raise typer.Exit(result.exit_code)


@app.command("attach")
def attach_command(
    pid: int = typer.Argument(..., help="Root process id."),
    follow: bool = typer.Option(False, "--follow", help="Keep sampling until interrupted."),
    interval: float = typer.Option(1.0, "--interval", min=0.1, help="Seconds between snapshots."),
    db: Path | None = typer.Option(None, "--db", dir_okay=False, help="Evidence database."),
) -> None:
    """Sample established sockets for a process tree; attachment cannot block."""

    if pid <= 0:
        _fail(ValueError("pid must be positive"), code=2)
    store = Store(db or default_db_path())
    session = store.create_session(
        mode=Mode.AUDIT,
        agent="attached-process",
        command=["attach", str(pid)],
        root_pid=pid,
        status="running",
        coverage=("lsof established TCP snapshots", "observation only; no request counts or blocking"),
        note="attach samples sockets and cannot enforce policy",
    )
    console.print(
        f"[bold]netwatch session[/bold] {session.id} · attach is observation-only"
    )
    try:
        while True:
            added = record_snapshot(store, session.id, pid)
            if not follow:
                break
            console.print(f"[dim]{added} new socket(s)[/dim]")
            time.sleep(interval)
    except KeyboardInterrupt:
        store.finish_session(session.id, status="interrupted")
    except (OSError, RuntimeError, ValueError, sqlite3.Error) as exc:
        store.finish_session(session.id, status="failed", note=f"attach failed ({type(exc).__name__})")
        _fail(exc)
    else:
        store.finish_session(session.id, status="complete")
    _print_report(store.report(session.id))


@app.command("sessions")
def sessions_command(
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output."),
    db: Path | None = typer.Option(None, "--db", dir_okay=False, help="Evidence database."),
) -> None:
    """List saved Netwatch sessions."""

    try:
        rows = Store(db or default_db_path()).list_sessions()
    except (OSError, sqlite3.Error) as exc:
        _fail(exc)
    if json_output:
        typer.echo(json.dumps({"sessions": [session_to_dict(row) for row in rows]}, indent=2))
        return
    table = Table(title="Netwatch sessions")
    table.add_column("session")
    table.add_column("started")
    table.add_column("agent")
    table.add_column("mode")
    table.add_column("status")
    table.add_column("pid", justify="right")
    for row in rows:
        table.add_row(row.id, row.started_at, row.agent, row.mode.value, row.status, str(row.root_pid or ""))
    console.print(table)
    if not rows:
        console.print("[dim]no sessions yet; run: fieldkit netwatch run -- codex[/dim]")


@app.command("report")
def report_command(
    session_id: str = typer.Argument(..., help="Session id."),
    json_output: bool = typer.Option(False, "--json", help="Machine-readable output."),
    db: Path | None = typer.Option(None, "--db", dir_okay=False, help="Evidence database."),
) -> None:
    """Show grouped destinations and event counts for one session."""

    try:
        report = Store(db or default_db_path()).report(session_id)
    except KeyError:
        _fail(ValueError(f"no netwatch session {session_id!r}"), code=2)
    except (OSError, sqlite3.Error) as exc:
        _fail(exc)
    if json_output:
        typer.echo(json.dumps(report_to_dict(report), indent=2))
        return
    _print_report(report)


@policy_app.command("init")
def policy_init_command(
    path: Path = typer.Argument(..., dir_okay=False, help="Policy JSON path."),
    force: bool = typer.Option(False, "--force", help="Replace an existing file."),
) -> None:
    """Write a deny-by-default policy that only allows loopback development."""

    if path.exists() and not force:
        _fail(ValueError(f"{path} already exists; pass --force to replace it"), code=2)
    try:
        Policy.starter().write(path)
    except (OSError, ValueError) as exc:
        _fail(exc)
    typer.echo(f"wrote {path}")


@policy_app.command("add")
def policy_add_command(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, help="Policy JSON path."),
    action: Action = typer.Option(..., "--action", help="Allow or deny."),
    rule_id: str | None = typer.Option(None, "--id", help="Stable rule id."),
    host: list[str] | None = typer.Option(None, "--host", help="Exact or wildcard host. Repeatable."),
    ip: list[str] | None = typer.Option(None, "--ip", help="IP or CIDR. Repeatable."),
    port: list[int] | None = typer.Option(None, "--port", help="Port. Repeatable."),
    protocol: list[str] | None = typer.Option(
        None, "--protocol", help="http, https, or tcp. Repeatable."
    ),
    allow_private: bool = typer.Option(
        False,
        "--allow-private",
        help="Allow matched private/loopback destinations.",
    ),
    note: str | None = typer.Option(None, "--note", help="Rule explanation."),
) -> None:
    """Append a validated allow or deny rule to a policy."""

    try:
        existing = Policy.load(path)
        selected_id = rule_id or f"{action.value}-{len(existing.rules) + 1}"
        rule = make_rule(
            selected_id,
            action,
            hosts=tuple(host or ()),
            ips=tuple(ip or ()),
            ports=tuple(port or ()),
            protocols=tuple(protocol or ()),
            allow_private=allow_private,
            note=note,
        )
        existing.with_rule(rule).write(path)
    except (OSError, ValueError) as exc:
        _fail(exc)
    typer.echo(f"added {selected_id} to {path}")


@policy_app.command("check")
def policy_check_command(
    path: Path = typer.Argument(..., exists=True, dir_okay=False, help="Policy JSON path."),
    destination: str = typer.Argument(..., help="URL or host[:port]."),
    protocol: str = typer.Option("https", "--protocol", help="Used when destination is not a URL."),
    mode: Mode = typer.Option(Mode.ENFORCE, "--mode", help="Show enforce or audit outcome."),
) -> None:
    """Explain a policy decision before running an agent."""

    try:
        policy = Policy.load(path)
        target = parse_destination(destination, protocol)
        addresses = _resolve_ips(target.host, target.port)
        decisions = [
            (address, policy.evaluate(target.host, address, target.port, target.protocol, mode))
            for address in addresses or [None]
        ]
        selected = next(
            (item for item in decisions if item[1].action is Action.DENY),
            decisions[0],
        )
    except (OSError, ValueError) as exc:
        _fail(exc, code=2)
    address, decision = selected
    typer.echo(
        f"{decision.outcome.value}: {target.host}:{target.port} ({address or 'unresolved'}) · "
        f"{decision.reason}"
    )
    if decision.outcome is EventDecision.BLOCKED:
        raise typer.Exit(3)


def _policy_for_run(mode: Mode, path: Path | None) -> Policy:
    if path is not None:
        return Policy.load(path)
    if mode is Mode.ENFORCE:
        raise ValueError("enforce mode needs --policy; start with: fieldkit netwatch policy init policy.json")
    return Policy.audit_all()


def _resolve_ips(host: str, port: int) -> list[str]:
    try:
        rows = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except OSError:
        return []
    addresses: list[str] = []
    for row in rows:
        address = str(ipaddress.ip_address(row[4][0]))
        if address not in addresses:
            addresses.append(address)
    return addresses


def _print_report(report: object) -> None:
    if not hasattr(report, "destinations"):
        return
    data = report_to_dict(report)  # type: ignore[arg-type]
    session = data["session"]
    totals = data["totals"]
    console.print(
        f"\n[bold]session {session['id']}[/bold] · {session['status']} · "
        f"{session['mode']} · {totals['events']} network event(s) · "
        f"{totals['tool_events']} tool event(s)"
    )
    table = Table(title="Destinations")
    table.add_column("service")
    table.add_column("destination")
    table.add_column("scope")
    table.add_column("protocol")
    table.add_column("events", justify="right")
    table.add_column("allowed", justify="right")
    table.add_column("blocked", justify="right")
    table.add_column("would block", justify="right")
    table.add_column("bytes", justify="right")
    for row in data["destinations"]:
        table.add_row(
            str(row["service"]),
            f"{row['host']}:{row['port']}",
            str(row["scope"]),
            str(row["protocol"]),
            str(row["events"]),
            str(row["allowed"]),
            str(row["blocked"]),
            str(row["would_block"]),
            _bytes(int(row["bytes_sent"]) + int(row["bytes_received"])),
        )
    console.print(table)
    console.print(
        "[dim]HTTPS paths and bodies remain encrypted. Attach rows are socket snapshots, not request counts.[/dim]"
    )


def _bytes(value: int) -> str:
    if value < 1024:
        return f"{value} B"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} KiB"
    return f"{value / 1024 / 1024:.1f} MiB"


def _yes_no(value: bool) -> str:
    return "available" if value else "not available"


def _fail(exc: Exception, *, code: int = 1) -> None:
    typer.secho(f"error: {exc}", fg="red", err=True)
    raise typer.Exit(code) from exc
