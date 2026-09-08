from __future__ import annotations

import asyncio
import hmac
import ipaddress
import json
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError

from fieldkit_netwatch.agents import AgentKind, capability_report, discover_agents
from fieldkit_netwatch.control import (
    ControlPlane,
    check_policy_destination,
    default_policy_path,
    load_policy_state,
    report_as_csv,
    save_policy_document,
)
from fieldkit_netwatch.models import Mode, report_to_dict, session_to_dict
from fieldkit_netwatch.policy import Policy
from fieldkit_netwatch.store import Store, default_db_path

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def _netwatch_lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.netwatch_control_planes = {}
    try:
        yield
    finally:
        planes = tuple(app.state.netwatch_control_planes.values())
        await asyncio.gather(*(plane.shutdown() for plane in planes), return_exceptions=True)
        app.state.netwatch_control_planes.clear()


router = APIRouter(prefix="/netwatch", tags=["netwatch"], lifespan=_netwatch_lifespan)
_CONTROL_TOKEN = secrets.token_urlsafe(32)


class RunPayload(BaseModel):
    """Validated direct-argv launch request from the local dashboard."""

    command: list[str]
    mode: Mode = Mode.AUDIT
    agent: AgentKind = AgentKind.AUTO
    use_policy: bool = True


class AttachPayload(BaseModel):
    """Validated process-observation request from the local dashboard."""

    pid: int
    follow: bool = True
    interval: float = Field(default=1.0, ge=0.1)


class PolicyCheckPayload(BaseModel):
    """One destination to explain against the managed policy."""

    destination: str
    protocol: str = "https"
    mode: Mode = Mode.ENFORCE


@router.get("/status")
def status(request: Request) -> dict[str, object]:
    """Report local capture capabilities without making a network request."""

    payload = capability_report()
    payload["storage"] = str(Store().db_path)
    payload["control_available"] = _is_loopback_request(request)
    return payload


@router.get("/control")
def control_token(request: Request) -> dict[str, object]:
    """Issue the per-process token only to a direct loopback browser."""

    _require_loopback(request)
    return {"token": _CONTROL_TOKEN, "policy_path": str(default_policy_path())}


@router.get("/overview")
def overview() -> dict[str, object]:
    """Return cross-session traffic grouped by source, agent, and destination."""

    return Store().overview()


@router.get("/agents")
def agents() -> dict[str, object]:
    """List running supported agent roots with redacted arguments."""

    rows = [
        {
            "pid": row.pid,
            "ppid": row.ppid,
            "agent": row.agent.value,
            "executable": row.executable,
            "command": row.command,
        }
        for row in discover_agents()
    ]
    return {"agents": rows}


@router.get("/sessions")
def sessions(request: Request) -> dict[str, object]:
    """List saved sessions newest first."""

    store = Store()
    return {
        "storage": str(store.db_path),
        "owned_sessions": list(_control_plane(request).active_session_ids()),
        "sessions": [session_to_dict(session) for session in store.list_sessions()],
    }


@router.get("/sessions/{session_id}")
def session_report(session_id: str) -> dict[str, object]:
    """Return one session with grouped and raw metadata."""

    try:
        return report_to_dict(Store().report(session_id))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"no netwatch session {session_id!r}") from exc


@router.get("/sessions/{session_id}/export.json")
def export_json(session_id: str) -> Response:
    """Download one complete metadata-only report as JSON."""

    report = _report_or_404(session_id)
    return Response(
        json.dumps(report_to_dict(report), indent=2) + "\n",
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="netwatch-{report.session.id}.json"'},
    )


@router.get("/sessions/{session_id}/export.csv")
def export_csv(session_id: str) -> Response:
    """Download one network/tool evidence ledger as CSV."""

    report = _report_or_404(session_id)
    return Response(
        report_as_csv(report),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="netwatch-{report.session.id}.csv"'},
    )


@router.post("/sessions/{session_id}/stop")
async def stop_session(session_id: str, request: Request) -> dict[str, object]:
    """Stop only a run or attachment owned by this server process."""

    _require_control(request)
    try:
        session = await _control_plane(request).stop(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=409, detail="this server does not own that running session") from exc
    return {"session": session_to_dict(session)}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str, request: Request) -> dict[str, object]:
    """Delete a stopped session and its local evidence."""

    _require_control(request)
    store = Store()
    try:
        deleted = store.delete_session(session_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail=f"no netwatch session {session_id!r}")
    return {"deleted": session_id}


@router.post("/runs", status_code=202)
async def start_run(request: Request) -> dict[str, object]:
    """Start a non-shell supervised command owned by this dashboard server."""

    _require_control(request)
    try:
        payload = RunPayload.model_validate(await request.json())
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail="invalid supervised command request") from exc
    try:
        session = await _control_plane(request).start_run(
            payload.command,
            mode=payload.mode,
            agent=payload.agent,
            use_policy=payload.use_policy,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=_safe_launch_error(exc)) from exc
    return {"session": session_to_dict(session)}


@router.post("/attachments", status_code=202)
async def start_attachment(request: Request) -> dict[str, object]:
    """Start an observation-only process attachment."""

    _require_control(request)
    try:
        payload = AttachPayload.model_validate(await request.json())
    except (json.JSONDecodeError, ValidationError) as exc:
        raise HTTPException(status_code=422, detail="invalid process attachment request") from exc
    try:
        session = await _control_plane(request).start_attach(
            payload.pid,
            follow=payload.follow,
            interval=payload.interval,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"session": session_to_dict(session)}


@router.get("/policy/starter")
def starter_policy() -> dict[str, object]:
    """Return the deny-by-default starter policy used by the CLI."""

    return Policy.starter().as_dict()


@router.get("/policy")
def managed_policy() -> dict[str, object]:
    """Return the dashboard-managed policy or an unsaved starter."""

    return load_policy_state().as_dict()


@router.put("/policy")
async def save_policy(request: Request) -> dict[str, object]:
    """Replace the dashboard-managed policy after full validation."""

    _require_control(request)
    try:
        payload = await request.json()
        return save_policy_document(payload).as_dict()
    except (json.JSONDecodeError, OSError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/policy/validate")
async def validate_policy(request: Request) -> dict[str, object]:
    """Validate and normalize an imported policy without writing it."""

    _require_control(request)
    try:
        payload = await request.json()
        return {"policy": Policy.from_dict(payload).as_dict()}
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/policy/check")
async def check_policy(request: Request) -> dict[str, object]:
    """Explain a managed policy decision for one user-requested destination."""

    _require_control(request)
    try:
        payload = PolicyCheckPayload.model_validate(await request.json())
        return await check_policy_destination(
            payload.destination,
            protocol=payload.protocol,
            mode=payload.mode,
        )
    except (json.JSONDecodeError, OSError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _report_or_404(session_id: str):  # type: ignore[no-untyped-def]
    try:
        return Store().report(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"no netwatch session {session_id!r}") from exc


def _require_control(request: Request) -> None:
    _require_loopback(request)
    if request.headers.get("content-type", "").split(";", 1)[0] != "application/json":
        raise HTTPException(status_code=415, detail="local control requests must use JSON")
    supplied = request.headers.get("x-fieldkit-control", "")
    if not hmac.compare_digest(supplied, _CONTROL_TOKEN):
        raise HTTPException(status_code=403, detail="missing or invalid local control token")


def _require_loopback(request: Request) -> None:
    if not _is_loopback_request(request):
        raise HTTPException(status_code=403, detail="netwatch controls are available on loopback only")
    host = request.headers.get("host", "")
    for header in ("origin", "referer"):
        value = request.headers.get(header)
        if value and urlsplit(value).netloc.lower() != host.lower():
            raise HTTPException(status_code=403, detail="cross-origin netwatch control request refused")
    fetch_site = request.headers.get("sec-fetch-site")
    if fetch_site not in {None, "none", "same-origin"}:
        raise HTTPException(status_code=403, detail="cross-site netwatch control request refused")


def _is_loopback_request(request: Request) -> bool:
    client = request.client.host if request.client else ""
    host = urlsplit(f"//{request.headers.get('host', '')}").hostname or ""
    return _is_loopback_name(client) and _is_loopback_name(host)


def _is_loopback_name(value: str) -> bool:
    if value.lower().rstrip(".") == "localhost":
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _safe_launch_error(exc: Exception) -> str:
    message = str(exc)
    if message.startswith("command not found:"):
        return message
    return f"couldn't start supervised command ({type(exc).__name__})"


def _control_plane(request: Request) -> ControlPlane:
    planes: dict[Path, ControlPlane] | None = getattr(
        request.app.state,
        "netwatch_control_planes",
        None,
    )
    if planes is None:
        raise RuntimeError("Netwatch control lifecycle is not initialized")
    configured_path = default_db_path()
    key = configured_path.resolve()
    return planes.setdefault(key, ControlPlane(configured_path))
