from __future__ import annotations

from pathlib import PurePosixPath

from fastapi import UploadFile

from fieldkit.core.io import MAX_DATASET_BYTES

MAX_UPLOAD_BYTES = MAX_DATASET_BYTES


class UploadTooLarge(Exception):
    """Raised when one uploaded file crosses the 50 MB limit."""

    pass


async def read_upload(upload: UploadFile) -> bytes:
    """Read one upload into memory while enforcing Fieldkit's size cap."""

    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadTooLarge
    return content


def safe_filename(filename: str | None, *, fallback: str = "upload") -> str:
    """Return a basename safe to echo in a generated filename."""

    name = PurePosixPath((filename or "").replace("\\", "/")).name
    return fallback if name in {"", ".", ".."} else name
