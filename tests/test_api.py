from __future__ import annotations

import base64
import csv
import importlib
from io import StringIO
from pathlib import Path
from types import SimpleNamespace

import pytest
from click import unstyle
from fastapi import APIRouter
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from fieldkit import __version__
from fieldkit.cli import app as cli_app
from fieldkit.web import create_app
from fieldkit.web.routes import MAX_UPLOAD_BYTES

# tool routes and internals now live in the plugin packages; the dev
# workspace installs every plugin, so the hub tests exercise the real thing
from fieldkit_scrub import web as scrub_routes
from fieldkit_tell.adapters import ADAPTERS, run_detectors
from fieldkit_tell.render import render_html
from fieldkit_tell.rewrite import unslop
from fieldkit_tell.signals import analyze
from fieldkit_tell import web as tell_routes
from fieldkit_xray import web as xray_routes
from fieldkit_netwatch.models import EventDecision, Mode
from fieldkit_netwatch.store import Store


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(scrub_routes, "load_or_create_salt", lambda: b"api-test" * 4)
    with TestClient(
        create_app(debrief_db=tmp_path / "debrief.db"),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as test_client:
        yield test_client


def _file(path: Path, *, filename: str | None = None) -> tuple[str, bytes]:
    return filename or path.name, path.read_bytes()


def _csv_rows(content_b64: str) -> list[dict[str, str]]:
    text = base64.b64decode(content_b64).decode("utf-8")
    return list(csv.DictReader(StringIO(text)))


def test_health_and_static_hub(client: TestClient) -> None:
    health = client.get("/api/health")
    page = client.get("/")

    assert health.status_code == 200
    assert health.json() == {"status": "ok", "version": __version__}
    assert "fieldkit" in page.text
    assert '<script type="module" src="/hub.js"></script>' in page.text


@pytest.mark.parametrize("host", ["localhost:8765", "127.0.0.1:8765", "[::1]:8765"])
def test_loopback_host_headers_are_allowed(client: TestClient, host: str) -> None:
    assert client.get("/api/health", headers={"host": host}).status_code == 200


@pytest.mark.parametrize(
    "host",
    [
        "attacker.example",
        "attacker.example:8765",
        "localhost.attacker.example",
        "192.168.1.20:8765",
        "localhost:",
        "localhost:not-a-port",
        "localhost:65536",
        f"localhost:{'9' * 5000}",
    ],
)
def test_untrusted_or_malformed_host_cannot_read_debrief_entries(
    client: TestClient, host: str
) -> None:
    created = client.post(
        "/api/debrief/entries",
        json={"text": "Synthetic audit note", "tag": "win"},
    )
    assert created.status_code == 201

    response = client.get("/api/debrief/entries", headers={"host": host})

    assert response.status_code == 400
    assert response.json() == {"error": "invalid host header"}


@pytest.mark.parametrize(
    ("method", "path", "request_kwargs"),
    [
        ("POST", "/api/mimic/generate", {"data": {"n": "1", "spec_yaml": "columns: []"}}),
        ("POST", "/api/xray", {"files": {"file": ("sample.csv", b"id\n1\n")}}),
        ("POST", "/api/debrief/entries", {"json": {"text": "blocked", "tag": "note"}}),
        ("DELETE", "/api/debrief/entries/1", {}),
    ],
)
def test_unsafe_plugin_routes_reject_foreign_origins_before_handlers(
    client: TestClient,
    method: str,
    path: str,
    request_kwargs: dict[str, object],
) -> None:
    response = client.request(
        method,
        path,
        headers={"Origin": "https://attacker.example"},
        **request_kwargs,
    )

    assert response.status_code == 403
    assert response.json() == {"error": "same-origin request required"}


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": ""},
        {"Origin": "null"},
        {"Origin": "http://localhost, https://attacker.example"},
        {"Origin": "http://127.0.0.1"},
        {"Origin": "http://localhost:8765"},
        {"Origin": "http://localhost", "Sec-Fetch-Site": "cross-site"},
        {"Origin": "http://localhost", "Sec-Fetch-Site": "same-site"},
    ],
)
def test_unsafe_requests_reject_missing_malformed_or_cross_site_origin(
    client: TestClient, headers: dict[str, str]
) -> None:
    response = client.post(
        "/api/debrief/entries",
        headers=headers,
        json={"text": "blocked", "tag": "note"},
    )

    assert response.status_code == 403


def test_unsafe_request_without_origin_is_rejected(client: TestClient) -> None:
    prior = client.headers.pop("origin")
    try:
        response = client.post(
            "/api/debrief/entries",
            json={"text": "blocked", "tag": "note"},
        )
    finally:
        client.headers["origin"] = prior

    assert response.status_code == 403


def test_unsafe_request_with_multiple_origin_headers_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/debrief/entries",
        headers=[("Origin", "http://localhost"), ("Origin", "http://localhost")],
        json={"text": "blocked", "tag": "note"},
    )

    assert response.status_code == 403


def test_host_and_origin_must_describe_the_same_loopback_origin(client: TestClient) -> None:
    accepted = client.post(
        "/api/debrief/entries",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1:8765"},
        json={"text": "same origin", "tag": "note"},
    )
    mismatched = client.post(
        "/api/debrief/entries",
        headers={"Host": "127.0.0.1:8765", "Origin": "http://127.0.0.1"},
        json={"text": "blocked", "tag": "note"},
    )

    assert accepted.status_code == 201
    assert mismatched.status_code == 403


def test_dynamic_third_party_plugin_inherits_same_origin_boundary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fieldkit.web import app as app_module

    calls: list[str] = []
    router = APIRouter(prefix="/third-party")

    @router.post("/run", status_code=204)
    async def run_third_party() -> None:
        calls.append("called")

    module = SimpleNamespace(router=router, STATIC_DIR=None)
    entry_point = SimpleNamespace(load=lambda: module)
    monkeypatch.setattr(app_module, "web_modules", lambda: {"third-party": entry_point})

    with TestClient(
        create_app(debrief_db=tmp_path / "debrief.db"),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as third_party_client:
        rejected = third_party_client.post(
            "/api/third-party/run",
            headers={"Origin": "https://attacker.example"},
        )
        accepted = third_party_client.post("/api/third-party/run")

    assert rejected.status_code == 403
    assert accepted.status_code == 204
    assert calls == ["called"]


@pytest.mark.parametrize("path", ["/", "/api/health", "/missing"])
def test_every_response_has_local_security_headers(client: TestClient, path: str) -> None:
    response = client.get(path)

    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]


def test_netwatch_plugin_api_and_static_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "netwatch-api.db"
    monkeypatch.setenv("FIELDKIT_NETWATCH_DB", str(db))
    store = Store(db)
    session = store.create_session(
        mode=Mode.AUDIT,
        agent="codex",
        command=["codex"],
        coverage=("Codex sandbox network proxy",),
        status="complete",
    )
    event_id = store.begin_network_event(
        session_id=session.id,
        source="http-connect",
        protocol="https",
        method="CONNECT",
        host="api.openai.com",
        port=443,
        resolved_ip="8.8.8.8",
        scope="public",
        service="OpenAI API",
        decision=EventDecision.ALLOWED,
    )
    store.finish_network_event(event_id)

    with TestClient(
        create_app(debrief_db=tmp_path / "debrief-netwatch.db"),
        base_url="http://localhost",
    ) as netwatch_client:
        report = netwatch_client.get(f"/api/netwatch/sessions/{session.id}")
        page = netwatch_client.get("/netwatch/")

    assert report.status_code == 200
    assert report.json()["destinations"][0]["service"] == "OpenAI API"
    assert page.status_code == 200
    assert "Who connected, where, and how?" in page.text


def test_shared_busy_indicator_has_orb_and_reduced_motion_fallback(
    client: TestClient,
) -> None:
    script = client.get("/fieldkit.js").text
    styles = client.get("/fieldkit.css").text

    assert 'getContext("2d")' in script
    assert "const size = 20" in script
    assert "MIT-licensed thinking-orbs" in script
    assert "prefers-reduced-motion: reduce" in script
    assert "visibilitychange" in script
    assert "document.hidden" in script
    assert "cancelAnimationFrame" in script
    assert "stopIndicator();" in script
    assert "busy.remove();" in script
    assert ".spinner.has-orb" in styles
    assert ".spinner { animation-duration: 2.5s; }" in styles


def test_awcp_check_diff_eval_and_static_page(client: TestClient) -> None:
    examples = Path(__file__).resolve().parents[1] / "examples" / "awcp"
    spec = examples / "support-ticket-triage.yaml"
    later = examples / "support-ticket-triage-v2.yaml"
    suite = examples / "support-triage-golden.yaml"

    page = client.get("/awcp/")
    checked = client.post("/api/awcp", files={"file": (spec.name, spec.read_bytes())})
    diffed = client.post(
        "/api/awcp/diff",
        files={
            "file_a": (spec.name, spec.read_bytes()),
            "file_b": (later.name, later.read_bytes()),
        },
    )
    scored = client.post(
        "/api/awcp/eval",
        files={
            "file": (spec.name, spec.read_bytes()),
            "suite": (suite.name, suite.read_bytes()),
        },
    )

    assert page.status_code == 200
    assert "fieldkit awcp check SPEC" in page.text
    assert checked.status_code == 200
    assert checked.json()["ok"] is True
    assert diffed.status_code == 200
    assert diffed.json()["ok"] is True
    assert scored.status_code == 200
    assert scored.json()["status"] == "passed"


def test_xray_json_and_html(client: TestClient, fixture_dir: Path) -> None:
    upload = _file(fixture_dir / "customers.csv")

    response = client.post("/api/xray", files={"file": upload})
    html = client.post("/api/xray?output=html", files={"file": upload})

    assert response.status_code == 200
    assert response.json()["row_count"] == 150
    assert response.json()["source"] == "customers.csv"
    assert html.status_code == 200
    assert "<html" in html.json()["html"]


def test_scrub_returns_filtered_csv_and_optional_mapping(
    client: TestClient, fixture_dir: Path
) -> None:
    source = fixture_dir / "customers.csv"
    original_emails = {row["email"] for row in csv.DictReader(StringIO(source.read_text()))}

    response = client.post(
        "/api/scrub",
        files={"file": _file(source, filename="../customers.csv")},
        data={"kinds": "email"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["replaced"]["email"] == 150
    assert payload["file"]["filename"] == "scrubbed_customers.csv"
    assert payload["mapping"] is None
    rows = _csv_rows(payload["file"]["content_b64"])
    assert len(rows) == 150
    assert original_emails.isdisjoint(row["email"] for row in rows)

    mapped = client.post(
        "/api/scrub",
        files={"file": _file(source)},
        data={"kinds": "email", "include_mapping": "true"},
    )
    assert mapped.status_code == 200
    assert mapped.json()["mapping"]


def test_scrub_supports_text_uploads_and_sparse_table_pii(client: TestClient) -> None:
    log_source = b"contact sparse.person@example.com\nstatus=ready\n"
    text_response = client.post(
        "/api/scrub",
        files={"file": ("field.log", log_source)},
        data={"kinds": "email"},
    )
    sparse_csv = b"note\nroutine\ncontact sparse.person@example.com\nroutine again\n"
    sparse_response = client.post(
        "/api/scrub",
        files={"file": ("sparse.csv", sparse_csv)},
        data={"kinds": "email"},
    )

    assert text_response.status_code == 200
    text_payload = text_response.json()
    text_output = base64.b64decode(text_payload["file"]["content_b64"]).decode("utf-8")
    assert text_payload["file"]["filename"] == "scrubbed_field.log"
    assert "sparse.person@example.com" not in text_output
    assert text_payload["summary"]["replaced"] == {"email": 1}

    assert sparse_response.status_code == 200
    sparse_output = base64.b64decode(sparse_response.json()["file"]["content_b64"])
    assert b"sparse.person@example.com" not in sparse_output
    assert sparse_response.json()["summary"]["replaced"] == {"email": 1}


def test_mimic_learns_and_generates_from_yaml(client: TestClient, fixture_dir: Path) -> None:
    learned = client.post(
        "/api/mimic/learn",
        files={"file": _file(fixture_dir / "customers.csv")},
    )

    assert learned.status_code == 200
    spec_yaml = learned.json()["spec_yaml"]
    assert "customer_id" in spec_yaml

    generated = client.post(
        "/api/mimic/generate",
        data={"spec_yaml": spec_yaml, "n": "25", "seed": "7", "fmt": "csv"},
    )

    assert generated.status_code == 200
    payload = generated.json()
    assert len(payload["preview"]) == 20
    assert len(_csv_rows(payload["file"]["content_b64"])) == 25


def test_mimic_generates_directly_from_an_upload(client: TestClient, fixture_dir: Path) -> None:
    response = client.post(
        "/api/mimic/generate",
        files={"file": _file(fixture_dir / "customers.csv")},
        data={"n": "3", "fmt": "jsonl"},
    )

    assert response.status_code == 200
    content = base64.b64decode(response.json()["file"]["content_b64"]).decode()
    assert len(content.splitlines()) == 3


def test_datadiff_json_and_html(client: TestClient, fixture_dir: Path) -> None:
    files = {
        "file_a": _file(fixture_dir / "customers.csv"),
        "file_b": _file(fixture_dir / "customers_v2.csv"),
    }

    response = client.post("/api/datadiff", files=files)
    html = client.post("/api/datadiff?output=html", files=files)

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert rows["added"] == 12
    assert rows["removed"] == 10
    assert rows["changed"] == 25
    assert response.json()["key_detection"]["candidates"][0] == ["customer_id"]
    assert html.status_code == 200
    assert "<html" in html.json()["html"]


def test_debrief_crud_and_reports_use_configured_database(client: TestClient) -> None:
    created = client.post(
        "/api/debrief/entries",
        json={"text": "Pilot approved", "tag": "win"},
    )

    assert created.status_code == 201
    entry = created.json()
    assert entry["text"] == "Pilot approved"
    assert client.get("/api/debrief/entries").json() == [entry]
    assert "Pilot approved" in client.get("/api/debrief/report").json()["markdown"]
    assert "Pilot approved" in client.get("/api/debrief/report?fmt=json").text

    deleted = client.delete(f"/api/debrief/entries/{entry['id']}")
    missing = client.delete(f"/api/debrief/entries/{entry['id']}")
    assert deleted.status_code == 204
    assert deleted.content == b""
    assert missing.status_code == 404
    assert missing.json() == {"error": f"no entry {entry['id']}"}


def test_bad_upload_and_oversize_request_have_clean_errors(client: TestClient) -> None:
    invalid = client.post("/api/xray", files={"file": ("garbage.bin", b"garbage!")})
    too_large = client.post(
        "/api/xray",
        files={"file": ("tiny.csv", b"x\n1\n")},
        headers={"content-length": str(MAX_UPLOAD_BYTES + 1)},
    )

    assert invalid.status_code == 422
    assert "error" in invalid.json()
    assert too_large.status_code == 413
    assert too_large.json() == {"error": "request too large (50 MB total max)"}


def test_streamed_request_is_bounded_before_multipart_parsing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app_module = importlib.import_module("fieldkit.web.app")
    monkeypatch.setattr(app_module, "MAX_UPLOAD_BYTES", 16)
    chunks = iter(
        [
            b'--fde\r\nContent-Disposition: form-data; name="file"; ',
            b'filename="tiny.csv"\r\nContent-Type: text/csv\r\n\r\nx\n1\n\r\n--fde--\r\n',
        ]
    )

    with TestClient(
        create_app(debrief_db=tmp_path / "debrief.db"),
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as tiny_client:
        response = tiny_client.post(
            "/api/xray",
            content=chunks,
            headers={
                "content-type": "multipart/form-data; boundary=fde",
                "transfer-encoding": "chunked",
            },
        )

    assert response.status_code == 413, response.text
    assert response.json() == {"error": "request too large (50 MB total max)"}


def test_unexpected_errors_do_not_leak(
    client: TestClient, fixture_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_profile(_table: object) -> None:
        raise RuntimeError("customer secret should stay private")

    monkeypatch.setattr(xray_routes, "profile_table", fail_profile)
    response = client.post(
        "/api/xray",
        files={"file": _file(fixture_dir / "customers.csv")},
    )

    assert response.status_code == 500
    assert response.json() == {"error": "internal error"}
    assert "customer secret" not in response.text


@pytest.mark.parametrize("force_color", [False, True])
def test_serve_help_exposes_only_loopback_safe_options(
    monkeypatch: pytest.MonkeyPatch, force_color: bool
) -> None:
    if force_color:
        monkeypatch.setenv("TERM", "xterm-256color")
        monkeypatch.setenv("FORCE_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
    result = CliRunner().invoke(cli_app, ["serve", "--help"])
    output = unstyle(result.output)

    assert result.exit_code == 0
    if force_color:
        assert "\x1b[" in result.output
    assert "--host" not in output
    assert "--port" in output


def test_serve_always_binds_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    called: dict[str, object] = {}

    def fake_run(application: object, **kwargs: object) -> None:
        called.update(kwargs)

    monkeypatch.setattr(uvicorn, "run", fake_run)
    result = CliRunner().invoke(cli_app, ["serve", "--port", "9876"])

    assert result.exit_code == 0, result.output
    assert called["host"] == "127.0.0.1"
    assert called["port"] == 9876


def test_tell_adapter_status_is_key_presence_only(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_tell_keys(monkeypatch)

    response = client.get("/api/tell/adapters")

    assert response.status_code == 200
    payload = response.json()
    assert [item["name"] for item in payload["adapters"]] == [adapter.name for adapter in ADAPTERS]
    assert all(item["keyed"] is False for item in payload["adapters"])
    assert all(item["env_vars"] for item in payload["adapters"])
    assert isinstance(payload["ml_available"], bool)


def test_tell_browser_defaults_to_offline(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("FIELDKIT_TELL_SAPLING_KEY", "configured")
    offline_values: list[bool] = []

    def fake_detectors(_source: str, **kwargs: object) -> list[object]:
        offline_values.append(bool(kwargs["offline"]))
        return []

    monkeypatch.setattr(tell_routes, "run_detectors", fake_detectors)

    response = client.post("/api/tell/check", data={"text": "A local draft."})

    assert response.status_code == 200
    assert offline_values == [True]


def test_tell_remote_check_requires_single_use_payload_and_session_bound_intent(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_tell_keys(monkeypatch)
    monkeypatch.setenv("FIELDKIT_TELL_SAPLING_KEY", "configured")
    source = "A field note with enough text for the configured checker."
    calls: list[str] = []

    def fake_detectors(text: str, **_kwargs: object) -> list[object]:
        calls.append(text)
        return []

    monkeypatch.setattr(tell_routes, "run_detectors", fake_detectors)

    direct = client.post(
        "/api/tell/check",
        data={"text": source, "offline": "false"},
    )
    intent = client.post("/api/tell/egress-intent", data={"text": source})

    assert direct.status_code == 403
    assert intent.status_code == 200
    assert intent.json()["adapters"] == [{"name": "sapling", "display_name": "Sapling"}]
    assert intent.json()["token"]
    assert "HttpOnly" in intent.headers["set-cookie"]
    assert "SameSite=strict" in intent.headers["set-cookie"]
    token = intent.json()["token"]

    wrong_payload = client.post(
        "/api/tell/check",
        data={"text": f"{source} changed", "offline": "false", "egress_token": token},
    )
    with TestClient(
        client.app,
        base_url="http://localhost",
        headers={"Origin": "http://localhost"},
    ) as other_session:
        wrong_session = other_session.post(
            "/api/tell/check",
            data={"text": source, "offline": "false", "egress_token": token},
        )
    monkeypatch.setenv("FIELDKIT_TELL_ZEROGPT_KEY", "newly-configured")
    wrong_vendor_set = client.post(
        "/api/tell/check",
        data={"text": source, "offline": "false", "egress_token": token},
    )
    monkeypatch.delenv("FIELDKIT_TELL_ZEROGPT_KEY")
    allowed = client.post(
        "/api/tell/check",
        data={"text": source, "offline": "false", "egress_token": token},
    )
    replay = client.post(
        "/api/tell/check",
        data={"text": source, "offline": "false", "egress_token": token},
    )

    assert wrong_payload.status_code == 403
    assert wrong_session.status_code == 403
    assert wrong_vendor_set.status_code == 403
    assert allowed.status_code == 200
    assert replay.status_code == 403
    assert calls == [source]


def test_tell_browser_requires_native_per_send_confirmation(client: TestClient) -> None:
    html = client.get("/tell/").text
    script = client.get("/tell/app.js").text

    assert 'id="offline" checked' in html
    assert 'api("/api/tell/egress-intent"' in script
    assert "window.confirm" in script
    assert 'form.append("egress_token", intent.token)' in script


def test_tell_check_defaults_every_remote_row_to_offline(
    client: TestClient,
    fixture_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_tell_keys(monkeypatch)
    source = (fixture_dir / "slop_sample.md").read_text(encoding="utf-8")

    response = client.post("/api/tell/check", data={"text": source})

    assert response.status_code == 200
    payload = response.json()
    assert [item["adapter"] for item in payload["detectors"]] == [
        adapter.name for adapter in ADAPTERS
    ]
    assert all(item["status"] == "skipped" for item in payload["detectors"])
    assert all(item["detail"] == "offline mode" for item in payload["detectors"])
    assert len(payload["signals"]) == 10
    assert "aggregate" not in payload


def test_tell_check_html_contains_honesty_and_every_evidence_row(
    client: TestClient,
    fixture_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _clear_tell_keys(monkeypatch)
    source = (fixture_dir / "slop_sample.md").read_text(encoding="utf-8")

    response = client.post("/api/tell/check?output=html", data={"text": source})

    assert response.status_code == 200
    html = response.json()["html"]
    assert "<html" in html
    assert "Local signal scores are tell-density, not P(AI)" in html
    assert "Historical prose and non-native writers" in html
    assert all(adapter.display_name in html for adapter in ADAPTERS)
    assert all(signal["title"] in html for signal in response.json()["signals"])


def test_tell_unslop_returns_diff_and_text_file(client: TestClient, fixture_dir: Path) -> None:
    source = (fixture_dir / "slop_sample.md").read_text(encoding="utf-8")

    response = client.post(
        "/api/tell/unslop",
        data={"text": source, "max_iterations": "2"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["diff"]
    assert payload["final"] != source
    assert payload["file"]["filename"] == "unslopped_text.txt"
    decoded = base64.b64decode(payload["file"]["content_b64"]).decode("utf-8")
    assert decoded == payload["final"]
    assert len(payload["iterations"]) <= 2


def test_tell_text_xor_file_validation(client: TestClient) -> None:
    both = client.post(
        "/api/tell/check",
        data={"text": "pasted"},
        files={"file": ("draft.md", b"uploaded")},
    )
    neither = client.post("/api/tell/unslop")
    unsupported = client.post(
        "/api/tell/check",
        files={"file": ("draft.rtf", b"plain enough")},
    )
    valid_upload = client.post(
        "/api/tell/unslop",
        files={"file": ("../draft.md", b"We utilize this plan.")},
    )

    assert both.status_code == 422
    assert both.json() == {"error": "provide exactly one of text or file"}
    assert neither.status_code == 422
    assert neither.json() == {"error": "provide exactly one of text or file"}
    assert unsupported.status_code == 422
    assert unsupported.json() == {"error": "tell uploads must be .txt or .md"}
    assert valid_upload.status_code == 200
    assert valid_upload.json()["file"]["filename"] == "unslopped_draft.txt"


def test_tell_cli_writes_html_without_remote_calls(
    fixture_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_tell_keys(monkeypatch)
    output = tmp_path / "tell.html"

    result = CliRunner().invoke(
        cli_app,
        [
            "tell",
            "check",
            str(fixture_dir / "slop_sample.md"),
            "--html",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output.is_file()
    assert "Remote classifier scores" in output.read_text(encoding="utf-8")


def test_tell_html_can_include_unslop_provenance(fixture_dir: Path) -> None:
    source = (fixture_dir / "slop_sample.md").read_text(encoding="utf-8")
    report = analyze(source)
    rewrite = unslop(source)

    html = render_html(
        report,
        run_detectors(source, offline=True),
        rewrite=rewrite,
    )

    assert "Deterministic un-slop rewrite" in html
    assert "Word diff" in html
    assert "Suggestions requiring judgment" in html
    assert rewrite.final.splitlines()[0] in html


def _clear_tell_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    for adapter in ADAPTERS:
        for env_var in adapter.env_vars:
            monkeypatch.delenv(env_var, raising=False)
