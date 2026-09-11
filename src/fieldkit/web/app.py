from __future__ import annotations

import logging
import re
from ipaddress import ip_address
from pathlib import Path
from typing import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.formparsers import MultiPartParser

from fieldkit import __version__
from fieldkit.plugins import REGISTRY, installed_plugins, web_modules
from fieldkit.web.routes import MAX_UPLOAD_BYTES, UploadTooLarge

logger = logging.getLogger(__name__)

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
    )
    # plugins that care (debrief) fall back to their own default when unset
    app.state.debrief_db = debrief_db
    MultiPartParser.spool_max_size = MAX_UPLOAD_BYTES
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
        if request.method in {"GET", "HEAD"} and path.startswith("/") and path.count("/") == 1:
            tool = path[1:]
            if tool in tool_pages:
                return _secured(RedirectResponse(url=f"{path}/", status_code=307))

        raw_length = request.headers.get("content-length")
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

        received = 0
        body_limit_exceeded = False
        receive = request.receive

        async def receive_with_limit() -> dict[str, object]:
            nonlocal body_limit_exceeded, received
            message = await receive()
            if message.get("type") == "http.request":
                body = message.get("body", b"")
                if isinstance(body, bytes):
                    received += len(body)
                    if received > MAX_UPLOAD_BYTES:
                        body_limit_exceeded = True
                        raise UploadTooLarge
            return message

        # Starlette does not offer a public receive wrapper. Replacing this
        # callback keeps the cap in front of multipart parsing and disk spooling.
        request._receive = receive_with_limit  # noqa: SLF001
        try:
            response = await call_next(request)
        except UploadTooLarge:
            response = JSONResponse(
                status_code=413,
                content={"error": "request too large (50 MB total max)"},
            )
        except Exception:
            logger.exception("unhandled API error")
            response = JSONResponse(status_code=500, content={"error": "internal error"})
        # FastAPI normalizes receive errors raised while parsing form data to a
        # generic 400. The wrapper still records the authoritative cause.
        if body_limit_exceeded:
            response = JSONResponse(
                status_code=413,
                content={"error": "request too large (50 MB total max)"},
            )
        return _secured(response)

    @app.exception_handler(UploadTooLarge)
    async def upload_too_large(_request: Request, _exc: UploadTooLarge) -> JSONResponse:
        return JSONResponse(
            status_code=413,
            content={"error": "file too large (50 MB max)"},
        )

    @app.exception_handler(ValueError)
    async def invalid_input(_request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"error": str(exc)})

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        """Report the local service version and readiness."""

        return {"status": "ok", "version": __version__}

    @app.get("/api/plugins")
    async def plugins() -> dict[str, object]:
        """Which tools this environment has, and what else exists."""

        installed = installed_plugins()
        rows = [
            {
                "name": name,
                "summary": known.summary,
                "status": "installed" if name in installed else "available",
            }
            for name, known in REGISTRY.items()
        ]
        rows += [
            {"name": name, "summary": "(third-party plugin)", "status": "installed"}
            for name in sorted(set(installed) - set(REGISTRY))
        ]
        return {"plugins": rows}

    for name, ep in sorted(web_modules().items()):
        try:
            module = ep.load()
        except Exception:  # one broken plugin must not take the hub down
            logger.exception("web plugin %s failed to load", name)
            continue
        app.include_router(module.router, prefix="/api")
        static_dir = getattr(module, "STATIC_DIR", None)
        if static_dir and Path(static_dir).is_dir():
            tool_pages.add(name)
            app.mount(f"/{name}", StaticFiles(directory=static_dir, html=True), name=name)

    static_dir = Path(__file__).parent / "static"
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


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
