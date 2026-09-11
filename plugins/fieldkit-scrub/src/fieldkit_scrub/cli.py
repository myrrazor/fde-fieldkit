from __future__ import annotations

import json
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from fieldkit.core.io import SUPPORTED_FORMATS, load_table, write_table
from fieldkit.core.pii import PIIKind
from fieldkit.core.private_files import atomic_write_private
from fieldkit_scrub.engine import Scrubber, ScrubSummary
from fieldkit_scrub.salt import load_or_create_salt

_TABULAR_SUFFIXES = {".csv", ".tsv", ".xlsx", ".json", ".jsonl", ".ndjson"}

app = typer.Typer(
    help="Deterministically pseudonymize PII in a data file",
    context_settings={"allow_interspersed_args": True},
)


@app.callback(invoke_without_command=True)
def main(
    file: Path = typer.Argument(..., dir_okay=False, help="Data file to scrub."),
    out: Path | None = typer.Option(
        None, "-o", "--output", metavar="PATH", help="Required output path."
    ),
    kinds: str | None = typer.Option(
        None,
        "--kinds",
        metavar="LIST",
        help="Comma-separated kinds: email,phone,ssn,credit_card,ip,name,secret.",
    ),
    salt_file: Path | None = typer.Option(
        None, "--salt-file", metavar="PATH", help="Salt file for stable pseudonyms."
    ),
    mapping: Path | None = typer.Option(
        None, "--mapping", metavar="PATH", help="Write the sensitive original-to-fake map."
    ),
    text: bool = typer.Option(
        False,
        "--text",
        help="Use line mode. Exact bytes are matched; equivalent spellings are not normalized.",
    ),
    fmt: str | None = typer.Option(
        None,
        "--fmt",
        help=f"Force table format ({', '.join(SUPPORTED_FORMATS)}).",
    ),
) -> None:
    """Scrub FILE into a new output while preserving deterministic joins."""

    if out is None:
        typer.echo("error: -o/--output is required; scrub never overwrites in place", err=True)
        raise typer.Exit(1)
    if not file.is_file():
        typer.echo(f"error: file not found: {file}", err=True)
        raise typer.Exit(1)
    if file.resolve() == out.resolve():
        typer.echo("error: input and output must be different files", err=True)
        raise typer.Exit(1)

    try:
        selected_kinds = _parse_kinds(kinds)
        salt = load_or_create_salt(salt_file) if salt_file is not None else load_or_create_salt()
        scrubber = Scrubber(salt, kinds=selected_kinds)
        line_mode = text or file.suffix.lower() not in _TABULAR_SUFFIXES
        if line_mode:
            if fmt is not None:
                raise ValueError("--fmt applies to tabular scrub only; omit it with --text")
            output, summary = scrubber.scrub_text(file.read_text(encoding="utf-8"))
            out.write_text(output, encoding="utf-8")
        else:
            loaded = load_table(file, fmt=fmt)
            output, summary = scrubber.scrub_dataframe(loaded)
            write_table(output, out, loaded.fmt)

        if mapping is not None:
            typer.echo(
                "warning: the mapping file is as sensitive as the original data",
                err=True,
            )
            atomic_write_private(
                mapping,
                (json.dumps(scrubber.mapping, indent=2, sort_keys=True) + "\n").encode("utf-8"),
            )
        _render_summary(summary)
    except (OSError, UnicodeError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


def _parse_kinds(value: str | None) -> set[PIIKind]:
    if value is None:
        return set(PIIKind)
    try:
        return {PIIKind(item.strip()) for item in value.split(",") if item.strip()}
    except ValueError as exc:
        choices = ", ".join(kind.value for kind in PIIKind)
        raise ValueError(f"unknown PII kind; choose from: {choices}") from exc


def _render_summary(summary: ScrubSummary) -> None:
    console = Console()
    totals = Table(title="Replacements")
    totals.add_column("Kind")
    totals.add_column("Count", justify="right")
    for kind, count in summary.replaced.items():
        totals.add_row(kind, str(count))
    console.print(totals)

    if not summary.by_column:
        return
    columns = Table(title="By column")
    columns.add_column("Column")
    columns.add_column("Kind")
    columns.add_column("Count", justify="right")
    for column, counts in summary.by_column.items():
        for kind, count in counts.items():
            columns.add_row(column, kind, str(count))
    console.print(columns)
