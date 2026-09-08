from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from typer.testing import CliRunner

from fieldkit.cli import app
from fieldkit_debrief import Entry, Store, Tag, build_report, render_html, render_markdown


def test_store_crud_round_trip(tmp_path: Path) -> None:
    db = tmp_path / "debrief.db"
    store = Store(db)
    first = store.add("Renewal is signed", Tag.WIN, datetime(2026, 7, 13, 9, 15))
    second = store.add("Waiting on security", Tag.BLOCKER, datetime(2026, 7, 13, 10, 30))

    assert store.list() == [first, second]
    assert store.list(tag=Tag.BLOCKER) == [second]
    assert store.delete(first.id) is True
    assert store.list() == [second]
    assert store.delete(first.id) is False
    assert store.delete(9999) is False
    assert db.stat().st_mode & 0o777 == 0o600


def test_store_restricts_existing_database_permissions(tmp_path: Path) -> None:
    db = tmp_path / "debrief.db"
    db.touch(mode=0o644)

    Store(db)

    assert db.stat().st_mode & 0o777 == 0o600


def test_week_filter_uses_iso_year_across_calendar_boundary(tmp_path: Path) -> None:
    store = Store(tmp_path / "debrief.db")
    monday = store.add("Monday", Tag.NOTE, datetime(2014, 12, 29, 8))
    sunday = store.add("Sunday", Tag.NEXT, datetime(2015, 1, 4, 18))
    following_monday = store.add("Next week", Tag.WIN, datetime(2015, 1, 5, 8))

    assert store.list(week="2015-W01") == [monday, sunday]
    assert store.list(week="2015-W02") == [following_monday]


def test_build_report_routes_every_tag_and_keeps_empty_sections() -> None:
    entries = [
        Entry(5, "2026-07-17T10:00:00", Tag.NEXT, "Send the rollout plan"),
        Entry(4, "2026-07-16T10:00:00", Tag.BLOCKER, "Need legal review"),
        Entry(3, "2026-07-15T10:00:00", Tag.NOTE, "Pilot configuration underway"),
        Entry(2, "2026-07-14T10:00:00", Tag.DECISION, "Launch with SSO"),
        Entry(1, "2026-07-13T10:00:00", Tag.WIN, "Pilot approved"),
    ]

    report = build_report(entries, "2026-W29")

    assert report.date_range == "Jul 13 – Jul 19, 2026"
    assert [heading for heading, _ in report.sections] == [
        "Wins",
        "Decisions",
        "In Progress",
        "Blockers & Asks",
        "Next Steps",
    ]
    assert [section_entries[0].tag for _, section_entries in report.sections] == [
        Tag.WIN,
        Tag.DECISION,
        Tag.NOTE,
        Tag.BLOCKER,
        Tag.NEXT,
    ]

    empty = build_report([], "2026-W29")
    assert all(section_entries == [] for _, section_entries in empty.sections)
    assert render_markdown(empty).count("Nothing logged.") == 5


def test_render_markdown_is_byte_stable_and_complete() -> None:
    report = build_report(
        [
            Entry(2, "2026-07-14T11:00:00", Tag.WIN, "Expanded to finance"),
            Entry(1, "2026-07-13T09:00:00", Tag.WIN, "Pilot approved"),
        ],
        "2026-W29",
        title="Acme Weekly Status",
    )

    first = render_markdown(report)
    second = render_markdown(report)

    assert first.encode() == second.encode()
    assert first.index("Pilot approved") < first.index("Expanded to finance")
    assert all(
        f"## {heading}" in first
        for heading in ("Wins", "Decisions", "In Progress", "Blockers & Asks", "Next Steps")
    )


def test_render_html_extends_base_and_escapes_entry_text() -> None:
    report = build_report(
        [Entry(1, "2026-07-13T09:00:00", Tag.WIN, "Usage < target & rising")],
        "2026-W29",
    )

    html = render_html(report)

    assert html.startswith("<!doctype html>")
    assert "Usage &lt; target &amp; rising" in html
    assert all(f">{escape(heading)}<" in html for heading, _ in report.sections)


def test_cli_add_list_filter_report_and_delete(tmp_path: Path) -> None:
    runner = CliRunner()
    db = tmp_path / "debrief.db"
    base = ["--db", str(db)]

    added = runner.invoke(app, ["debrief", "add", "Pilot approved", "--tag", "win", *base])
    assert added.exit_code == 0, added.output
    assert "1 win" in added.output

    runner.invoke(app, ["debrief", "add", "Need security signoff", "--tag", "blocker", *base])
    listed = runner.invoke(app, ["debrief", "list", *base])
    assert listed.exit_code == 0, listed.output
    assert "Pilot approved" in listed.output
    assert "Need security signoff" in listed.output

    filtered = runner.invoke(app, ["debrief", "list", "--tag", "win", *base])
    assert filtered.exit_code == 0, filtered.output
    assert "Pilot approved" in filtered.output
    assert "Need security signoff" not in filtered.output

    first_entry = Store(db).list()[0]
    week = datetime.fromisoformat(first_entry.ts).isocalendar()
    current_week = f"{week.year}-W{week.week:02d}"
    stdout_report = runner.invoke(app, ["debrief", "report", "--week", current_week, *base])
    assert stdout_report.exit_code == 0, stdout_report.output
    assert "Pilot approved" in stdout_report.output

    markdown_path = tmp_path / "status.md"
    html_path = tmp_path / "status.html"
    rendered = runner.invoke(
        app,
        [
            "debrief",
            "report",
            "--week",
            current_week,
            "-o",
            str(markdown_path),
            "--html",
            str(html_path),
            *base,
        ],
    )
    assert rendered.exit_code == 0, rendered.output
    assert "Pilot approved" in markdown_path.read_text(encoding="utf-8")
    assert "Pilot approved" in html_path.read_text(encoding="utf-8")

    deleted = runner.invoke(app, ["debrief", "delete", "1", *base])
    assert deleted.exit_code == 0
    assert deleted.output.strip() == "deleted"
    missing = runner.invoke(app, ["debrief", "delete", "1", *base])
    assert missing.exit_code == 1
    assert "no entry 1" in missing.output
