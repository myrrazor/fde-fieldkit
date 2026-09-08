from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from fieldkit.cli import app
from fieldkit_tell import cli as tell_cli
from fieldkit_tell.adapters import (
    ADAPTERS,
    AdapterStatus,
    DetectorResult,
    active_remote_adapters,
    run_detectors,
)
from fieldkit_tell import ml as tell_ml

_ALL_ENV_VARS = {name for adapter in ADAPTERS for name in adapter.env_vars}
_TEXT = "Field notes should include facts, ownership, and the next decision. " * 10


@pytest.fixture(autouse=True)
def no_detector_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in _ALL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.mark.parametrize(
    ("adapter_name", "payload", "expected_probability", "expected_label"),
    [
        (
            "pangram",
            {"ai_likelihood": 0.81, "label": "Likely AI"},
            0.81,
            "Likely AI",
        ),
        (
            "gptzero",
            {
                "documents": [
                    {
                        "class_probabilities": {"ai": 0.72},
                        "predicted_class": "MIXED",
                    }
                ]
            },
            0.72,
            "MIXED",
        ),
        (
            "originality",
            {"score": {"ai": 0.64}, "classification": "AI"},
            0.64,
            "AI",
        ),
        (
            "copyleaks",
            {"summary": {"ai": 0.73}, "label": "AI content"},
            0.73,
            "AI content",
        ),
        (
            "sapling",
            {"score": 0.68, "verdict": "machine-written"},
            0.68,
            "machine-written",
        ),
        (
            "winston",
            {"score": 20, "result": "20% human"},
            0.8,
            "20% human",
        ),
        (
            "zerogpt",
            {"data": {"fakePercentage": 77, "feedback": "Most likely AI"}},
            0.77,
            "Most likely AI",
        ),
    ],
)
def test_adapter_success_normalizes_score_and_preserves_label(
    monkeypatch: pytest.MonkeyPatch,
    adapter_name: str,
    payload: dict[str, object],
    expected_probability: float,
    expected_label: str,
) -> None:
    adapter = next(item for item in ADAPTERS if item.name == adapter_name)
    for name in adapter.env_vars:
        monkeypatch.setenv(name, f"{name}-test")

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "id.copyleaks.com":
            return httpx.Response(200, json={"access_token": "token"})
        return httpx.Response(200, json=payload)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = _result_for(adapter_name, run_detectors(_TEXT, offline=False, client=client))

    assert result.status == AdapterStatus.RAN
    assert result.ai_probability == pytest.approx(expected_probability)
    assert result.label == expected_label


def test_pangram_current_async_schema_is_supported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIELDKIT_TELL_PANGRAM_KEY", "pangram-test")
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(f"{request.method} {request.url.path}")
        if request.method == "POST":
            return httpx.Response(200, json={"task_id": "task-1"})
        return httpx.Response(
            200,
            json={
                "stage": "STAGE_SUCCESS",
                "fraction_ai": 0.61,
                "prediction_short": "Mixed",
                "windows": [
                    {
                        "start_index": 0,
                        "end_index": 10,
                        "ai_assistance_score": 0.55,
                    }
                ],
            },
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = _result_for("pangram", run_detectors(_TEXT, offline=False, client=client))

    assert calls == ["POST /task", "GET /task/task-1"]
    assert result.ai_probability == 0.61
    assert result.label == "Mixed"
    assert result.spans[0].score == 0.55


@pytest.mark.parametrize(
    ("handler", "detail"),
    [
        (lambda request: httpx.Response(500, request=request), "HTTP 500"),
        (
            lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("late", request=request)),
            "request timed out",
        ),
    ],
)
def test_http_failures_become_error_rows(
    monkeypatch: pytest.MonkeyPatch,
    handler: Callable[[httpx.Request], httpx.Response],
    detail: str,
) -> None:
    monkeypatch.setenv("FIELDKIT_TELL_SAPLING_KEY", "sapling-test")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = _result_for("sapling", run_detectors(_TEXT, offline=False, client=client))

    assert result.status == AdapterStatus.ERROR
    assert result.ai_probability is None
    assert detail in result.detail


def test_missing_keys_never_touch_transport() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        results = run_detectors(_TEXT, offline=False, client=client)

    assert calls == 0
    assert len(results) == len(ADAPTERS)
    assert all(result.status == AdapterStatus.SKIPPED for result in results)
    assert _result_for("sapling", results).detail == "no FIELDKIT_TELL_SAPLING_KEY set"


def test_vendor_minimum_skips_without_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIELDKIT_TELL_WINSTON_KEY", "winston-test")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = _result_for("winston", run_detectors("too short", offline=False, client=client))

    assert calls == 0
    assert result.status == AdapterStatus.SKIPPED
    assert result.detail == "text under vendor minimum"


def test_offline_skips_every_adapter_even_when_keyed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in _ALL_ENV_VARS:
        monkeypatch.setenv(name, "configured")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        results = run_detectors(_TEXT, offline=True, client=client)

    assert calls == 0
    assert [result.adapter for result in results] == [adapter.name for adapter in ADAPTERS]
    assert all(result.detail == "offline mode" for result in results)
    assert active_remote_adapters(_TEXT) == []
    assert [adapter.name for adapter in active_remote_adapters(_TEXT, offline=False)] == [
        adapter.name for adapter in ADAPTERS
    ]


def test_python_api_defaults_offline_even_with_credentials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An ambient vendor key must never turn an omitted argument into egress."""

    for name in _ALL_ENV_VARS:
        monkeypatch.setenv(name, "configured")
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={}, request=request)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        results = run_detectors(_TEXT, client=client)

    assert calls == 0
    assert [result.adapter for result in results] == [adapter.name for adapter in ADAPTERS]
    assert all(result.detail == "offline mode" for result in results)


def test_malformed_vendor_payload_is_one_error_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIELDKIT_TELL_GPTZERO_KEY", "gptzero-test")

    with httpx.Client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={}))
    ) as client:
        result = _result_for("gptzero", run_detectors(_TEXT, offline=False, client=client))

    assert result.status == AdapterStatus.ERROR
    assert result.detail.startswith("unexpected payload:")


def test_missing_ml_extra_is_an_explicit_skip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tell_ml, "ml_available", lambda: False)

    result = tell_ml.run_local_detector("A local-only check.")

    assert result.status == AdapterStatus.SKIPPED
    assert result.detail == "install with: uv sync --extra ml"


def test_cli_keyless_default_is_offline(fixture_dir: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    keyless_path = tmp_path / "keyless.json"
    source = fixture_dir / "slop_sample.md"

    keyless = runner.invoke(app, ["tell", "check", str(source), "--json", str(keyless_path)])
    keyless_payload = json.loads(keyless_path.read_text(encoding="utf-8"))

    assert keyless.exit_code == 0, keyless.output
    assert all(row["status"] == "skipped" for row in keyless_payload["detectors"])
    assert all(row["detail"] == "offline mode" for row in keyless_payload["detectors"])
    assert len(keyless_payload["detectors"]) == len(ADAPTERS)


def test_cli_warns_before_remote_send(monkeypatch: pytest.MonkeyPatch, fixture_dir: Path) -> None:
    monkeypatch.setenv("FIELDKIT_TELL_SAPLING_KEY", "sapling-test")
    fake_result = DetectorResult(
        "sapling",
        "Sapling",
        AdapterStatus.RAN,
        0.5,
        "Mixed",
        [],
        "",
        1.0,
    )
    monkeypatch.setattr(tell_cli, "run_detectors", lambda *args, **kwargs: [fake_result])

    result = CliRunner().invoke(
        app, ["tell", "check", str(fixture_dir / "slop_sample.md"), "--remote"]
    )

    assert result.exit_code == 0, result.output
    assert result.output.startswith("sending text to 1 remote services: Sapling")
    assert result.output.index("sending text") < result.output.index("Stylometric tells")


def test_cli_stays_offline_with_keys_until_remote_flag(
    monkeypatch: pytest.MonkeyPatch, fixture_dir: Path
) -> None:
    monkeypatch.setenv("FIELDKIT_TELL_SAPLING_KEY", "sapling-test")
    offline_values: list[bool] = []

    def fake_run(_text: str, **kwargs: object) -> list[DetectorResult]:
        offline_values.append(bool(kwargs["offline"]))
        return []

    monkeypatch.setattr(tell_cli, "run_detectors", fake_run)

    result = CliRunner().invoke(app, ["tell", "check", str(fixture_dir / "slop_sample.md")])

    assert result.exit_code == 0, result.output
    assert offline_values == [True]
    assert "sending text" not in result.output


def test_adapters_command_reports_names_without_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIELDKIT_TELL_SAPLING_KEY", "secret-value")

    result = CliRunner().invoke(app, ["tell", "adapters"])

    assert result.exit_code == 0, result.output
    assert all(adapter.display_name in result.output for adapter in ADAPTERS)
    assert "FIELDKIT_TELL_SAPLING_KEY" in result.output
    assert "secret-value" not in result.output


def _result_for(name: str, results: list[DetectorResult]) -> DetectorResult:
    return next(result for result in results if result.adapter == name)
