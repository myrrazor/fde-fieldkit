from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from fieldkit.cli import app
from fieldkit.web import create_app
from fieldkit_awcp.check import check_spec
from fieldkit_awcp.diff import diff_workload_specs
from fieldkit_awcp.evals import (
    ArtifactStore,
    EvalError,
    EvalSafetyMeasurementError,
    EvalService,
    load_eval_suite,
    run_eval,
)
from fieldkit_awcp.fingerprint import fingerprint_workload_spec
from fieldkit_awcp.spec import load_mapping, load_workload_spec, validate_workload_spec
from fieldkit_awcp.web import router as awcp_router


runner = CliRunner()


def test_sample_workload_validates(example_dir: Path) -> None:
    spec = load_workload_spec(example_dir / "support-ticket-triage.yaml")
    result = validate_workload_spec(spec)

    assert result.ok
    assert result.errors == []
    assert result.workload_name == "support-ticket-triage"
    assert result.project == "customer-success-ai"


def test_yaml_and_json_round_trip_the_same_spec(example_dir: Path, tmp_path: Path) -> None:
    spec = load_workload_spec(example_dir / "support-ticket-triage.yaml")
    json_path = tmp_path / "workload.json"
    json_path.write_text(json.dumps(spec), encoding="utf-8")

    assert load_workload_spec(json_path) == spec


def test_missing_owner_is_rejected() -> None:
    spec = {
        "apiVersion": "aiworkloads.dev/v1alpha1",
        "kind": "AIWorkload",
        "metadata": {"name": "bad-workload", "project": "demo"},
        "spec": {
            "description": "Missing owner should fail.",
            "inputs": {"schema": {"type": "object"}},
            "outputs": {"schema": {"type": "object"}},
            "modelRoute": {"gateway": "gw", "primary": "company/primary-chat"},
            "evals": {"requiredSuites": ["demo-suite"], "gates": {"minOverallScore": 0.8}},
            "policies": {"requiredPacks": ["baseline"], "enforcementMode": "block"},
            "privacy": {"storeInputs": False, "storeOutputs": False},
        },
    }

    result = validate_workload_spec(spec)

    assert not result.ok
    assert "metadata.owner is required" in result.errors


def test_wildcard_tool_scope_is_rejected_without_echoing_secrets(example_dir: Path) -> None:
    spec = load_workload_spec(example_dir / "support-ticket-triage.yaml")
    secret = "sk-live-secret:*"
    spec["spec"]["tools"]["allowed"][0]["scopes"] = [secret]

    result = validate_workload_spec(spec)

    assert not result.ok
    assert "tools.allowed[0].scopes contains wildcard scope" in result.errors
    assert secret not in str(result.errors)
    assert "sk-live-" not in str(result.errors)


@pytest.mark.parametrize(
    "entry, expected",
    [
        ("customer:delete", "tools.allowed[0] must be an object"),
        (None, "tools.allowed[0] must be an object"),
        ({"scopes": ["customer:delete"]}, "tools.allowed[0].name is required"),
        (
            {"name": "customer.delete", "scopes": "customer:delete"},
            "tools.allowed[0].scopes must be a list",
        ),
        (
            {"name": "customer.delete", "requiresApproval": "false"},
            "tools.allowed[0].requiresApproval must be a boolean",
        ),
    ],
)
def test_malformed_allowed_tools_are_rejected(
    example_dir: Path, entry: object, expected: str
) -> None:
    spec = load_workload_spec(example_dir / "support-ticket-triage.yaml")
    spec["spec"]["tools"]["allowed"] = [entry]

    result = validate_workload_spec(spec)

    assert not result.ok
    assert expected in result.errors


def test_unsupported_schema_pattern_is_rejected(example_dir: Path) -> None:
    spec = load_workload_spec(example_dir / "support-ticket-triage.yaml")
    spec["spec"]["inputs"]["schema"]["properties"]["ticket_id"]["pattern"] = "a.*b"

    result = validate_workload_spec(spec)

    assert not result.ok
    assert "pattern is unsupported" in str(result.errors)
    assert "a.*b" not in str(result.errors)


def test_check_fingerprints_prompt_files_and_ignores_escape(example_dir: Path, tmp_path: Path) -> None:
    spec = load_workload_spec(example_dir / "support-ticket-triage.yaml")
    checked = check_spec(spec, source="support-ticket-triage.yaml", base_dir=example_dir)

    assert checked.ok
    assert checked.fingerprint.prompt_hashes["system"].mode == "content"
    assert checked.fingerprint.prompt_hashes["userTemplate"].mode == "content"

    escaped = json.loads(json.dumps(spec))
    escaped["spec"]["prompts"]["system"]["ref"] = "/etc/hosts"
    escaped["spec"]["prompts"]["userTemplate"]["ref"] = "../../../../../../etc/hosts"
    outside = fingerprint_workload_spec(escaped, base_dir=tmp_path)
    assert outside.prompt_hashes["system"].mode == "ref"
    assert outside.prompt_hashes["userTemplate"].mode == "ref"


def test_diff_categorizes_model_prompt_tool_policy_and_retrieval(example_dir: Path) -> None:
    before = load_workload_spec(example_dir / "support-ticket-triage.yaml")
    after = load_workload_spec(example_dir / "support-ticket-triage-v2.yaml")

    changes = diff_workload_specs(before, after)
    kinds = {change.category for change in changes}

    assert {"model", "prompt", "tool", "policy", "retrieval"} <= kinds
    assert any(change.path == "spec.modelRoute.primary" for change in changes)


def test_eval_scores_recorded_cases_and_writes_an_artifact(
    example_dir: Path, tmp_path: Path
) -> None:
    workload = load_workload_spec(example_dir / "support-ticket-triage.yaml")
    suite = load_eval_suite(example_dir / "support-triage-golden.yaml")
    run = run_eval(workload, suite, artifact_dir=tmp_path, source="support-ticket-triage.yaml")

    assert run.status == "passed"
    assert run.score >= 0.82
    assert run.metrics["local_scorer"] is True
    assert run.metrics["case_count"] == 2
    artifact = ArtifactStore(tmp_path).read_json(run.artifact_uri)
    assert artifact["honesty"].startswith("scored locally")
    assert [row["case_id"] for row in artifact["results"]] == ["billing-priority", "login-help"]


def test_eval_fails_when_the_gate_is_higher_than_the_score(tmp_path: Path) -> None:
    service = EvalService(artifact_store=ArtifactStore(tmp_path))
    suite = service.create_suite(
        name="tight-gate",
        config={"gates": {"minOverallScore": 0.95}},
        cases=[{"id": "case-1", "score": 0.5, "pii_leakage_rate": 0.0, "unsupported_claim_rate": 0.0}],
    )
    run = service.start_run(suite.id, "wlv_local", workload_version_spec={"spec": {}})

    assert run.status == "failed"
    assert run.score < 0.95


def test_missing_required_pii_metric_fails_closed(tmp_path: Path) -> None:
    service = EvalService(artifact_store=ArtifactStore(tmp_path))
    suite = service.create_suite(
        name="safety",
        config={"gates": {"maxPiiLeakageRate": 0.0}},
        cases=[{"id": "case-1", "score": 1.0}],
    )

    with pytest.raises(EvalSafetyMeasurementError) as caught:
        service.start_run(suite.id, "wlv_local", workload_version_spec={"spec": {}})

    assert caught.value.reason == "missing_required_safety_metric"
    assert caught.value.metric == "pii_leakage_rate"
    assert list(tmp_path.rglob("result.json")) == []


@pytest.mark.parametrize("value", [None, "0", "not-a-number", [], {}, True, False])
def test_malformed_required_safety_metrics_fail_closed(tmp_path: Path, value: object) -> None:
    service = EvalService(artifact_store=ArtifactStore(tmp_path))
    suite = service.create_suite(
        name="safety",
        config={"gates": {"maxPiiLeakageRate": 0.0}},
        cases=[{"id": "case-1", "score": 1.0, "pii_leakage_rate": value}],
    )

    with pytest.raises(EvalSafetyMeasurementError) as caught:
        service.start_run(suite.id, "wlv_local", workload_version_spec={"spec": {}})

    assert caught.value.reason == "malformed_required_safety_metric"


@pytest.mark.parametrize("value", [math.nan, math.inf, -math.inf])
def test_non_finite_safety_metrics_fail_closed(tmp_path: Path, value: float) -> None:
    service = EvalService(artifact_store=ArtifactStore(tmp_path))
    suite = service.create_suite(
        name="safety",
        config={"gates": {"maxPiiLeakageRate": 0.0}},
        cases=[{"id": "case-1", "score": 1.0, "pii_leakage_rate": value}],
    )

    with pytest.raises(EvalSafetyMeasurementError) as caught:
        service.start_run(suite.id, "wlv_local", workload_version_spec={"spec": {}})

    assert caught.value.reason == "non_finite_safety_metric"


def test_eval_suite_without_cases_is_rejected(tmp_path: Path) -> None:
    service = EvalService(artifact_store=ArtifactStore(tmp_path))
    with pytest.raises(EvalError, match="at least one eval case"):
        service.create_suite(name="empty", cases=[])


def test_cli_check_diff_and_eval(example_dir: Path, tmp_path: Path) -> None:
    check = runner.invoke(
        app,
        [
            "awcp",
            "check",
            str(example_dir / "support-ticket-triage.yaml"),
            "--json",
            str(tmp_path / "check.json"),
            "--html",
            str(tmp_path / "check.html"),
        ],
    )
    assert check.exit_code == 0, check.output
    assert "support-ticket-triage" in check.stdout
    assert "local check only" in check.stdout
    payload = json.loads((tmp_path / "check.json").read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert "awcp" in (tmp_path / "check.html").read_text(encoding="utf-8")

    diff = runner.invoke(
        app,
        [
            "awcp",
            "diff",
            str(example_dir / "support-ticket-triage.yaml"),
            str(example_dir / "support-ticket-triage-v2.yaml"),
        ],
    )
    assert diff.exit_code == 0, diff.output
    assert "modelRoute" in diff.stdout
    assert "Changes · 8" in diff.stdout

    scored = runner.invoke(
        app,
        [
            "awcp",
            "eval",
            str(example_dir / "support-ticket-triage.yaml"),
            "--suite",
            str(example_dir / "support-triage-golden.yaml"),
            "--artifact-dir",
            str(tmp_path / "artifacts"),
        ],
    )
    assert scored.exit_code == 0, scored.stdout + scored.stderr
    assert "passed" in scored.stdout
    assert "no model ran" in scored.stdout


def test_cli_check_fails_on_a_broken_spec(tmp_path: Path) -> None:
    broken = tmp_path / "broken.yaml"
    broken.write_text("kind: NotAWorkload\n", encoding="utf-8")
    result = runner.invoke(app, ["awcp", "check", str(broken)])
    assert result.exit_code == 1
    assert "failed" in result.stdout or "error:" in result.output


def test_cli_rejects_a_missing_file() -> None:
    result = runner.invoke(app, ["awcp", "check", "no-such-workload.yaml"])
    assert result.exit_code == 1
    assert "error:" in result.output


def test_web_check_diff_and_eval(example_dir: Path) -> None:
    client = TestClient(create_app(), base_url="http://localhost", headers={"Origin": "http://localhost"})
    spec = example_dir / "support-ticket-triage.yaml"
    later = example_dir / "support-ticket-triage-v2.yaml"
    suite = example_dir / "support-triage-golden.yaml"

    page = client.get("/awcp/")
    assert page.status_code == 200
    assert "Is this workload spec honest enough to share?" in page.text
    assert "var(--paper)" not in page.text
    assert "var(--surface)" in page.text
    script = client.get("/awcp/app.js")
    assert "stat-row" in script.text
    assert 'class="stats"' not in script.text

    checked = client.post("/api/awcp", files={"file": (spec.name, spec.read_bytes(), "text/yaml")})
    assert checked.status_code == 200
    assert checked.json()["ok"] is True
    assert checked.json()["workload_name"] == "support-ticket-triage"

    html = client.post(
        "/api/awcp?output=html",
        files={"file": (spec.name, spec.read_bytes(), "text/yaml")},
    )
    assert "<html" in html.json()["html"]

    diffed = client.post(
        "/api/awcp/diff",
        files={
            "file_a": (spec.name, spec.read_bytes(), "text/yaml"),
            "file_b": (later.name, later.read_bytes(), "text/yaml"),
        },
    )
    assert diffed.status_code == 200
    assert any(change["path"] == "spec.modelRoute.primary" for change in diffed.json()["changes"])

    scored = client.post(
        "/api/awcp/eval",
        files={
            "file": (spec.name, spec.read_bytes(), "text/yaml"),
            "suite": (suite.name, suite.read_bytes(), "text/yaml"),
        },
    )
    assert scored.status_code == 200
    assert scored.json()["status"] == "passed"
    assert scored.json()["ok"] is True


def test_web_rejects_garbage_yaml() -> None:
    client = TestClient(create_app(), base_url="http://localhost", headers={"Origin": "http://localhost"})
    response = client.post(
        "/api/awcp",
        files={"file": ("bad.yaml", b"- just a list\n", "text/yaml")},
    )
    assert response.status_code == 422


def test_plugin_router_is_mounted_under_awcp() -> None:
    assert awcp_router.prefix == "/awcp"


def test_load_mapping_requires_an_object(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="mapping"):
        load_mapping(yaml.safe_dump(["not", "a", "map"]), source="list.yaml")
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(Exception, match="mapping"):
        load_workload_spec(path)
