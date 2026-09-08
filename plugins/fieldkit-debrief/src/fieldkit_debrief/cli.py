from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from fieldkit_debrief.report import build_report, render_html, render_markdown
from fieldkit_debrief.store import DEFAULT_DB, Store, Tag

app = typer.Typer(help="Log engagement notes and render weekly status reports")


@app.command("add")
def add_command(
    text: str = typer.Argument(..., help="Engagement note to log."),
    tag: Tag = typer.Option(..., "--tag", case_sensitive=False, help="Status category."),
    db: Path = typer.Option(DEFAULT_DB, "--db", dir_okay=False, help="Debrief database."),
) -> None:
    """Add a timestamped entry to the engagement log."""

    try:
        entry = Store(db).add(text, tag)
    except (OSError, sqlite3.Error, ValueError) as exc:
        _fail(exc)
    typer.echo(f"{entry.id} {entry.tag.value}")


@app.command("list")
def list_command(
    week: str | None = typer.Option(None, "--week", metavar="YYYY-WNN", help="ISO week."),
    tag: Tag | None = typer.Option(
        None, "--tag", case_sensitive=False, help="Only show one status category."
    ),
    db: Path = typer.Option(DEFAULT_DB, "--db", dir_okay=False, help="Debrief database."),
) -> None:
    """List logged entries, optionally filtered by ISO week or tag."""

    try:
        entries = Store(db).list(week=week, tag=tag)
    except (OSError, sqlite3.Error, ValueError) as exc:
        _fail(exc)

    table = Table()
    table.add_column("id", justify="right")
    table.add_column("ts")
    table.add_column("tag")
    table.add_column("text")
    for entry in entries:
        table.add_row(str(entry.id), entry.ts, entry.tag.value, entry.text)
    Console().print(table)


@app.command("report")
def report_command(
    week: str | None = typer.Option(None, "--week", metavar="YYYY-WNN", help="ISO week."),
    output: Path | None = typer.Option(
        None, "-o", "--output", dir_okay=False, metavar="PATH", help="Markdown output path."
    ),
    html: Path | None = typer.Option(
        None, "--html", dir_okay=False, metavar="PATH", help="HTML output path."
    ),
    db: Path = typer.Option(DEFAULT_DB, "--db", dir_okay=False, help="Debrief database."),
) -> None:
    """Render a stakeholder-ready report for an ISO week."""

    selected_week = week or _current_week()
    try:
        report = build_report(Store(db).list(week=selected_week), selected_week)
        markdown = render_markdown(report)
        if output is not None:
            output.write_text(markdown, encoding="utf-8")
            typer.echo(f"wrote {output}")
        if html is not None:
            html.write_text(render_html(report), encoding="utf-8")
            typer.echo(f"wrote {html}")
        if output is None and html is None:
            typer.echo(markdown, nl=False)
    except (OSError, sqlite3.Error, UnicodeError, ValueError) as exc:
        _fail(exc)


@app.command("delete")
def delete_command(
    entry_id: int = typer.Argument(..., help="Entry id to delete."),
    db: Path = typer.Option(DEFAULT_DB, "--db", dir_okay=False, help="Debrief database."),
) -> None:
    """Delete one entry by id."""

    try:
        deleted = Store(db).delete(entry_id)
    except (OSError, sqlite3.Error) as exc:
        _fail(exc)
    if not deleted:
        typer.echo(f"no entry {entry_id}", err=True)
        raise typer.Exit(1)
    typer.echo("deleted")


def _current_week() -> str:
    iso = datetime.now().isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _fail(exc: Exception) -> None:
    typer.echo(f"error: {exc}", err=True)
    raise typer.Exit(1) from exc
