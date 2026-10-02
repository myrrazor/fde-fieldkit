from __future__ import annotations

import importlib
import logging
import re
import time
from contextlib import asynccontextmanager
from html import escape
from ipaddress import ip_address
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.formparsers import FormMessage, FormParser, MultiPartException, MultiPartParser
from starlette.requests import Request as StarletteRequest

from fieldkit import __version__
from fieldkit.plugins import REGISTRY, installed_plugins, web_modules
from fieldkit.web.routes import (
    HEAVY_REQUEST_BYTES,
    MAX_UPLOAD_BYTES,
    ClientGone,
    JobCrashed,
    UploadTooLarge,
    arm_heavy_jobs,
    begin_heavy_request,
    end_heavy_request,
    job_is_waiting,
    release_admission,
    stop_heavy_jobs,
    valid_job_id,
)

# Text fields stay at Starlette's 1 MB cap. Only a generation spec needs to
# be larger, and that one field is still inside the 50 MB body limit.
_TEXT_FIELD_BYTES = 1024 * 1024
_SPEC_FIELDS = {"spec_yaml"}
_starlette_form = StarletteRequest.form


def _part_limit(name: bytes | bytearray | str | None) -> int:
    if name == "spec_yaml" or name == b"spec_yaml":
        return MAX_UPLOAD_BYTES
    return _TEXT_FIELD_BYTES


def _part_too_big(limit: int) -> MultiPartException:
    return MultiPartException(f"Part exceeded maximum size of {int(limit / 1024)}KB.")


def _form_with_upload_limit(  # type: ignore[no-untyped-def]
    self,
    *,
    max_files: int | float = 1000,
    max_fields: int | float = 1000,
    max_part_size: int = _TEXT_FIELD_BYTES,
):
    return _starlette_form(
        self,
        max_files=max_files,
        max_fields=max_fields,
        max_part_size=max_part_size,
    )


def _form_field_start(self: FormParser) -> None:
    self._current_field_size = 0
    self._fk_field_name = bytearray()
    self.messages.append((FormMessage.FIELD_START, b""))


def _form_field_name(self: FormParser, data: bytes, start: int, end: int) -> None:
    chunk = data[start:end]
    name = getattr(self, "_fk_field_name", None)
    if name is None:
        name = bytearray()
        self._fk_field_name = name
    name += chunk
    self._current_field_size += end - start
    if self._current_field_size > _part_limit(name):
        raise _part_too_big(_part_limit(name))
    self.messages.append((FormMessage.FIELD_NAME, chunk))


def _form_field_data(self: FormParser, data: bytes, start: int, end: int) -> None:
    self._current_field_size += end - start
    name = getattr(self, "_fk_field_name", b"")
    if self._current_field_size > _part_limit(name):
        raise _part_too_big(_part_limit(name))
    self.messages.append((FormMessage.FIELD_DATA, data[start:end]))


def _multipart_part_data(self: MultiPartParser, data: bytes, start: int, end: int) -> None:
    message_bytes = data[start:end]
    if self._current_part.file is None:
        limit = _part_limit(self._current_part.field_name)
        if len(self._current_part.data) + len(message_bytes) > limit:
            raise _part_too_big(limit)
        self._current_part.data.extend(message_bytes)
        return
    self._file_parts_to_write.append((self._current_part, message_bytes))


StarletteRequest.form = _form_with_upload_limit  # type: ignore[method-assign]
FormParser.on_field_start = _form_field_start  # type: ignore[method-assign]
FormParser.on_field_name = _form_field_name  # type: ignore[method-assign]
FormParser.on_field_data = _form_field_data  # type: ignore[method-assign]
MultiPartParser.on_part_data = _multipart_part_data  # type: ignore[method-assign]

logger = logging.getLogger(__name__)
_PLUGIN_CACHE_SECONDS = 2.0
_plugin_cache_at = 0.0
_plugin_cache: set[str] | None = None


@asynccontextmanager
async def _lifespan(_app: FastAPI):  # type: ignore[no-untyped-def]
    arm_heavy_jobs()
    yield
    stop_heavy_jobs()


def _installed_snapshot() -> set[str]:
    """Installed plugins, refreshed at most every couple of seconds.

    Scanning entry points and invalidating import caches on every tool request
    stalls the event loop while a CPU-heavy job holds the GIL.
    """

    global _plugin_cache_at, _plugin_cache
    now = time.monotonic()
    if _plugin_cache is not None and now - _plugin_cache_at < _PLUGIN_CACHE_SECONDS:
        return _plugin_cache
    importlib.invalidate_caches()
    _plugin_cache = set(installed_plugins())
    _plugin_cache_at = now
    return _plugin_cache

_BRACKETED_HOST = re.compile(r"^\[([^\]]+)](?::(\d+))?$")
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
        "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
    ),
    "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
}


def create_app(*, debrief_db: Path | None = None) -> FastAPI:
    """Create the local-only Fieldkit HTTP application.

    Tool routes and their static pages come from installed plugins; the hub
    itself only knows how to find them.
    """

    # Drag-drop hub only — no OpenAPI browser surface on the loopback UI.
    app = FastAPI(
        title="Fieldkit",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        lifespan=_lifespan,
    )
    # plugins that care (debrief) fall back to their own default when unset
    app.state.debrief_db = debrief_db
    app.state.mounted_plugins = frozenset()
    app.state.installed_at_start = frozenset(installed_plugins())
    MultiPartParser.spool_max_size = MAX_UPLOAD_BYTES
    MultiPartParser.max_part_size = _TEXT_FIELD_BYTES
    tool_pages = set()

    @app.middleware("http")
    async def enforce_local_request_boundary(  # type: ignore[no-untyped-def]
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        authority = _loopback_authority(request.headers.get("host", ""))
        if authority is None:
            return _secured(JSONResponse(status_code=400, content={"error": "invalid host header"}))
        if request.method not in _SAFE_METHODS and not _is_same_origin_browser_request(
            request, authority
        ):
            return _secured(
                JSONResponse(status_code=403, content={"error": "same-origin request required"})
            )

        path = request.url.path
        tool = _tool_segment(path, app.state.mounted_plugins)
        if tool is not None:
            issue = _plugin_restart_issue(
                tool,
                mounted=set(app.state.mounted_plugins),
                started=set(app.state.installed_at_start),
            )
            if issue:
                if _wants_html(request):
                    return _secured(
                        HTMLResponse(
                            _simple_page("Restart fieldkit serve", issue),
                            status_code=503,
                        )
                    )
                return _secured(JSONResponse(status_code=503, content={"error": issue}))

        if request.method in {"GET", "HEAD"} and path.startswith("/") and path.count("/") == 1:
            tool = path[1:]
            if tool in tool_pages:
                return _secured(RedirectResponse(url=f"{path}/", status_code=307))

        raw_length = request.headers.get("content-length")
        parsed_length = -1
        if raw_length is not None:
            try:
                parsed_length = int(raw_length)
            except ValueError:
                return _secured(
                    JSONResponse(status_code=400, content={"error": "invalid content length"})
                )
            if parsed_length < 0:
                return _secured(
                    JSONResponse(status_code=400, content={"error": "invalid content length"})
                )
            if parsed_length > MAX_UPLOAD_BYTES:
                return _secured(
                    JSONResponse(
                        status_code=413,
                        content={"error": "request too large (50 MB total max)"},
                    )
                )

        # A known-large body takes a place before it is stored. A chunked body
        # takes one only after it has actually passed the heavy threshold, so a
        # DELETE with no body, or a few stalled bytes, does not fill the cap.
        holding_upload = False
        chunked = _is_chunked(request)
        if (
            request.method not in _SAFE_METHODS
            and raw_length is not None
            and parsed_length >= HEAVY_REQUEST_BYTES
        ):
            if not begin_heavy_request(request):
                # Read and drop the body first. Closing early makes the browser
                # report a network error instead of this message.
                await _discard_unread_body(request)
                return _secured(
                    JSONResponse(status_code=429, content={"error": "busy, try again"})
                )
            holding_upload = True

        received = 0
        body_limit_exceeded = False
        admission_full = False
        receive = request.receive

        async def receive_with_limit() -> dict[str, object]:
            nonlocal body_limit_exceeded, received, holding_upload, admission_full
            message = await receive()
            if message.get("type") == "http.disconnect":
                release_admission(request)
            elif message.get("type") == "http.request":
                body = message.get("body", b"")
                if isinstance(body, bytes):
                    received += len(body)
                    if received > MAX_UPLOAD_BYTES:
                        body_limit_exceeded = True
                        raise UploadTooLarge
                    if (
                        chunked
                        and not holding_upload
                        and received >= HEAVY_REQUEST_BYTES
                    ):
                        if not begin_heavy_request(request):
                            admission_full = True
                            raise _AdmissionFull()
                        holding_upload = True
            return message

        # Starlette does not offer a public receive wrapper. Replacing this
        # callback keeps the cap in front of multipart parsing and disk spooling.
        request._receive = receive_with_limit  # noqa: SLF001
        try:
            try:
                response = await call_next(request)
            except ClientGone as exc:
                if exc.reason == "shutdown":
                    response = JSONResponse(
                        status_code=499,
                        content={"error": "server stopped before the job finished"},
                    )
                else:
                    response = Response(status_code=499)
            except JobCrashed as exc:
                logger.warning("heavy job crashed: %s", exc.reason)
                response = JSONResponse(
                    status_code=500,
                    content={"error": _crash_message(exc.reason)},
                )
            except UploadTooLarge:
                response = JSONResponse(
                    status_code=413,
                    content={"error": "request too large (50 MB total max)"},
                )
            except _AdmissionFull:
                response = JSONResponse(
                    status_code=429, content={"error": "busy, try again"}
                )
            except Exception:
                logger.exception("unhandled API error")
                response = JSONResponse(status_code=500, content={"error": "internal error"})
            # FastAPI normalizes receive errors raised while parsing form data to a
            # generic 400. The wrapper still records the authoritative cause.
            if admission_full:
                response = JSONResponse(
                    status_code=429, content={"error": "busy, try again"}
                )
            if body_limit_exceeded:
                response = JSONResponse(
                    status_code=413,
                    content={"error": "request too large (50 MB total max)"},
                )
            return _secured(response)
        finally:
            if holding_upload:
                await end_heavy_request(request)

    @app.exception_handler(UploadTooLarge)
    async def upload_too_large(_request: Request, _exc: UploadTooLarge) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={"error": "file too large (50 MB max)"},
        )

    @app.exception_handler(ValueError)
    async def invalid_input(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": str(exc)})

    @app.exception_handler(StarletteHTTPException)
    async def http_exception(request: Request, exc: StarletteHTTPException) -> Response:
        if exc.status_code == 404 and _wants_html(request):
            return HTMLResponse(
                _simple_page(
                    "Not found",
                    "That page is not part of this Fieldkit hub.",
                ),
                status_code=404,
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Report the local service version and readiness."""

        return {"status": "ok", "version": __version__}

    @app.get("/api/queue/{job_id}", response_model=None)
    async def queue_state(job_id: str) -> dict[str, bool] | JSONResponse:
        """Whether the heavy job tagged with this id is waiting for a slot."""

        if not valid_job_id(job_id):
            return JSONResponse(status_code=400, content={"error": "invalid job id"})
        return {"waiting": job_is_waiting(job_id)}

    @app.get("/api/plugins")
    async def plugins() -> dict[str, object]:
        """Which tools this environment has, and what else exists."""

        importlib.invalidate_caches()
        installed = installed_plugins()
        live = set(installed)
        mounted = set(app.state.mounted_plugins)
        started = set(app.state.installed_at_start)
        rows = [
            {
                "name": name,
                "summary": known.summary,
                "status": "installed" if name in live else "available",
                "runtime": _runtime_label(name, live, started, mounted),
            }
            for name, known in REGISTRY.items()
        ]
        rows += [
            {
                "name": name,
                "summary": "(third-party plugin)",
                "status": "installed",
                "runtime": _runtime_label(name, live, started, mounted),
            }
            for name in sorted(live - set(REGISTRY))
        ]
        return {
            "plugins": rows,
            "restart_required": any(row["runtime"] == "restart" for row in rows),
        }

    mounted_plugins: set[str] = set()
    for name, ep in sorted(web_modules().items()):
        try:
            module = ep.load()
        except Exception:  # one broken plugin must not take the hub down
            logger.exception("web plugin %s failed to load", name)
            continue
        app.include_router(module.router, prefix="/api")
        mounted_plugins.add(name)
        static_dir = getattr(module, "STATIC_DIR", None)
        if static_dir and Path(static_dir).is_dir():
            tool_pages.add(name)
            app.mount(f"/{name}", StaticFiles(directory=static_dir, html=True), name=name)

    app.state.mounted_plugins = frozenset(mounted_plugins)
    static_dir = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


def _runtime_label(name: str, live: set[str], started: set[str], mounted: set[str]) -> str:
    if (name in live) != (name in started) or (name in live and name not in mounted):
        return "restart"
    return "ready" if name in live else "absent"


def _tool_segment(path: str, mounted: set[str]) -> str | None:
    parts = [part for part in path.split("/") if part]
    if not parts:
        return None
    if parts[0] == "api":
        if len(parts) < 2 or parts[1] in {"health", "plugins"}:
            return None
        return parts[1]
    if parts[0] in REGISTRY or parts[0] in mounted:
        return parts[0]
    return None


def _plugin_restart_issue(name: str, *, mounted: set[str], started: set[str]) -> str | None:
    live = _installed_snapshot()
    # Web-only modules mounted at startup have no CLI entry. They are not a
    # plugin that was removed out from under the hub.
    if name in mounted and name not in started:
        return None
    if name in live and name not in started:
        return (
            f"{name} is installed but not loaded in this hub — "
            "restart fieldkit serve to load it"
        )
    if name in started and name not in live:
        return (
            f"{name} was removed after this hub started — "
            "restart fieldkit serve to unload it"
        )
    return None


def _wants_html(request: Request) -> bool:
    if request.url.path.startswith("/api/"):
        return False
    accept = request.headers.get("accept", "")
    return "text/html" in accept


def _simple_page(title: str, message: str) -> str:
    safe_title = escape(title)
    safe_message = escape(message)
    return (
        "<!doctype html><html lang=en><meta charset=utf-8>"
        f"<title>{safe_title} — fieldkit</title>"
        '<link rel="stylesheet" href="/fieldkit.css">'
        f"<body><div class=shell><h1>{safe_title}</h1><p>{safe_message}</p>"
        '<p><a href="/">Back to fieldkit</a></p></div></body></html>'
    )


async def _discard_unread_body(request: Request) -> None:
    while True:
        message = await request.receive()
        kind = message.get("type")
        if kind == "http.disconnect" or kind != "http.request":
            return
        if not message.get("more_body", False):
            return


class _AdmissionFull(Exception):
    """A chunked body crossed the heavy threshold after the queue was full."""


def _is_chunked(request: Request) -> bool:
    """True only when the client actually declared a chunked body."""

    return "chunked" in request.headers.get("transfer-encoding", "").lower()


def _crash_message(reason: str) -> str:
    """A short crash label. Parser text stays in the log, not in the toast."""

    cleaned = " ".join(reason.split())
    if not cleaned or len(cleaned) > 80:
        return "the job crashed"
    return f"the job crashed: {cleaned}"


def _secured(response: Response) -> Response:
    for name, value in _SECURITY_HEADERS.items():
        response.headers[name] = value
    return response


def _is_loopback_host(raw_host: str) -> bool:
    return _loopback_authority(raw_host) is not None


def _loopback_authority(raw_host: str) -> str | None:
    raw_host = raw_host.strip()
    bracketed = _BRACKETED_HOST.fullmatch(raw_host)
    if bracketed:
        host, port = bracketed.groups()
        bracketed_host = True
    else:
        if raw_host.count(":") > 1:
            return None
        host, separator, port = raw_host.partition(":")
        if separator and not port:
            return None
        if not separator:
            port = ""
        bracketed_host = False

    if port and (not port.isascii() or not port.isdecimal() or len(port) > 5 or int(port) > 65535):
        return None
    if host.lower() == "localhost":
        if bracketed_host:
            return None
        normalized_host = "localhost"
    else:
        try:
            address = ip_address(host)
        except ValueError:
            return None
        if not address.is_loopback:
            return None
        normalized_host = f"[{address.compressed}]" if address.version == 6 else address.compressed
        if bracketed_host != (address.version == 6):
            return None
    return f"{normalized_host}:{port}" if port else normalized_host


def _is_same_origin_browser_request(request: Request, authority: str) -> bool:
    origins = request.headers.getlist("origin")
    if len(origins) != 1 or origins[0] != f"http://{authority}":
        return False

    fetch_sites = request.headers.getlist("sec-fetch-site")
    return not fetch_sites or (len(fetch_sites) == 1 and fetch_sites[0] == "same-origin")
