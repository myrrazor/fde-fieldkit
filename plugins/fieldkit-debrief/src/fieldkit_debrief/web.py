from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from fieldkit_debrief import Store, Tag, build_report, default_db_path, render_html, render_markdown

STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(prefix="/debrief", tags=["debrief"])


class EntryCreate(BaseModel):
    """JSON body for a new debrief entry."""

    text: str
    tag: Tag


@router.get("/entries")
async def list_entries(
    request: Request,
    week: Annotated[str | None, Query()] = None,
    tag: Annotated[Tag | None, Query()] = None,
) -> list[dict[str, object]]:
    """List debrief entries with optional week and tag filters."""

    return [asdict(entry) for entry in _store(request).list(week=week, tag=tag)]


@router.post("/entries", status_code=status.HTTP_201_CREATED)
async def add_entry(request: Request, payload: EntryCreate) -> dict[str, object]:
    """Persist one debrief entry."""

    return asdict(_store(request).add(payload.text, payload.tag))


@router.delete("/entries/{entry_id}")
async def delete_entry(request: Request, entry_id: int) -> Response:
    """Delete one debrief entry by id."""

    if not _store(request).delete(entry_id):
        return JSONResponse(status_code=404, content={"error": f"no entry {entry_id}"})
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/report")
async def weekly_report(
    request: Request,
    week: Annotated[str | None, Query()] = None,
    fmt: Annotated[Literal["md", "html", "json"], Query()] = "md",
) -> dict[str, object]:
    """Render one ISO week's debrief in Markdown, HTML, or JSON form."""

    selected_week = week or _current_week()
    report = build_report(_store(request).list(week=selected_week), selected_week)
    if fmt == "md":
        return {"markdown": render_markdown(report)}
    if fmt == "html":
        return {"html": render_html(report)}
    return asdict(report)


def _store(request: Request) -> Store:
    # the hub leaves debrief_db unset unless the caller overrides it
    return Store(request.app.state.debrief_db or default_db_path())


def _current_week() -> str:
    iso = datetime.now().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"
