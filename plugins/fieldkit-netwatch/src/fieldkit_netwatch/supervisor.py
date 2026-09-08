from __future__ import annotations

import asyncio
import os
import signal
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from fieldkit_netwatch.agents import AgentKind, PreparedAgent, detect_agent, prepare_agent
from fieldkit_netwatch.models import Mode, SessionReport
from fieldkit_netwatch.policy import Policy
from fieldkit_netwatch.proxy import ProxyAddresses, ProxyServer
from fieldkit_netwatch.store import Store


@dataclass(frozen=True)
class RunResult:
    """Final process status and persisted evidence report."""

    exit_code: int
    report: SessionReport


ReadyCallback = Callable[[str, ProxyAddresses, PreparedAgent], None]


async def run_supervised(
    command: list[str],
    *,
    mode: Mode,
    policy: Policy,
    policy_path: Path | None,
    db_path: Path,
    agent: AgentKind = AgentKind.AUTO,
    on_ready: ReadyCallback | None = None,
) -> RunResult:
    """Run a command through Netwatch and return its persisted report."""

    if not command:
        raise ValueError("missing command after --")
    selected_agent = detect_agent(command) if agent is AgentKind.AUTO else agent
    store = Store(db_path)
    session = store.create_session(
        mode=mode,
        agent=selected_agent.value,
        command=command,
        coverage=("starting local proxy",),
        policy_path=policy_path,
    )
    proxy = ProxyServer(store=store, session_id=session.id, policy=policy, mode=mode)
    process: asyncio.subprocess.Process | None = None
    try:
        addresses = await proxy.start()
        with tempfile.TemporaryDirectory(prefix="fieldkit-netwatch-") as raw_temp:
            prepared = await asyncio.to_thread(
                prepare_agent,
                command,
                requested=agent,
                addresses=addresses,
                session_id=session.id,
                db_path=db_path,
                temp_dir=Path(raw_temp),
            )
            try:
                process = await asyncio.create_subprocess_exec(
                    *prepared.argv,
                    env=prepared.env,
                    start_new_session=True,
                )
            except FileNotFoundError as exc:
                raise ValueError(f"command not found: {command[0]}") from exc
            note = "; ".join(prepared.warnings) or None
            store.mark_running(
                session.id,
                root_pid=process.pid,
                coverage=prepared.coverage,
                http_proxy=addresses.http_url,
                socks_proxy=addresses.socks_url,
                note=note,
            )
            if on_ready:
                on_ready(session.id, addresses, prepared)
            exit_code = await process.wait()
            store.finish_session(
                session.id,
                status="complete" if exit_code == 0 else "failed",
                exit_code=exit_code,
            )
    except asyncio.CancelledError:
        if process:
            await _terminate_process(process)
        store.finish_session(session.id, status="interrupted", exit_code=process.returncode if process else None)
        raise
    except Exception as exc:
        if process:
            await _terminate_process(process)
        store.finish_session(
            session.id,
            status="failed",
            exit_code=process.returncode if process else None,
            note=f"supervisor failed ({type(exc).__name__})",
        )
        raise
    finally:
        await proxy.close()
    return RunResult(exit_code=exit_code, report=store.report(session.id))


def _kill_process_group(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except ProcessLookupError:
        pass


async def _terminate_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    _kill_process_group(process)
    await process.wait()
