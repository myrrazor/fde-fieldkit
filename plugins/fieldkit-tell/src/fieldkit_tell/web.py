from __future__ import annotations

import base64
import hashlib
import secrets
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Literal

from anyio import from_thread
from fastapi import APIRouter, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse

from fieldkit.web.routes import read_upload, safe_filename
from fieldkit_tell.adapters import (
    ADAPTERS,
    active_remote_adapters,
    adapter_is_keyed,
    run_detectors,
)
from fieldkit_tell.ml import ml_available
from fieldkit_tell.render import render_html
from fieldkit_tell.rewrite import unslop, word_diff
from fieldkit_tell.signals import analyze

STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(prefix="/tell", tags=["tell"])

_SESSION_COOKIE = "fieldkit_tell_session"


class EgressIntentStore:
    """Hold the one immediate browser egress intent accepted by this process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._current: tuple[str, str, str, tuple[str, ...]] | None = None

    def issue(self, session: str, payload_digest: str, adapters: tuple[str, ...]) -> str:
        """Replace the prior intent and return a new opaque, single-use token."""

        token = secrets.token_urlsafe(32)
        token_digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        with self._lock:
            self._current = (token_digest, session, payload_digest, adapters)
        return token

    def consume(
        self,
        token: str,
        session: str,
        payload_digest: str,
        adapters: tuple[str, ...],
    ) -> bool:
        """Consume an exact token/session/payload/vendor match once."""

        token_digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        candidate = (token_digest, session, payload_digest, adapters)
        with self._lock:
            if self._current is None or not _intent_matches(self._current, candidate):
                return False
            self._current = None
            return True


_EGRESS_INTENTS = EgressIntentStore()


@router.get("/adapters")
def adapter_status() -> dict[str, object]:
    """Report credential and local-model presence without opening a socket."""

    return {
        "adapters": [
            {
                "name": adapter.name,
                "display_name": adapter.display_name,
                "env_vars": list(adapter.env_vars),
                "keyed": adapter_is_keyed(adapter),
            }
            for adapter in ADAPTERS
        ],
        "ml_available": ml_available(),
    }


@router.post("/egress-intent")
def create_egress_intent(
    request: Request,
    text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
) -> JSONResponse:
    """Authorize one immediate remote check for this browser session and payload."""

    source, _filename = _resolve_text(text, file)
    active = active_remote_adapters(source, offline=False)
    names = tuple(adapter.name for adapter in active)
    session = request.cookies.get(_SESSION_COOKIE) or secrets.token_urlsafe(32)
    token = _EGRESS_INTENTS.issue(session, _payload_digest(source), names) if names else None
    response = JSONResponse(
        {
            "token": token,
            "adapters": [
                {"name": adapter.name, "display_name": adapter.display_name} for adapter in active
            ],
        }
    )
    response.set_cookie(
        _SESSION_COOKIE,
        session,
        httponly=True,
        samesite="strict",
        path="/api/tell",
    )
    return response


@router.post("/check")
def check_text(
    request: Request,
    text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
    offline: Annotated[bool, Form()] = True,
    egress_token: Annotated[str | None, Form()] = None,
    ml: Annotated[bool, Form()] = False,
    timeout: Annotated[float, Form(gt=0, le=120)] = 20.0,
    output: Annotated[Literal["json", "html"], Query()] = "json",
) -> dict[str, object]:
    """Check pasted or uploaded text and return every local and remote row."""

    source, _filename = _resolve_text(text, file)
    active = active_remote_adapters(source, offline=offline)
    if active:
        session = request.cookies.get(_SESSION_COOKIE, "")
        names = tuple(adapter.name for adapter in active)
        allowed = bool(egress_token) and _EGRESS_INTENTS.consume(
            egress_token,
            session,
            _payload_digest(source),
            names,
        )
        if not allowed:
            raise HTTPException(
                status_code=403,
                detail="remote checker confirmation required for this text and vendor set",
            )

    report = analyze(source)
    detectors = run_detectors(
        source,
        offline=offline,
        include_ml=ml,
        timeout=timeout,
    )
    payload = asdict(report)
    payload["detectors"] = [asdict(result) for result in detectors]
    if output == "html":
        payload["html"] = render_html(report, detectors)
    return payload


@router.post("/unslop")
def unslop_text(
    text: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
    max_iterations: Annotated[int, Form(ge=1, le=10)] = 3,
) -> dict[str, object]:
    """Rewrite deterministic patterns and return provenance plus a text download."""

    source, filename = _resolve_text(text, file)
    result = unslop(source, max_iterations=max_iterations)
    payload = asdict(result)
    payload["diff"] = [asdict(operation) for operation in word_diff(source, result.final)]
    stem = Path(filename).stem or "text"
    payload["file"] = {
        "filename": f"unslopped_{stem}.txt",
        "content_b64": base64.b64encode(result.final.encode("utf-8")).decode("ascii"),
    }
    return payload


def _resolve_text(text: str | None, file: UploadFile | None) -> tuple[str, str]:
    if (text is None) == (file is None):
        raise ValueError("provide exactly one of text or file")
    if text is not None:
        return text, "text.txt"
    if file is None:  # guarded above, keeps the type narrow
        raise ValueError("provide exactly one of text or file")

    filename = safe_filename(file.filename, fallback="upload.txt")
    if Path(filename).suffix.lower() not in {".txt", ".md"}:
        raise ValueError("tell uploads must be .txt or .md")
    try:
        content = from_thread.run(read_upload, file)
        return content.decode("utf-8-sig"), filename
    except UnicodeDecodeError as exc:
        raise ValueError(f"invalid text encoding: {exc}") from exc


def _payload_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _intent_matches(
    expected: tuple[str, str, str, tuple[str, ...]],
    candidate: tuple[str, str, str, tuple[str, ...]],
) -> bool:
    return (
        secrets.compare_digest(expected[0], candidate[0])
        and secrets.compare_digest(expected[1], candidate[1])
        and secrets.compare_digest(expected[2], candidate[2])
        and expected[3] == candidate[3]
    )
