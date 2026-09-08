from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, Query, UploadFile

from fieldkit.core.io import load_table
from fieldkit.web.routes import read_upload, safe_filename
from fieldkit_datadiff import diff_tables, to_json
from fieldkit_datadiff.render import render_html

STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(prefix="/datadiff", tags=["datadiff"])


@router.post("")
async def diff_uploads(
    file_a: Annotated[UploadFile, File()],
    file_b: Annotated[UploadFile, File()],
    keys: Annotated[str | None, Form()] = None,
    output: Annotated[Literal["json", "html"], Query()] = "json",
) -> dict[str, object]:
    """Compare two uploaded tables as structured JSON or HTML."""

    name_a = safe_filename(file_a.filename, fallback="file_a")
    name_b = safe_filename(file_b.filename, fallback="file_b")
    table_a = load_table(BytesIO(await read_upload(file_a)), filename=name_a)
    table_b = load_table(BytesIO(await read_upload(file_b)), filename=name_b)
    result = diff_tables(table_a, table_b, keys=_parse_keys(keys))
    if output == "html":
        return {"html": render_html(result)}
    return json.loads(to_json(result))


def _parse_keys(value: str | None) -> list[str] | None:
    if value is None:
        return None
    keys = [item.strip() for item in value.split(",") if item.strip()]
    if not keys:
        raise ValueError("keys needs at least one column")
    return keys
