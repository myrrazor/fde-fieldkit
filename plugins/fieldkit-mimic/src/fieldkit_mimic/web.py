from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path
from typing import Annotated, Literal, cast

from fastapi import APIRouter, File, Form, Request, UploadFile

from fieldkit.core.io import load_table
from fieldkit.web.routes import read_upload, run_job, safe_filename
from fieldkit_mimic import MimicSpec, dump_spec, generate_serialized, learn_spec, load_spec

STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(prefix="/mimic", tags=["mimic"])


class _InMemorySpec:
    def __init__(self, content: str):
        self.content = content

    def read_text(self, encoding: str = "utf-8") -> str:
        return self.content


@router.post("/learn")
async def learn_upload(request: Request, file: Annotated[UploadFile, File()]) -> dict[str, str]:
    """Learn a portable generation spec from an uploaded sample."""

    filename = safe_filename(file.filename)
    content = await read_upload(file)
    return await run_job(request, _learn, content, filename, weight=len(content))


@router.post("/generate")
async def generate_upload(
    request: Request,
    n: Annotated[int, Form(ge=0, le=100_000)],
    file: Annotated[UploadFile | None, File()] = None,
    spec_yaml: Annotated[str | None, Form()] = None,
    seed: Annotated[int, Form()] = 0,
    fmt: Annotated[Literal["csv", "jsonl"], Form()] = "csv",
) -> dict[str, object]:
    """Generate a bounded synthetic dataset from a sample or YAML spec."""

    if (file is None) == (spec_yaml is None):
        raise ValueError("provide exactly one of file or spec_yaml")

    spec = await _resolve_spec(request, file, spec_yaml)
    # 100k rows is the heavy case even when the spec itself is small.
    output, preview = await run_job(
        request,
        _generate,
        spec,
        n,
        seed,
        fmt,
        isolate=n >= 20_000,
    )
    stem = Path(safe_filename(spec.name, fallback="synthetic")).stem or "synthetic"
    return {
        "preview": preview,
        "file": {
            "filename": f"synthetic_{stem}.{fmt}",
            "content_b64": base64.b64encode(output).decode("ascii"),
        },
    }


async def _resolve_spec(
    request: Request, file: UploadFile | None, spec_yaml: str | None
) -> MimicSpec:
    if spec_yaml is not None:
        return await run_job(request, _load_yaml, spec_yaml)
    if file is None:  # guarded above, but keeps the invariant local
        raise ValueError("provide exactly one of file or spec_yaml")

    filename = safe_filename(file.filename)
    content = await read_upload(file)
    if Path(filename).suffix.lower() in {".yaml", ".yml"}:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError(f"invalid mimic spec encoding: {exc}") from exc
        return await run_job(request, _load_yaml, text)
    return await run_job(request, _learn_table, content, filename, weight=len(content))


def _generate(spec: MimicSpec, n: int, seed: int, fmt: str) -> tuple[bytes, list[dict[str, object]]]:
    return generate_serialized(spec, n, seed=seed, fmt=fmt)


def _learn_table(content: bytes, filename: str) -> MimicSpec:
    return learn_spec(load_table(BytesIO(content), filename=filename), name=Path(filename).stem)


def _learn(content: bytes, filename: str) -> dict[str, str]:
    table = load_table(BytesIO(content), filename=filename)
    spec = learn_spec(table, name=Path(filename).stem)
    return {"spec_yaml": dump_spec(spec)}


def _load_yaml(content: str) -> MimicSpec:
    # load_spec only needs read_text(), so keep form YAML in memory and reuse its validator
    source = cast(Path, _InMemorySpec(content))
    return load_spec(source)
