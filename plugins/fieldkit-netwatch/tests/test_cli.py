from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fieldkit_netwatch import cli
from fieldkit_netwatch.cli import app
from fieldkit_netwatch.models import Mode
from fieldkit_netwatch.store import Store


runner = CliRunner()


def test_doctor_json_is_machine_readable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli,
        "capability_report",
        lambda: {
            "platform": {"system": "TestOS"},
            "capture": {
                "http_proxy": True,
                "socks5_tcp": True,
                "attach_snapshot": False,
                "tls_decryption": False,
                "udp_quic": False,
                "whole_machine_enforcement": False,
            },
            "agents": {"codex": {}, "claude": {}},
            "coverage_note": "test",
        },
    )
    result = runner.invoke(app, ["doctor", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["platform"] == {"system": "TestOS"}


def test_policy_cli_initializes_adds_and_checks_rules(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    initialized = runner.invoke(app, ["policy", "init", str(path)])
    added = runner.invoke(
        app,
        [
            "policy",
            "add",
            str(path),
            "--action",
            "allow",
            "--id",
            "service-api",
            "--host",
            "api.example.com",
            "--port",
            "443",
            "--protocol",
            "https",
        ],
    )
    allowed = runner.invoke(app, ["policy", "check", str(path), "https://localhost"])
    blocked = runner.invoke(app, ["policy", "check", str(path), "https://8.8.8.8"])

    assert initialized.exit_code == 0
    assert added.exit_code == 0
    payload = json.loads(path.read_text())
    assert payload["rules"][-1]["id"] == "service-api"
    assert allowed.exit_code == 0
    assert allowed.stdout.startswith("allowed:")
    assert blocked.exit_code == 3
    assert blocked.stdout.startswith("blocked:")


def test_enforce_run_requires_a_policy() -> None:
    result = runner.invoke(app, ["run", "--mode", "enforce", "--", sys.executable, "-c", "pass"])
    assert result.exit_code == 1
    assert "enforce mode needs --policy" in result.stderr


def test_run_sessions_and_report_commands_use_the_selected_database(tmp_path: Path) -> None:
    db = tmp_path / "cli.db"
    run = runner.invoke(
        app,
        ["run", "--db", str(db), "--agent", "generic", "--", sys.executable, "-c", "pass"],
    )
    assert run.exit_code == 0, run.output
    session_id = Store(db).list_sessions()[0].id

    sessions = runner.invoke(app, ["sessions", "--json", "--db", str(db)])
    report = runner.invoke(app, ["report", session_id, "--json", "--db", str(db)])
    assert sessions.exit_code == 0
    assert json.loads(sessions.stdout)["sessions"][0]["id"] == session_id
    assert report.exit_code == 0
    assert json.loads(report.stdout)["totals"]["events"] == 0


def test_sessions_table_handles_an_empty_database(tmp_path: Path) -> None:
    result = runner.invoke(app, ["sessions", "--db", str(tmp_path / "empty.db")])
    assert result.exit_code == 0
    assert "no sessions yet" in result.stdout


def test_attach_rejects_invalid_pid() -> None:
    result = runner.invoke(app, ["attach", "0"])
    assert result.exit_code == 2
    assert "pid must be positive" in result.stderr


def test_attach_fails_clearly_without_lsof(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(cli.shutil, "which", lambda _name: None)
    result = runner.invoke(app, ["attach", "1", "--db", str(tmp_path / "attach.db")])
    assert result.exit_code == 1
    assert "attach needs lsof" in result.stderr


def test_policy_for_run_allows_audit_without_file() -> None:
    assert cli._policy_for_run(Mode.AUDIT, None).default.value == "allow"

