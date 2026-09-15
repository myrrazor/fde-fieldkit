from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from fieldkit.web import create_app
from fieldkit_netwatch.models import EventDecision, Mode
from fieldkit_netwatch.store import Store


def _local_client(app=None, *, client=("127.0.0.1", 50000)) -> TestClient:  # type: ignore[no-untyped-def]
    # the hub only answers loopback hosts and same-origin mutations, so every
    # test presents as a browser on 127.0.0.1 rather than httpx's testserver
    return TestClient(
        app or create_app(),
        base_url="http://localhost",
        client=client,
        headers={"Origin": "http://localhost"},
    )


def test_netwatch_web_routes_return_sessions_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "web.db"
    monkeypatch.setenv("FIELDKIT_NETWATCH_DB", str(db))
    monkeypatch.setattr("fieldkit_netwatch.web.discover_agents", lambda: [])
    store = Store(db)
    session = store.create_session(
        mode=Mode.ENFORCE,
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
    store.finish_network_event(event_id, bytes_sent=4, bytes_received=8)

    with _local_client() as client:
        status = client.get("/api/netwatch/status")
        control = client.get("/api/netwatch/control")
        overview = client.get("/api/netwatch/overview")
        agents = client.get("/api/netwatch/agents")
        sessions = client.get("/api/netwatch/sessions")
        report = client.get(f"/api/netwatch/sessions/{session.id}")
        json_export = client.get(f"/api/netwatch/sessions/{session.id}/export.json")
        csv_export = client.get(f"/api/netwatch/sessions/{session.id}/export.csv")
        starter = client.get("/api/netwatch/policy/starter")
        policy = client.get("/api/netwatch/policy")
        page = client.get("/netwatch/")
        script = client.get("/netwatch/app.js")

    assert status.json()["storage"] == str(db)
    assert status.json()["control_available"]
    assert control.json()["token"]
    assert overview.json()["sources"][0]["source"] == "http-connect"
    assert isinstance(agents.json()["agents"], list)
    assert sessions.json()["storage"] == str(db)
    assert sessions.json()["sessions"][0]["id"] == session.id
    assert report.json()["destinations"][0]["service"] == "OpenAI API"
    assert report.json()["totals"]["bytes_received"] == 8
    assert json_export.headers["content-disposition"].endswith(f'netwatch-{session.id}.json"')
    assert csv_export.text.startswith("record_type,occurred_at,source")
    assert starter.json()["default"] == "deny"
    assert not policy.json()["saved"]
    assert page.status_code == 200
    assert "Coverage lane" in page.text
    assert "Allow what the agent needs" in page.text
    assert "data-control-action" in page.text
    assert "frame-ancestors \'none\'" in page.headers["content-security-policy"]
    assert "number(row.port)" not in script.text
    assert "number(agent.pid)" not in script.text
    assert 'data-use-pid="${attr(agent.pid)}"' in script.text
    assert "function attr(value)" in script.text
    assert script.text.count('$("#session-select").value = payload.session.id;\n    syncSessionUrl();') == 2


def test_netwatch_web_returns_404_for_unknown_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FIELDKIT_NETWATCH_DB", str(tmp_path / "web.db"))
    with _local_client() as client:
        response = client.get("/api/netwatch/sessions/missing")
    assert response.status_code == 404
    assert response.json()["detail"] == "no netwatch session 'missing'"


def test_netwatch_mutations_require_loopback_json_and_control_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FIELDKIT_NETWATCH_DB", str(tmp_path / "web.db"))
    starter = {"version": 1, "default": "deny", "rules": []}
    with _local_client() as client:
        token = client.get("/api/netwatch/control").json()["token"]
        missing = client.put("/api/netwatch/policy", json=starter)
        wrong_type = client.put(
            "/api/netwatch/policy",
            content="{}",
            headers={"X-Fieldkit-Control": token, "Content-Type": "text/plain"},
        )
        cross_origin = client.put(
            "/api/netwatch/policy",
            json=starter,
            headers={"X-Fieldkit-Control": token, "Origin": "https://attacker.example"},
        )
        remote_host = client.get("/api/netwatch/control", headers={"Host": "attacker.example"})
        with _local_client(client=("10.0.0.5", 50000)) as remote_client:
            remote_client_control = remote_client.get("/api/netwatch/control")
        invalid_import = client.post(
            "/api/netwatch/policy/validate",
            json={"version": 1, "default": "deny", "rules": [None]},
            headers={"X-Fieldkit-Control": token},
        )
        saved = client.put(
            "/api/netwatch/policy",
            json=starter,
            headers={"X-Fieldkit-Control": token, "Origin": "http://localhost"},
        )

    assert missing.status_code == 403
    assert wrong_type.status_code == 415
    assert cross_origin.status_code == 403
    assert remote_host.status_code == 400  # the hub refuses the host before netwatch sees it
    assert remote_client_control.status_code == 403
    assert invalid_import.status_code == 422
    assert saved.status_code == 200
    assert saved.json()["saved"]
    assert Path(saved.json()["path"]).parent == tmp_path


def test_netwatch_can_delete_stopped_evidence_with_local_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "web.db"
    monkeypatch.setenv("FIELDKIT_NETWATCH_DB", str(db))
    store = Store(db)
    session = store.create_session(
        mode=Mode.AUDIT,
        agent="generic",
        command=["agent"],
        coverage=("environment proxy",),
        status="complete",
    )
    with _local_client() as client:
        token = client.get("/api/netwatch/control").json()["token"]
        response = client.request(
            "DELETE",
            f"/api/netwatch/sessions/{session.id}",
            json={},
            headers={"X-Fieldkit-Control": token},
        )

    assert response.status_code == 200
    assert response.json() == {"deleted": session.id}
    assert store.get_session(session.id) is None


def test_netwatch_server_shutdown_stops_owned_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "shutdown.db"
    monkeypatch.setenv("FIELDKIT_NETWATCH_DB", str(db))
    monkeypatch.setattr("fieldkit_netwatch.control.shutil.which", lambda _name: "/usr/bin/lsof")
    monkeypatch.setattr("fieldkit_netwatch.control.record_snapshot", lambda *_args: 0)
    with _local_client() as client:
        token = client.get("/api/netwatch/control").json()["token"]
        started = client.post(
            "/api/netwatch/attachments",
            json={"pid": 12345, "follow": True, "interval": 0.1},
            headers={"X-Fieldkit-Control": token},
        )
        assert started.status_code == 202
        session_id = started.json()["session"]["id"]
        assert Store(db).get_session(session_id).status == "running"  # type: ignore[union-attr]

    assert Store(db).get_session(session_id).status == "interrupted"  # type: ignore[union-attr]


def test_invalid_managed_policy_can_be_repaired_from_the_dashboard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "repair.db"
    policy_path = tmp_path / "netwatch-policy.json"
    policy_path.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("FIELDKIT_NETWATCH_DB", str(db))

    with _local_client() as client:
        control = client.get("/api/netwatch/control")
        broken = client.get("/api/netwatch/policy")
        token = control.json()["token"]
        repaired = client.put(
            "/api/netwatch/policy",
            json={"version": 1, "default": "deny", "rules": []},
            headers={"X-Fieldkit-Control": token},
        )

    assert control.status_code == 200
    assert control.json()["policy_path"] == str(policy_path)
    assert broken.status_code == 422
    assert repaired.status_code == 200
    assert repaired.json()["saved"]


def test_control_planes_are_isolated_between_app_instances(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("fieldkit_netwatch.control.shutil.which", lambda _name: "/usr/bin/lsof")
    monkeypatch.setattr("fieldkit_netwatch.control.record_snapshot", lambda *_args: 0)
    db_a = tmp_path / "a.db"
    db_b = tmp_path / "b.db"
    client_a = _local_client()
    client_b = _local_client()
    a_open = False
    b_open = False
    try:
        monkeypatch.setenv("FIELDKIT_NETWATCH_DB", str(db_a))
        client_a.__enter__()
        a_open = True
        token_a = client_a.get("/api/netwatch/control").json()["token"]
        session_a = client_a.post(
            "/api/netwatch/attachments",
            json={"pid": 111, "follow": True, "interval": 0.1},
            headers={"X-Fieldkit-Control": token_a},
        ).json()["session"]["id"]

        monkeypatch.setenv("FIELDKIT_NETWATCH_DB", str(db_b))
        client_b.__enter__()
        b_open = True
        token_b = client_b.get("/api/netwatch/control").json()["token"]
        session_b = client_b.post(
            "/api/netwatch/attachments",
            json={"pid": 222, "follow": True, "interval": 0.1},
            headers={"X-Fieldkit-Control": token_b},
        ).json()["session"]["id"]

        client_a.__exit__(None, None, None)
        a_open = False
        assert Store(db_a).get_session(session_a).status == "interrupted"  # type: ignore[union-attr]
        assert Store(db_b).get_session(session_b).status == "running"  # type: ignore[union-attr]
        assert session_b in client_b.get("/api/netwatch/sessions").json()["owned_sessions"]
    finally:
        if a_open:
            client_a.__exit__(None, None, None)
        if b_open:
            client_b.__exit__(None, None, None)

    assert Store(db_b).get_session(session_b).status == "interrupted"  # type: ignore[union-attr]


def test_symlinked_database_keeps_policy_beside_configured_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    configured_dir = tmp_path / "configured"
    target_dir = tmp_path / "target"
    configured_dir.mkdir()
    target_dir.mkdir()
    configured_db = configured_dir / "events.db"
    configured_db.symlink_to(target_dir / "events.db")
    monkeypatch.setenv("FIELDKIT_NETWATCH_DB", str(configured_db))
    app = create_app()

    with _local_client(app) as client:
        token = client.get("/api/netwatch/control").json()["token"]
        client.get("/api/netwatch/sessions")
        saved = client.put(
            "/api/netwatch/policy",
            json={"version": 1, "default": "deny", "rules": []},
            headers={"X-Fieldkit-Control": token},
        )
        plane = next(iter(app.state.netwatch_control_planes.values()))

    assert saved.status_code == 200
    assert plane.db_path == configured_db
    assert Path(saved.json()["path"]) == configured_dir / "netwatch-policy.json"
    assert not (target_dir / "netwatch-policy.json").exists()
