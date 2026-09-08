from __future__ import annotations

import base64
from dataclasses import asdict
from io import BytesIO
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile

from fieldkit.core.io import load_table, write_table
from fieldkit.core.pii import PIIKind
from fieldkit.web.routes import read_upload, safe_filename
from fieldkit_scrub import Scrubber, load_or_create_salt

STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(prefix="/scrub", tags=["scrub"])

_TEXT_SUFFIXES = {".log", ".txt"}


@router.post("")
async def scrub_upload(
    file: Annotated[UploadFile, File()],
    kinds: Annotated[str | None, Form()] = None,
    include_mapping: Annotated[bool, Form()] = False,
) -> dict[str, object]:
    """Pseudonymize selected PII kinds in an uploaded table or text file."""

    filename = safe_filename(file.filename)
    content = await read_upload(file)
    scrubber = Scrubber(load_or_create_salt(), kinds=_parse_kinds(kinds))
    if Path(filename).suffix.lower() in _TEXT_SUFFIXES:
        try:
            source = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"invalid text encoding: {exc}") from exc
        scrubbed, summary = scrubber.scrub_text(source)
        output_bytes = scrubbed.encode("utf-8")
    else:
        table = load_table(BytesIO(content), filename=filename)
        frame, summary = scrubber.scrub_dataframe(table)
        output = BytesIO()
        write_table(frame, output, table.fmt)
        output_bytes = output.getvalue()
    return {
        "summary": asdict(summary),
        "file": {
            "filename": f"scrubbed_{filename}",
            "content_b64": base64.b64encode(output_bytes).decode("ascii"),
        },
        "mapping": scrubber.mapping if include_mapping else None,
    }


def _parse_kinds(value: str | None) -> set[PIIKind] | None:
    if value is None:
        return None
    try:
        return {PIIKind(item.strip()) for item in value.split(",") if item.strip()}
    except ValueError as exc:
        choices = ", ".join(kind.value for kind in PIIKind)
        raise ValueError(f"unknown PII kind; choose from: {choices}") from exc
