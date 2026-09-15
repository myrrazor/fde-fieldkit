from __future__ import annotations

import asyncio
import csv
import sqlite3
import stat
import sys
import threading
from io import StringIO
from pathlib import Path

import pytest

from fieldkit_netwatch.agents import AgentKind
from fieldkit_netwatch.control import (
    ControlPlane,
    check_policy_destination,
    load_policy_state,
    report_as_csv,
    save_policy_document,
)
from fieldkit_netwatch.models import EventDecision, Mode
from fieldkit_netwatch.store import Store


def test_managed_policy_starts_unsaved_then_writes_private_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FIELDKIT_NETWATCH_POLICY", raising=False)
    db = tmp_path / "netwatch.db"

    initial = load_policy_state(db)
    saved = save_policy_document(initial.policy.as_dict(), db)

    assert not initial.saved
    assert saved.saved
    assert saved.path == tmp_path / "netwatch-policy.json"
    assert stat.S_IMODE(saved.path.stat().st_mode) == 0o600
    assert load_policy_state(db).policy == initial.policy


def test_policy_check_explains_loopback_without_remote_enrichment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FIELDKIT_NETWATCH_POLICY", raising=False)
    save_policy_document(load_policy_state(tmp_path / "events.db").policy.as_dict(), tmp_path / "events.db")

    result = asyncio.run(
        check_policy_destination(
            "127.0.0.1:8765",
            protocol="tcp",
            mode=Mode.ENFORCE,
            db_path=tmp_path / "events.db",
        )
    )

    assert result["selected"]["outcome"] == "allowed"
    assert result["selected"]["rule_id"] == "local-addresses"
    assert result["selected"]["scope"] == "loopback"


def test_report_csv_labels_network_and_tool_rows(store: Store, session_id: str) -> None:
    event_id = store.begin_network_event(
        session_id=session_id,
        source="http-connect",
        protocol="https",
        host="api.openai.com",
        port=443,
        scope="public",
        service="OpenAI API",
        decision=EventDecision.ALLOWED,
    )
    store.finish_network_event(event_id, bytes_sent=2, bytes_received=3)
    store.add_tool_event(
        session_id=session_id,
        event="PreToolUse",
        tool="WebFetch",
        target="https://example.com/",
        correlation_id="tool-1",
    )

    rows = list(csv.DictReader(StringIO(report_as_csv(store.report(session_id)))))

    assert [row["record_type"] for row in rows] == ["network_event", "tool_event"]
    assert rows[0]["host"] == "api.openai.com"
    assert rows[1]["tool"] == "WebFetch"


def test_report_csv_neutralizes_spreadsheet_formula_cells(store: Store, session_id: str) -> None:
    event_id = store.begin_network_event(
        session_id=session_id,
        source="http-forward",
        protocol="http",
        host="=2+2",
        port=80,
        scope="public",
        service="+formula",
        decision=EventDecision.ALLOWED,
        process_name="@agent",
        detail=" -danger",
    )
    store.finish_network_event(event_id)
    store.add_tool_event(
        session_id=session_id,
        event="PreToolUse",
        tool="WebFetch",
        target="\tformula",
        correlation_id="-correlation",
    )

    rows = list(csv.DictReader(StringIO(report_as_csv(store.report(session_id)))))

    assert rows[0]["host"] == "'=2+2"
    assert rows[0]["service"] == "'+formula"
    assert rows[0]["process_name"] == "'@agent"
    assert rows[0]["detail"] == "' -danger"
    assert rows[1]["target"] == "'\tformula"
    assert rows[1]["correlation_id"] == "'-correlation"


def test_control_plane_starts_and_stops_owned_process_group(tmp_path: Path) -> None:
    db = tmp_path / "control.db"
    plane = ControlPlane(db)

    async def exercise() -> None:
        session = await plane.start_run(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            mode=Mode.AUDIT,
            agent=AgentKind.GENERIC,
            use_policy=False,
        )
        assert session.status == "running"
        assert session.id in plane.active_session_ids()
        stopped = await plane.stop(session.id)
        assert stopped.status == "interrupted"
        assert session.id not in plane.active_session_ids()

    asyncio.run(exercise())


def test_control_plane_attach_follow_is_owned_and_stoppable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("fieldkit_netwatch.control.shutil.which", lambda _name: "/usr/bin/lsof")
    monkeypatch.setattr("fieldkit_netwatch.control.record_snapshot", lambda *_args: 0)
    plane = ControlPlane(tmp_path / "attach.db")

    async def exercise() -> None:
        session = await plane.start_attach(123, follow=True, interval=0.1)
        assert session.id in plane.active_session_ids()
        stopped = await plane.stop(session.id)
        assert stopped.status == "interrupted"

    asyncio.run(exercise())


def test_control_plane_uses_audit_all_until_a_policy_is_saved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "audit.db"
    captured: dict[str, object] = {}

    async def fake_supervised(command: list[str], **kwargs: object) -> None:
        policy = kwargs["policy"]
        captured["policy"] = policy
        captured["policy_path"] = kwargs["policy_path"]
        store = Store(db)
        session = store.create_session(
            mode=Mode.AUDIT,
            agent="generic",
            command=command,
            coverage=("test",),
            status="running",
        )
        kwargs["on_ready"](session.id, None, None)  # type: ignore[operator]
        await asyncio.Event().wait()

    monkeypatch.setattr("fieldkit_netwatch.control.run_supervised", fake_supervised)
    plane = ControlPlane(db)

    async def exercise() -> None:
        session = await plane.start_run(
            ["agent"],
            mode=Mode.AUDIT,
            agent=AgentKind.GENERIC,
            use_policy=True,
        )
        policy = captured["policy"]
        assert policy.default.value == "allow"  # type: ignore[union-attr]
        assert policy.rules[0].id == "audit-all"  # type: ignore[union-attr]
        assert captured["policy_path"] is None
        await plane.stop(session.id)

    asyncio.run(exercise())


def test_control_plane_cancels_worker_if_launch_request_is_cancelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def waiting_supervisor(*_args: object, **_kwargs: object) -> None:
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr("fieldkit_netwatch.control.run_supervised", waiting_supervisor)
    plane = ControlPlane(tmp_path / "cancel.db")

    async def exercise() -> None:
        launch = asyncio.create_task(
            plane.start_run(
                ["agent"],
                mode=Mode.AUDIT,
                agent=AgentKind.GENERIC,
                use_policy=False,
            )
        )
        await entered.wait()
        launch.cancel()
        with pytest.raises(asyncio.CancelledError):
            await launch
        assert cancelled.is_set()
        assert not plane.active_session_ids()

    asyncio.run(exercise())


def test_one_shot_attach_waits_for_inflight_snapshot_before_stopping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    started = threading.Event()
    release = threading.Event()

    def slow_snapshot(store: Store, session_id: str, _pid: int) -> int:
        started.set()
        release.wait()
        store.record_observation(
            session_id=session_id,
            fingerprint="late-socket",
            host="127.0.0.1",
            port=443,
            scope="loopback",
            service="Localhost",
            process_pid=12345,
            process_name="agent",
            detail="test",
        )
        return 1

    monkeypatch.setattr("fieldkit_netwatch.control.shutil.which", lambda _name: "/usr/bin/lsof")
    monkeypatch.setattr("fieldkit_netwatch.control.record_snapshot", slow_snapshot)
    db = tmp_path / "one-shot.db"
    plane = ControlPlane(db)

    async def exercise() -> None:
        session = await plane.start_attach(12345, follow=False, interval=1)
        while not started.is_set():
            await asyncio.sleep(0)
        stopping = asyncio.create_task(plane.stop(session.id))
        await asyncio.sleep(0)
        assert not stopping.done()
        release.set()
        stopped = await stopping
        assert stopped.status == "interrupted"
        assert len(Store(db).list_network_events(session.id)) == 1
        await asyncio.sleep(0.01)
        assert len(Store(db).list_network_events(session.id)) == 1

    asyncio.run(exercise())


def test_attach_storage_failure_marks_session_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_snapshot(*_args: object) -> int:
        raise sqlite3.OperationalError("disk unavailable")

    monkeypatch.setattr("fieldkit_netwatch.control.shutil.which", lambda _name: "/usr/bin/lsof")
    monkeypatch.setattr("fieldkit_netwatch.control.record_snapshot", fail_snapshot)
    db = tmp_path / "failure.db"
    plane = ControlPlane(db)

    async def exercise() -> None:
        session = await plane.start_attach(12345, follow=False, interval=1)
        while session.id in plane.active_session_ids():
            await asyncio.sleep(0)
        failed = Store(db).get_session(session.id)
        assert failed is not None
        assert failed.status == "failed"
        assert failed.note == "attach failed (OperationalError)"

    asyncio.run(exercise())
