from __future__ import annotations

import asyncio
import csv
import ipaddress
import logging
import os
import socket
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

from fieldkit_netwatch.agents import AgentKind
from fieldkit_netwatch.attach import record_snapshot
from fieldkit_netwatch.destinations import ip_scope, parse_destination
from fieldkit_netwatch.models import Action, Mode, Session, SessionReport
from fieldkit_netwatch.policy import Policy
from fieldkit_netwatch.store import Store, default_db_path
from fieldkit_netwatch.supervisor import run_supervised

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PolicyState:
    """The dashboard-managed policy and its local storage state."""

    path: Path
    saved: bool
    policy: Policy

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe policy state."""

        return {
            "path": str(self.path),
            "saved": self.saved,
            "policy": self.policy.as_dict(),
        }


def default_policy_path(db_path: Path | None = None) -> Path:
    """Return the server-managed policy path; browser requests never choose it."""

    configured = os.environ.get("FIELDKIT_NETWATCH_POLICY")
    if configured:
        return Path(configured).expanduser()
    database = db_path or default_db_path()
    return database.with_name("netwatch-policy.json")


def load_policy_state(db_path: Path | None = None) -> PolicyState:
    """Load the managed policy or return the unsaved starter policy."""

    path = default_policy_path(db_path)
    if path.exists():
        return PolicyState(path, True, Policy.load(path))
    return PolicyState(path, False, Policy.starter())


def save_policy_document(payload: object, db_path: Path | None = None) -> PolicyState:
    """Validate and persist the dashboard-managed policy."""

    policy = Policy.from_dict(payload)
    path = default_policy_path(db_path)
    policy.write(path)
    return PolicyState(path, True, policy)


async def check_policy_destination(
    destination: str,
    *,
    protocol: str,
    mode: Mode,
    db_path: Path | None = None,
) -> dict[str, object]:
    """Resolve and explain the managed policy decision for one destination."""

    state = load_policy_state(db_path)
    target = parse_destination(destination, protocol)
    addresses = await asyncio.to_thread(_resolve_ips, target.host, target.port)
    rows = []
    for address in addresses or [None]:
        decision = state.policy.evaluate(
            target.host,
            address,
            target.port,
            target.protocol,
            mode,
        )
        rows.append(
            {
                "ip": address,
                "scope": ip_scope(address or target.host),
                "action": decision.action.value,
                "outcome": decision.outcome.value,
                "rule_id": decision.rule_id,
                "reason": decision.reason,
            }
        )
    selected = next((row for row in rows if row["action"] == Action.DENY.value), rows[0])
    return {
        "destination": {
            "host": target.host,
            "port": target.port,
            "protocol": target.protocol,
        },
        "selected": selected,
        "addresses": rows,
        "policy": {"path": str(state.path), "saved": state.saved},
    }


def report_as_csv(report: SessionReport) -> str:
    """Serialize stored network and tool evidence as one labelled CSV ledger."""

    fields = [
        "record_type",
        "occurred_at",
        "source",
        "service",
        "host",
        "port",
        "protocol",
        "method",
        "path",
        "scope",
        "decision",
        "rule_id",
        "bytes_sent",
        "bytes_received",
        "process_pid",
        "process_name",
        "tool",
        "target",
        "correlation_id",
        "detail",
    ]
    stream = StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=fields)
    writer.writeheader()
    for event in report.events:
        writer.writerow(
            _safe_csv_row({
                "record_type": "network_event",
                "occurred_at": event.started_at,
                "source": event.source,
                "service": event.service,
                "host": event.host,
                "port": event.port,
                "protocol": event.protocol,
                "method": event.method,
                "path": event.path,
                "scope": event.scope,
                "decision": event.decision.value,
                "rule_id": event.rule_id,
                "bytes_sent": event.bytes_sent,
                "bytes_received": event.bytes_received,
                "process_pid": event.process_pid,
                "process_name": event.process_name,
                "detail": event.detail,
            })
        )
    for event in report.tool_events:
        writer.writerow(
            _safe_csv_row({
                "record_type": "tool_event",
                "occurred_at": event.occurred_at,
                "source": "agent-hook",
                "tool": event.tool,
                "target": event.target,
                "correlation_id": event.correlation_id,
                "detail": event.event,
            })
        )
    return stream.getvalue()


class ControlPlane:
    """Own background runs and attachments started by one local web server."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._tasks: dict[str, asyncio.Task[None]] = {}

    async def start_run(
        self,
        command: list[str],
        *,
        mode: Mode,
        agent: AgentKind,
        use_policy: bool,
    ) -> Session:
        """Start a supervised argv command and return after its proxies are ready."""

        _validate_command(command)
        state = load_policy_state(self.db_path) if mode is Mode.ENFORCE or use_policy else None
        if mode is Mode.ENFORCE and (state is None or not state.saved):
            raise ValueError("save a policy before starting enforce mode")
        use_saved_policy = bool(state and state.saved and (use_policy or mode is Mode.ENFORCE))
        policy = state.policy if state and use_saved_policy else Policy.audit_all()
        policy_path = state.path if state and use_saved_policy else None
        ready: asyncio.Future[str] = asyncio.get_running_loop().create_future()

        def on_ready(session_id: str, _addresses: object, _prepared: object) -> None:
            if not ready.done():
                ready.set_result(session_id)

        async def worker() -> None:
            try:
                await run_supervised(
                    command,
                    mode=mode,
                    policy=policy,
                    policy_path=policy_path,
                    db_path=self.db_path,
                    agent=agent,
                    on_ready=on_ready,
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if not ready.done():
                    ready.set_exception(exc)

        task = asyncio.create_task(worker(), name="netwatch-supervised-run")
        try:
            session_id = await ready
        except BaseException:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            raise
        self._own(session_id, task)
        session = Store(self.db_path).get_session(session_id)
        if session is None:
            raise RuntimeError("supervised session disappeared after launch")
        return session

    async def start_attach(self, pid: int, *, follow: bool, interval: float) -> Session:
        """Start one socket snapshot or an owned follow loop for a process tree."""

        if pid <= 0:
            raise ValueError("pid must be positive")
        if interval < 0.1:
            raise ValueError("attach interval must be at least 0.1 seconds")
        store = Store(self.db_path)
        session = store.create_session(
            mode=Mode.AUDIT,
            agent="attached-process",
            command=["attach", str(pid)],
            root_pid=pid,
            status="running",
            coverage=("lsof established TCP snapshots", "observation only; no request counts or blocking"),
            note="attach samples sockets and cannot enforce policy",
        )
        work = (
            self._follow_attach(store, session.id, pid, interval)
            if follow
            else self._snapshot_once(store, session.id, pid)
        )
        task = asyncio.create_task(work, name="netwatch-attach-follow" if follow else "netwatch-attach-once")
        self._own(session.id, task)
        return session

    async def stop(self, session_id: str) -> Session:
        """Stop an operation owned by this server process."""

        task = self._tasks.get(session_id)
        if task is None:
            raise KeyError(session_id)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        store = Store(self.db_path)
        session = store.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        if session.status in {"starting", "running"}:
            store.finish_session(session_id, status="interrupted")
            session = _session_or_raise(store, session_id)
        return session

    def active_session_ids(self) -> tuple[str, ...]:
        """Return sessions this server can safely stop."""

        return tuple(sorted(self._tasks))

    async def shutdown(self) -> None:
        """Stop every operation owned by this server."""

        session_ids = tuple(self._tasks)
        results = await asyncio.gather(
            *(self.stop(session_id) for session_id in session_ids),
            return_exceptions=True,
        )
        for session_id, result in zip(session_ids, results, strict=True):
            if isinstance(result, Exception) and not isinstance(result, KeyError):
                logger.warning("failed to stop Netwatch session %s during shutdown: %s", session_id, result)

    async def _snapshot_once(self, store: Store, session_id: str, pid: int) -> None:
        try:
            await self._record_snapshot(store, session_id, pid)
        except asyncio.CancelledError:
            store.finish_session(session_id, status="interrupted")
            raise
        except Exception as exc:
            store.finish_session(session_id, status="failed", note=f"attach failed ({type(exc).__name__})")
        else:
            store.finish_session(session_id, status="complete")

    async def _follow_attach(
        self,
        store: Store,
        session_id: str,
        pid: int,
        interval: float,
    ) -> None:
        try:
            while True:
                await self._record_snapshot(store, session_id, pid)
                await asyncio.sleep(interval)
        except asyncio.CancelledError:
            store.finish_session(session_id, status="interrupted")
            raise
        except Exception as exc:
            store.finish_session(session_id, status="failed", note=f"attach failed ({type(exc).__name__})")

    async def _record_snapshot(self, store: Store, session_id: str, pid: int) -> None:
        snapshot = asyncio.create_task(asyncio.to_thread(record_snapshot, store, session_id, pid))
        try:
            await asyncio.shield(snapshot)
        except asyncio.CancelledError:
            await snapshot
            raise

    def _own(self, session_id: str, task: asyncio.Task[None]) -> None:
        self._tasks[session_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(session_id, None))

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


def _validate_command(command: list[str]) -> None:
    if not command or not command[0].strip():
        raise ValueError("command needs an executable")
    if any(not part or "\x00" in part for part in command):
        raise ValueError("command arguments cannot be empty or contain NUL bytes")


def _session_or_raise(store: Store, session_id: str) -> Session:
    session = store.get_session(session_id)
    if session is None:
        raise RuntimeError("netwatch session disappeared")
    return session


def _safe_csv_row(row: dict[str, object]) -> dict[str, object]:
    return {key: _safe_csv_cell(value) for key, value in row.items()}


def _safe_csv_cell(value: object) -> object:
    if not isinstance(value, str) or not value:
        return value
    stripped = value.lstrip()
    if value[0] in "\t\r\n" or (stripped and stripped[0] in "=+-@"):
        return f"'{value}"
    return value
