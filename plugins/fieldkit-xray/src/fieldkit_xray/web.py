from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Query, UploadFile
from starlette.concurrency import run_in_threadpool

from fieldkit.core.io import load_table
from fieldkit.web.routes import read_upload, safe_filename
from fieldkit_xray import profile_table, to_json
from fieldkit_xray.render import render_html

STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(prefix="/xray", tags=["xray"])


@router.post("")
async def profile_upload(
    file: Annotated[UploadFile, File()],
    output: Annotated[Literal["json", "html"], Query()] = "json",
) -> dict[str, object]:
    """Profile an uploaded table as structured JSON or self-contained HTML."""

    filename = safe_filename(file.filename)
    content = await read_upload(file)
    return await run_in_threadpool(_profile, content, filename, output)


def _profile(content: bytes, filename: str, output: str) -> dict[str, object]:
    table = load_table(BytesIO(content), filename=filename)
    result = profile_table(table)
    if output == "html":
        return {"html": render_html(result)}
    return json.loads(to_json(result))
