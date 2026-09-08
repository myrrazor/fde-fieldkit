from pathlib import Path

import typer
from rich.console import Console

from fieldkit.core.io import load_table
from fieldkit_datadiff.diff import diff_tables, to_json
from fieldkit_datadiff.render import render_html, render_terminal

app = typer.Typer(
    help="Schema-aware diff of two data dumps",
    context_settings={"allow_interspersed_args": True},
)


@app.callback(invoke_without_command=True)
def main(
    old: Path = typer.Argument(..., dir_okay=False, help="Original data dump."),
    new: Path = typer.Argument(..., dir_okay=False, help="New data dump."),
    key: str | None = typer.Option(
        None, "--key", metavar="COL[,COL]", help="Comma-separated row key columns."
    ),
    json_path: Path | None = typer.Option(
        None, "--json", metavar="PATH", help="Also write the diff as JSON."
    ),
    html_path: Path | None = typer.Option(
        None, "--html", metavar="PATH", help="Also write a printable HTML report."
    ),
    include_values: bool = typer.Option(
        False,
        "--include-values",
        help="Include sensitive raw row/category values in this report.",
    ),
    sheet: str | None = typer.Option(None, "--sheet", help="Excel sheet to compare."),
) -> None:
    """Compare OLD and NEW and optionally save JSON and HTML reports."""

    for path in (old, new):
        if not path.is_file():
            typer.echo(f"error: file not found: {path}", err=True)
            raise typer.Exit(1)

    try:
        keys = _parse_key(key)
        result = diff_tables(
            load_table(old, sheet=sheet),
            load_table(new, sheet=sheet),
            keys=keys,
            include_values=include_values,
        )
        console = Console()
        render_terminal(result, console)
        if json_path is not None:
            json_path.write_text(to_json(result), encoding="utf-8")
            console.print("wrote", str(json_path))
        if html_path is not None:
            html_path.write_text(render_html(result), encoding="utf-8")
            console.print("wrote", str(html_path))
    except (OSError, UnicodeError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


def _parse_key(value: str | None) -> list[str] | None:
    if value is None:
        return None
    keys = [item.strip() for item in value.split(",") if item.strip()]
    if not keys:
        raise ValueError("--key needs at least one column")
    if len(set(keys)) != len(keys):
        raise ValueError("--key columns must not repeat")
    return keys
