from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Query, UploadFile

from fieldkit.web.routes import read_upload, safe_filename
from fieldkit_awcp.check import check_spec
from fieldkit_awcp.diff import diff_workload_specs
from fieldkit_awcp.evals import EvalError, EvalSafetyMeasurementError, run_eval
from fieldkit_awcp.render import (
    check_to_json,
    diff_to_json,
    eval_to_json,
    render_check_html,
    render_diff_html,
    render_eval_html,
)
from fieldkit_awcp.spec import WorkloadSpecError, load_mapping

STATIC_DIR = Path(__file__).parent / "static"

router = APIRouter(prefix="/awcp", tags=["awcp"])


@router.post("")
async def check_upload(
    file: Annotated[UploadFile, File()],
    output: Annotated[Literal["json", "html"], Query()] = "json",
) -> dict[str, object]:
    """Validate an uploaded WorkloadSpec."""

    filename = safe_filename(file.filename, fallback="workload.yaml")
    result = check_spec(_load_upload(await read_upload(file), filename), source=filename)
    if output == "html":
        return {"html": render_check_html(result)}
    return json.loads(check_to_json(result))


@router.post("/diff")
async def diff_uploads(
    file_a: Annotated[UploadFile, File()],
    file_b: Annotated[UploadFile, File()],
    output: Annotated[Literal["json", "html"], Query()] = "json",
) -> dict[str, object]:
    """Diff two uploaded WorkloadSpecs."""

    name_a = safe_filename(file_a.filename, fallback="before.yaml")
    name_b = safe_filename(file_b.filename, fallback="after.yaml")
    before = _load_upload(await read_upload(file_a), name_a)
    after = _load_upload(await read_upload(file_b), name_b)
    changes = diff_workload_specs(before, after)
    if output == "html":
        return {"html": render_diff_html(changes, before=name_a, after=name_b)}
    return json.loads(diff_to_json(changes, before=name_a, after=name_b))


@router.post("/eval")
async def eval_uploads(
    file: Annotated[UploadFile, File()],
    suite: Annotated[UploadFile, File()],
    output: Annotated[Literal["json", "html"], Query()] = "json",
) -> dict[str, object]:
    """Score an uploaded golden suite against an uploaded spec. Local only."""

    spec_name = safe_filename(file.filename, fallback="workload.yaml")
    suite_name = safe_filename(suite.filename, fallback="suite.yaml")
    workload = _load_upload(await read_upload(file), spec_name)
    suite_payload = _load_upload(await read_upload(suite), suite_name)
    try:
        with tempfile.TemporaryDirectory() as tmp:
            run = run_eval(
                workload,
                suite_payload,
                artifact_dir=Path(tmp),
                source=spec_name,
            )
    except (EvalError, EvalSafetyMeasurementError) as exc:
        raise ValueError(str(exc)) from exc
    if output == "html":
        return {"html": render_eval_html(run)}
    return json.loads(eval_to_json(run))


def _load_upload(content: bytes, filename: str) -> dict:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{filename} is not utf-8 text") from exc
    try:
        return load_mapping(text, source=filename)
    except WorkloadSpecError as exc:
        raise ValueError(str(exc)) from exc
