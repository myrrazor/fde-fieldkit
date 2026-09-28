from __future__ import annotations

from pathlib import PurePosixPath

from fastapi import UploadFile

from fieldkit.core.io import MAX_DATASET_BYTES
from fieldkit.web.routes.jobs import (
    HEAVY_REQUEST_BYTES,
    ClientGone,
    JobCrashed,
    arm_heavy_jobs,
    begin_heavy_request,
    end_heavy_request,
    job_is_waiting,
    release_admission,
    run_job,
    stop_heavy_jobs,
)

__all__ = [
    "HEAVY_REQUEST_BYTES",
    "MAX_UPLOAD_BYTES",
    "ClientGone",
    "JobCrashed",
    "UploadTooLarge",
    "arm_heavy_jobs",
    "begin_heavy_request",
    "end_heavy_request",
    "job_is_waiting",
    "release_admission",
    "read_upload",
    "run_job",
    "safe_filename",
    "stop_heavy_jobs",
]

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

    raw = (filename or "").splitlines()[0] if filename else ""
    cleaned = "".join(char for char in raw if char.isprintable() and char not in {'"', "'", "`"})
    name = PurePosixPath(cleaned.replace("\\", "/")).name
    return fallback if name in {"", ".", ".."} else name
