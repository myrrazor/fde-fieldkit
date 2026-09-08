from __future__ import annotations

import stat
from pathlib import Path

from fieldkit_netwatch.models import EventDecision, Mode
from fieldkit_netwatch.store import Store


def test_session_commands_are_redacted_and_database_is_private(tmp_path: Path) -> None:
    db = tmp_path / "nested" / "events.db"
    store = Store(db)
    session = store.create_session(
        mode=Mode.AUDIT,
        agent="generic",
        command=["agent", "--api-key", "do-not-store", "--token=also-no"],
        coverage=("environment proxy",),
    )

    assert session.command == ("agent", "[arguments redacted]")
    assert stat.S_IMODE(db.stat().st_mode) == 0o600
    assert b"do-not-store" not in db.read_bytes()


def test_report_groups_events_and_keeps_sanitized_paths(store: Store, session_id: str) -> None:
    first = store.begin_network_event(
        session_id=session_id,
        source="http-forward",
        protocol="http",
        method="GET",
        host="api.openai.com",
        port=80,
        path="/v1/models",
        resolved_ip="8.8.8.8",
        scope="public",
        service="OpenAI API",
        decision=EventDecision.ALLOWED,
        rule_id="openai",
    )
    store.finish_network_event(first, bytes_sent=20, bytes_received=40)
    second = store.begin_network_event(
        session_id=session_id,
        source="http-forward",
        protocol="http",
        method="POST",
        host="api.openai.com",
        port=80,
        path="/v1/responses",
        resolved_ip="8.8.8.8",
        scope="public",
        service="OpenAI API",
        decision=EventDecision.WOULD_BLOCK,
        rule_id="deny-api",
    )
    store.finish_network_event(second, bytes_sent=3, bytes_received=4)
    store.add_tool_event(
        session_id=session_id,
        event="PreToolUse",
        tool="WebFetch",
        target="https://example.com/",
        correlation_id="tool-1",
    )

    report = store.report(session_id)
    assert report.totals == {
        "events": 2,
        "allowed": 1,
        "observed": 0,
        "blocked": 0,
        "would_block": 1,
        "failed": 0,
        "unsupported": 0,
        "public": 2,
        "local_private": 0,
        "services": 1,
        "tool_events": 1,
        "bytes_sent": 23,
        "bytes_received": 44,
    }
    assert len(report.destinations) == 1
    assert report.destinations[0].events == 2
    assert report.destinations[0].paths == {"/v1/models", "/v1/responses"}


def test_attach_observations_deduplicate_by_fingerprint(store: Store, session_id: str) -> None:
    kwargs = {
        "session_id": session_id,
        "fingerprint": "12|127.0.0.1:5000|1.1.1.1:443",
        "host": "1.1.1.1",
        "port": 443,
        "scope": "public",
        "service": "IP address",
        "process_pid": 12,
        "process_name": "agent",
        "detail": "socket sample",
    }
    assert store.record_observation(**kwargs)
    assert not store.record_observation(**kwargs)
    report = store.report(session_id)
    assert report.totals["events"] == 1
    assert report.totals["observed"] == 1
    assert report.destinations[0].observed == 1
    assert report.destinations[0].allowed == 0


def test_overview_groups_agent_source_and_destination(store: Store, session_id: str) -> None:
    event_id = store.begin_network_event(
        session_id=session_id,
        source="http-connect",
        protocol="https",
        host="api.openai.com",
        port=443,
        resolved_ip="8.8.8.8",
        scope="public",
        service="OpenAI API",
        decision=EventDecision.BLOCKED,
        rule_id="deny-openai",
    )
    store.finish_network_event(event_id, bytes_sent=4, bytes_received=8)

    overview = store.overview()

    assert overview["totals"]["sessions"] == 1
    assert overview["totals"]["blocked"] == 1
    assert overview["agents"][0]["agent"] == "test"
    assert overview["sources"][0]["source"] == "http-connect"
    assert overview["destinations"][0]["agents"] == ["test"]
    assert overview["destinations"][0]["sources"] == ["http-connect"]


def test_report_keeps_unsupported_separate_from_failed(store: Store, session_id: str) -> None:
    unsupported = store.begin_network_event(
        session_id=session_id,
        source="socks5",
        protocol="tcp",
        host="unsupported.example",
        port=443,
        scope="public",
        service="unsupported.example",
        decision=EventDecision.UNSUPPORTED,
    )
    store.finish_network_event(unsupported)
    failed = store.begin_network_event(
        session_id=session_id,
        source="http-connect",
        protocol="https",
        host="failed.example",
        port=443,
        scope="public",
        service="failed.example",
        decision=EventDecision.FAILED,
    )
    store.finish_network_event(failed)

    report = store.report(session_id)
    overview = store.overview()

    assert report.totals["unsupported"] == 1
    assert report.totals["failed"] == 1
    by_host = {row.host: row for row in report.destinations}
    assert by_host["unsupported.example"].unsupported == 1
    assert by_host["unsupported.example"].failed == 0
    assert by_host["failed.example"].failed == 1
    by_overview_host = {row["host"]: row for row in overview["destinations"]}
    assert by_overview_host["unsupported.example"]["unsupported"] == 1
    assert by_overview_host["failed.example"]["failed"] == 1


def test_delete_session_requires_it_to_be_stopped(store: Store, session_id: str) -> None:
    try:
        store.delete_session(session_id)
    except ValueError as exc:
        assert str(exc) == "stop the session before deleting its evidence"
    else:
        raise AssertionError("running evidence should not be deleted")

    store.finish_session(session_id, status="complete")
    assert store.delete_session(session_id)
    assert store.get_session(session_id) is None
    assert not store.delete_session(session_id)


def test_unknown_report_raises_key_error(store: Store) -> None:
    try:
        store.report("missing")
    except KeyError as exc:
        assert exc.args == ("missing",)
    else:
        raise AssertionError("missing session should not produce a report")
