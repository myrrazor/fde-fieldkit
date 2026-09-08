from __future__ import annotations

import json
import os
import sqlite3
import uuid
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from fieldkit_netwatch.destinations import redact_command
from fieldkit_netwatch.models import (
    DestinationSummary,
    EventDecision,
    Mode,
    NetworkEvent,
    Session,
    SessionReport,
    ToolEvent,
)


def default_db_path() -> Path:
    """Return the configured evidence database path."""

    configured = os.environ.get("FIELDKIT_NETWATCH_DB")
    return Path(configured).expanduser() if configured else Path.home() / ".fieldkit" / "netwatch.db"


class Store:
    """Concurrent-safe SQLite storage for sessions and metadata-only events."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or default_db_path()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()
        try:
            self.db_path.chmod(0o600)
        except OSError:
            # Some mounted filesystems do not expose POSIX mode bits. SQLite still works there.
            pass

    def create_session(
        self,
        *,
        mode: Mode,
        agent: str,
        command: list[str] | tuple[str, ...],
        coverage: tuple[str, ...],
        policy_path: Path | None = None,
        status: str = "starting",
        root_pid: int | None = None,
        note: str | None = None,
    ) -> Session:
        """Create a session while retaining the executable but no command arguments."""

        session_id = uuid.uuid4().hex
        started_at = _now()
        safe_command = redact_command(command)
        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                INSERT INTO sessions(
                    id, started_at, status, mode, agent, command_json, root_pid,
                    coverage_json, policy_path, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    started_at,
                    status,
                    mode.value,
                    agent,
                    json.dumps(safe_command),
                    root_pid,
                    json.dumps(coverage),
                    str(policy_path) if policy_path else None,
                    note,
                ),
            )
        session = self.get_session(session_id)
        if session is None:
            raise sqlite3.DatabaseError("couldn't read the new netwatch session")
        return session

    def mark_running(
        self,
        session_id: str,
        *,
        root_pid: int,
        coverage: tuple[str, ...],
        http_proxy: str,
        socks_proxy: str,
        note: str | None = None,
    ) -> None:
        """Record the child PID and active proxy listeners."""

        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE sessions
                SET status = 'running', root_pid = ?, coverage_json = ?,
                    http_proxy = ?, socks_proxy = ?, note = COALESCE(?, note)
                WHERE id = ?
                """,
                (
                    root_pid,
                    json.dumps(coverage),
                    http_proxy,
                    socks_proxy,
                    note,
                    session_id,
                ),
            )

    def finish_session(
        self,
        session_id: str,
        *,
        status: str,
        exit_code: int | None = None,
        note: str | None = None,
    ) -> None:
        """Close a session with its final process status."""

        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE sessions
                SET ended_at = ?, status = ?, exit_code = ?, note = COALESCE(?, note)
                WHERE id = ?
                """,
                (_now(), status, exit_code, note, session_id),
            )

    def get_session(self, session_id: str) -> Session | None:
        """Return one session by id."""

        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return _session_from_row(row) if row is not None else None

    def list_sessions(self) -> list[Session]:
        """List newest sessions first."""

        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT * FROM sessions ORDER BY started_at DESC, id DESC"
            ).fetchall()
        return [_session_from_row(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        """Delete one stopped session and its event evidence."""

        session = self.get_session(session_id)
        if session is None:
            return False
        if session.status in {"starting", "running"}:
            raise ValueError("stop the session before deleting its evidence")
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cursor.rowcount > 0

    def overview(self) -> dict[str, object]:
        """Aggregate all saved evidence by agent, capture source, and destination."""

        sessions = self.list_sessions()
        totals = _counter_row()
        totals.update({"sessions": len(sessions), "running": 0, "services": 0})
        agents: dict[str, dict[str, object]] = {}
        sources: dict[str, dict[str, object]] = {}
        destinations: dict[tuple[str, str, int, str, str], dict[str, object]] = {}
        service_names: set[str] = set()
        for session in sessions:
            if session.status in {"starting", "running"}:
                totals["running"] = int(totals["running"]) + 1
            for event in self.list_network_events(session.id):
                _add_event(totals, event)
                _add_event(agents.setdefault(session.agent, _named_counter("agent", session.agent)), event)
                _add_event(sources.setdefault(event.source, _named_counter("source", event.source)), event)
                _add_destination(destinations, event, session.agent)
                service_names.add(event.service)
        totals["services"] = len(service_names)
        return {
            "totals": totals,
            "agents": sorted(agents.values(), key=_overview_sort_key),
            "sources": sorted(sources.values(), key=_overview_sort_key),
            "destinations": sorted(
                (_public_destination(row) for row in destinations.values()),
                key=lambda row: (-int(row["events"]), str(row["service"]), str(row["host"])),
            ),
        }

    def begin_network_event(
        self,
        *,
        session_id: str,
        source: str,
        protocol: str,
        host: str,
        port: int,
        scope: str,
        service: str,
        decision: EventDecision,
        method: str | None = None,
        path: str | None = None,
        resolved_ip: str | None = None,
        rule_id: str | None = None,
        detail: str | None = None,
        process_pid: int | None = None,
        process_name: str | None = None,
        fingerprint: str | None = None,
    ) -> int:
        """Open an event row before connecting upstream."""

        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO network_events(
                    session_id, started_at, source, protocol, method, host, port,
                    path, resolved_ip, scope, service, decision, rule_id, detail,
                    process_pid, process_name, fingerprint
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    _now(),
                    source,
                    protocol,
                    method,
                    host,
                    port,
                    path,
                    resolved_ip,
                    scope,
                    service,
                    decision.value,
                    rule_id,
                    detail,
                    process_pid,
                    process_name,
                    fingerprint,
                ),
            )
            event_id = cursor.lastrowid
        if event_id is None:
            raise sqlite3.DatabaseError("couldn't read the new network event id")
        return event_id

    def finish_network_event(
        self,
        event_id: int,
        *,
        bytes_sent: int = 0,
        bytes_received: int = 0,
        detail: str | None = None,
        decision: EventDecision | None = None,
    ) -> None:
        """Close an event and record byte totals or a final failure."""

        with closing(self._connect()) as connection, connection:
            connection.execute(
                """
                UPDATE network_events
                SET ended_at = ?, bytes_sent = ?, bytes_received = ?,
                    detail = COALESCE(?, detail), decision = COALESCE(?, decision)
                WHERE id = ?
                """,
                (
                    _now(),
                    bytes_sent,
                    bytes_received,
                    detail,
                    decision.value if decision else None,
                    event_id,
                ),
            )

    def record_observation(
        self,
        *,
        session_id: str,
        fingerprint: str,
        host: str,
        port: int,
        scope: str,
        service: str,
        process_pid: int,
        process_name: str,
        detail: str,
    ) -> bool:
        """Persist one sampled socket, ignoring repeats in the same session."""

        timestamp = _now()
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO network_events(
                    session_id, started_at, ended_at, source, protocol, host, port,
                    resolved_ip, scope, service, decision, detail, process_pid,
                    process_name, fingerprint
                ) VALUES (?, ?, ?, 'lsof', 'tcp', ?, ?, ?, ?, ?, 'observed', ?, ?, ?, ?)
                """,
                (
                    session_id,
                    timestamp,
                    timestamp,
                    host,
                    port,
                    host,
                    scope,
                    service,
                    detail,
                    process_pid,
                    process_name,
                    fingerprint,
                ),
            )
            return cursor.rowcount > 0

    def add_tool_event(
        self,
        *,
        session_id: str,
        event: str,
        tool: str,
        target: str | None,
        correlation_id: str | None,
    ) -> ToolEvent:
        """Persist sanitized agent-hook metadata."""

        timestamp = _now()
        with closing(self._connect()) as connection, connection:
            cursor = connection.execute(
                """
                INSERT INTO tool_events(
                    session_id, occurred_at, event, tool, target, correlation_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (session_id, timestamp, event, tool, target, correlation_id),
            )
            event_id = cursor.lastrowid
        if event_id is None:
            raise sqlite3.DatabaseError("couldn't read the new tool event id")
        return ToolEvent(event_id, session_id, timestamp, event, tool, target, correlation_id)

    def list_network_events(self, session_id: str) -> list[NetworkEvent]:
        """List captured events in arrival order."""

        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM network_events
                WHERE session_id = ? ORDER BY started_at, id
                """,
                (session_id,),
            ).fetchall()
        return [_network_event_from_row(row) for row in rows]

    def list_tool_events(self, session_id: str) -> list[ToolEvent]:
        """List sanitized hook events in arrival order."""

        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT * FROM tool_events
                WHERE session_id = ? ORDER BY occurred_at, id
                """,
                (session_id,),
            ).fetchall()
        return [_tool_event_from_row(row) for row in rows]

    def report(self, session_id: str) -> SessionReport:
        """Build totals and grouped destinations for one session."""

        session = self.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        events = self.list_network_events(session_id)
        tool_events = self.list_tool_events(session_id)
        totals = {
            "events": len(events),
            "allowed": 0,
            "observed": 0,
            "blocked": 0,
            "would_block": 0,
            "failed": 0,
            "unsupported": 0,
            "public": 0,
            "local_private": 0,
            "services": 0,
            "tool_events": len(tool_events),
            "bytes_sent": 0,
            "bytes_received": 0,
        }
        groups: dict[tuple[str, str, int, str, str], DestinationSummary] = {}
        for event in events:
            key = (event.service, event.host, event.port, event.protocol, event.scope)
            group = groups.setdefault(
                key,
                DestinationSummary(
                    service=event.service,
                    host=event.host,
                    port=event.port,
                    protocol=event.protocol,
                    scope=event.scope,
                    first_seen=event.started_at,
                    last_seen=event.started_at,
                ),
            )
            group.events += 1
            group.first_seen = min(group.first_seen, event.started_at)
            group.last_seen = max(group.last_seen, event.ended_at or event.started_at)
            group.bytes_sent += event.bytes_sent
            group.bytes_received += event.bytes_received
            if event.path:
                group.paths.add(event.path)
            if event.decision is EventDecision.BLOCKED:
                group.blocked += 1
                totals["blocked"] += 1
            elif event.decision is EventDecision.WOULD_BLOCK:
                group.would_block += 1
                totals["would_block"] += 1
            elif event.decision is EventDecision.UNSUPPORTED:
                group.unsupported += 1
                totals["unsupported"] += 1
            elif event.decision is EventDecision.FAILED:
                group.failed += 1
                totals["failed"] += 1
            elif event.decision is EventDecision.OBSERVED:
                group.observed += 1
                totals["observed"] += 1
            else:
                group.allowed += 1
                totals["allowed"] += 1
            if event.scope == "public":
                totals["public"] += 1
            else:
                totals["local_private"] += 1
            totals["bytes_sent"] += event.bytes_sent
            totals["bytes_received"] += event.bytes_received
        totals["services"] = len({event.service for event in events})
        destinations = tuple(
            sorted(groups.values(), key=lambda group: (-group.events, group.service, group.host))
        )
        return SessionReport(
            session=session,
            totals=totals,
            destinations=destinations,
            events=tuple(events),
            tool_events=tuple(tool_events),
        )

    def _initialize(self) -> None:
        with closing(self._connect()) as connection, connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions(
                    id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    mode TEXT NOT NULL,
                    agent TEXT NOT NULL,
                    command_json TEXT NOT NULL,
                    root_pid INTEGER,
                    coverage_json TEXT NOT NULL,
                    policy_path TEXT,
                    http_proxy TEXT,
                    socks_proxy TEXT,
                    exit_code INTEGER,
                    note TEXT
                );

                CREATE TABLE IF NOT EXISTS network_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    source TEXT NOT NULL,
                    protocol TEXT NOT NULL,
                    method TEXT,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    path TEXT,
                    resolved_ip TEXT,
                    scope TEXT NOT NULL,
                    service TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    rule_id TEXT,
                    detail TEXT,
                    bytes_sent INTEGER NOT NULL DEFAULT 0,
                    bytes_received INTEGER NOT NULL DEFAULT 0,
                    process_pid INTEGER,
                    process_name TEXT,
                    fingerprint TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS network_event_fingerprint
                    ON network_events(session_id, fingerprint)
                    WHERE fingerprint IS NOT NULL;
                CREATE INDEX IF NOT EXISTS network_event_session
                    ON network_events(session_id, started_at);

                CREATE TABLE IF NOT EXISTS tool_events(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    occurred_at TEXT NOT NULL,
                    event TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    target TEXT,
                    correlation_id TEXT
                );
                CREATE INDEX IF NOT EXISTS tool_event_session
                    ON tool_events(session_id, occurred_at);
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _counter_row() -> dict[str, int]:
    return {
        "events": 0,
        "allowed": 0,
        "observed": 0,
        "blocked": 0,
        "would_block": 0,
        "failed": 0,
        "unsupported": 0,
        "public": 0,
        "local_private": 0,
        "bytes_sent": 0,
        "bytes_received": 0,
    }


def _named_counter(label: str, value: str) -> dict[str, object]:
    return {label: value, **_counter_row()}


def _add_event(row: dict[str, object], event: NetworkEvent) -> None:
    row["events"] = int(row["events"]) + 1
    decision = event.decision.value
    row[decision] = int(row[decision]) + 1
    scope_bucket = "public" if event.scope == "public" else "local_private"
    row[scope_bucket] = int(row[scope_bucket]) + 1
    row["bytes_sent"] = int(row["bytes_sent"]) + event.bytes_sent
    row["bytes_received"] = int(row["bytes_received"]) + event.bytes_received


def _add_destination(
    rows: dict[tuple[str, str, int, str, str], dict[str, object]],
    event: NetworkEvent,
    agent: str,
) -> None:
    key = (event.service, event.host, event.port, event.protocol, event.scope)
    row = rows.setdefault(
        key,
        {
            "service": event.service,
            "host": event.host,
            "port": event.port,
            "protocol": event.protocol,
            "scope": event.scope,
            "agents": set(),
            "sources": set(),
            **_counter_row(),
        },
    )
    _add_event(row, event)
    if isinstance(row["agents"], set):
        row["agents"].add(agent)
    if isinstance(row["sources"], set):
        row["sources"].add(event.source)


def _public_destination(row: dict[str, object]) -> dict[str, object]:
    return {
        **row,
        "agents": sorted(row["agents"]) if isinstance(row["agents"], set) else row["agents"],
        "sources": sorted(row["sources"]) if isinstance(row["sources"], set) else row["sources"],
    }


def _overview_sort_key(row: dict[str, object]) -> tuple[int, str]:
    name = str(row.get("agent") or row.get("source") or "")
    return (-int(row["events"]), name)


def _session_from_row(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        status=row["status"],
        mode=Mode(row["mode"]),
        agent=row["agent"],
        command=tuple(json.loads(row["command_json"])),
        root_pid=row["root_pid"],
        coverage=tuple(json.loads(row["coverage_json"])),
        policy_path=row["policy_path"],
        http_proxy=row["http_proxy"],
        socks_proxy=row["socks_proxy"],
        exit_code=row["exit_code"],
        note=row["note"],
    )


def _network_event_from_row(row: sqlite3.Row) -> NetworkEvent:
    return NetworkEvent(
        id=row["id"],
        session_id=row["session_id"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        source=row["source"],
        protocol=row["protocol"],
        method=row["method"],
        host=row["host"],
        port=row["port"],
        path=row["path"],
        resolved_ip=row["resolved_ip"],
        scope=row["scope"],
        service=row["service"],
        decision=EventDecision(row["decision"]),
        rule_id=row["rule_id"],
        detail=row["detail"],
        bytes_sent=row["bytes_sent"],
        bytes_received=row["bytes_received"],
        process_pid=row["process_pid"],
        process_name=row["process_name"],
        fingerprint=row["fingerprint"],
    )


def _tool_event_from_row(row: sqlite3.Row) -> ToolEvent:
    return ToolEvent(
        id=row["id"],
        session_id=row["session_id"],
        occurred_at=row["occurred_at"],
        event=row["event"],
        tool=row["tool"],
        target=row["target"],
        correlation_id=row["correlation_id"],
    )
