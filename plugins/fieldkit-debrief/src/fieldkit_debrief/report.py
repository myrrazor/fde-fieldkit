from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

import jinja2

from fieldkit.core.report import jinja_env
from fieldkit_debrief.store import Entry, Tag

_SECTIONS = (
    ("Wins", Tag.WIN),
    ("Decisions", Tag.DECISION),
    ("In Progress", Tag.NOTE),
    ("Blockers & Asks", Tag.BLOCKER),
    ("Next Steps", Tag.NEXT),
)


@dataclass
class ReportData:
    """Presentation-ready weekly engagement summary."""

    title: str
    week: str
    date_range: str
    sections: list[tuple[str, list[Entry]]]


def build_report(
    entries: list[Entry], week: str, *, title: str = "Weekly Status"
) -> ReportData:
    """Route entries into fixed stakeholder report sections."""

    start = _week_start(week)
    end = start + timedelta(days=6)
    ordered = sorted(entries, key=lambda entry: (datetime.fromisoformat(entry.ts), entry.id))
    sections = [
        (heading, [entry for entry in ordered if entry.tag == tag])
        for heading, tag in _SECTIONS
    ]
    return ReportData(
        title=title,
        week=week,
        date_range=_format_date_range(start, end),
        sections=sections,
    )


def render_markdown(report: ReportData) -> str:
    """Render a deterministic Markdown status report."""

    rendered = _template_env().get_template("report.md.j2").render(report=report)
    return f"{rendered.rstrip()}\n"


def render_html(report: ReportData) -> str:
    """Render a self-contained, printable HTML status report."""

    env = _template_env()
    env.autoescape = True
    return env.get_template("report.html.j2").render(
        title=f"{report.title} · {report.week}", report=report
    )


def _template_env() -> jinja2.Environment:
    env = jinja_env()
    env.trim_blocks = True
    env.lstrip_blocks = True
    env.keep_trailing_newline = True
    env.loader = jinja2.ChoiceLoader(
        [jinja2.PackageLoader("fieldkit_debrief"), env.loader]
    )
    return env


def _week_start(week: str) -> date:
    try:
        year_text, week_text = week.split("-W")
        if len(year_text) != 4 or len(week_text) != 2:
            raise ValueError
        year, week_number = int(year_text), int(week_text)
        start = date.fromisocalendar(year, week_number, 1)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"invalid ISO week {week!r}; expected YYYY-WNN") from exc
    if f"{year:04d}-W{week_number:02d}" != week:
        raise ValueError(f"invalid ISO week {week!r}; expected YYYY-WNN")
    return start


def _format_date_range(start: date, end: date) -> str:
    start_label = f"{start:%b} {start.day}"
    end_label = f"{end:%b} {end.day}"
    if start.year == end.year:
        return f"{start_label} – {end_label}, {end.year}"
    return f"{start_label}, {start.year} – {end_label}, {end.year}"
