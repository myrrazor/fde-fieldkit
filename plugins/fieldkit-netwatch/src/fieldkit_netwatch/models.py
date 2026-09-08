from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Mode(StrEnum):
    """Whether policy decisions are observed or enforced."""

    AUDIT = "audit"
    ENFORCE = "enforce"


class Action(StrEnum):
    """A policy rule's requested action."""

    ALLOW = "allow"
    DENY = "deny"


class EventDecision(StrEnum):
    """What happened to one captured network event."""

    ALLOWED = "allowed"
    BLOCKED = "blocked"
    WOULD_BLOCK = "would_block"
    FAILED = "failed"
    OBSERVED = "observed"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class Session:
    """One supervised command or attached-process observation window."""

    id: str
    started_at: str
    ended_at: str | None
    status: str
    mode: Mode
    agent: str
    command: tuple[str, ...]
    root_pid: int | None
    coverage: tuple[str, ...]
    policy_path: str | None
    http_proxy: str | None
    socks_proxy: str | None
    exit_code: int | None
    note: str | None


@dataclass(frozen=True)
class NetworkEvent:
    """Metadata for one proxy request, tunnel, or sampled socket."""

    id: int
    session_id: str
    started_at: str
    ended_at: str | None
    source: str
    protocol: str
    method: str | None
    host: str
    port: int
    path: str | None
    resolved_ip: str | None
    scope: str
    service: str
    decision: EventDecision
    rule_id: str | None
    detail: str | None
    bytes_sent: int
    bytes_received: int
    process_pid: int | None
    process_name: str | None
    fingerprint: str | None


@dataclass(frozen=True)
class ToolEvent:
    """Sanitized metadata from a supported agent lifecycle hook."""

    id: int
    session_id: str
    occurred_at: str
    event: str
    tool: str
    target: str | None
    correlation_id: str | None


@dataclass
class DestinationSummary:
    """Aggregated activity for one service, host, port, and protocol."""

    service: str
    host: str
    port: int
    protocol: str
    scope: str
    events: int = 0
    allowed: int = 0
    observed: int = 0
    blocked: int = 0
    would_block: int = 0
    failed: int = 0
    unsupported: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    first_seen: str = ""
    last_seen: str = ""
    paths: set[str] = field(default_factory=set)


@dataclass(frozen=True)
class SessionReport:
    """A session plus its totals, grouped destinations, and hook events."""

    session: Session
    totals: dict[str, int]
    destinations: tuple[DestinationSummary, ...]
    events: tuple[NetworkEvent, ...]
    tool_events: tuple[ToolEvent, ...]


def session_to_dict(session: Session) -> dict[str, Any]:
    """Return a JSON-safe session object."""

    return {
        "id": session.id,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "status": session.status,
        "mode": session.mode.value,
        "agent": session.agent,
        "command": list(session.command),
        "root_pid": session.root_pid,
        "coverage": list(session.coverage),
        "policy_path": session.policy_path,
        "http_proxy": session.http_proxy,
        "socks_proxy": session.socks_proxy,
        "exit_code": session.exit_code,
        "note": session.note,
    }


def report_to_dict(report: SessionReport) -> dict[str, Any]:
    """Return a JSON-safe report with sorted endpoint paths."""

    return {
        "session": session_to_dict(report.session),
        "totals": report.totals,
        "destinations": [
            {
                "service": item.service,
                "host": item.host,
                "port": item.port,
                "protocol": item.protocol,
                "scope": item.scope,
                "events": item.events,
                "allowed": item.allowed,
                "observed": item.observed,
                "blocked": item.blocked,
                "would_block": item.would_block,
                "failed": item.failed,
                "unsupported": item.unsupported,
                "bytes_sent": item.bytes_sent,
                "bytes_received": item.bytes_received,
                "first_seen": item.first_seen,
                "last_seen": item.last_seen,
                "paths": sorted(item.paths),
            }
            for item in report.destinations
        ],
        "events": [
            {
                "id": item.id,
                "session_id": item.session_id,
                "started_at": item.started_at,
                "ended_at": item.ended_at,
                "source": item.source,
                "protocol": item.protocol,
                "method": item.method,
                "host": item.host,
                "port": item.port,
                "path": item.path,
                "resolved_ip": item.resolved_ip,
                "scope": item.scope,
                "service": item.service,
                "decision": item.decision.value,
                "rule_id": item.rule_id,
                "detail": item.detail,
                "bytes_sent": item.bytes_sent,
                "bytes_received": item.bytes_received,
                "process_pid": item.process_pid,
                "process_name": item.process_name,
            }
            for item in report.events
        ],
        "tool_events": [
            {
                "id": item.id,
                "session_id": item.session_id,
                "occurred_at": item.occurred_at,
                "event": item.event,
                "tool": item.tool,
                "target": item.target,
                "correlation_id": item.correlation_id,
            }
            for item in report.tool_events
        ],
    }
