from pathlib import Path

import typer
from rich.console import Console

from fieldkit.core.io import SUPPORTED_FORMATS, load_table
from fieldkit_xray.profile import profile_table, to_json
from fieldkit_xray.render import render_html, render_terminal

app = typer.Typer(
    help="Profile a data file: schema, types, nulls, stats, PII flags",
    context_settings={"allow_interspersed_args": True},
)


@app.callback(invoke_without_command=True)
def main(
    file: Path = typer.Argument(..., dir_okay=False, help="Data file to profile."),
    json_path: Path | None = typer.Option(
        None, "--json", metavar="PATH", help="Also write the profile as JSON."
    ),
    html_path: Path | None = typer.Option(
        None, "--html", metavar="PATH", help="Also write a printable HTML report."
    ),
    top_k: int = typer.Option(10, "--top-k", min=1, help="Top values kept per column."),
    include_values: bool = typer.Option(
        False,
        "--include-values",
        help="Include sensitive raw top/outlier values in this report.",
    ),
    sheet: str | None = typer.Option(None, "--sheet", help="Excel sheet to profile."),
    fmt: str | None = typer.Option(
        None,
        "--fmt",
        help=f"Force table format ({', '.join(SUPPORTED_FORMATS)}). Hard 50 MB dataset (MAX_DATASET_BYTES).",
    ),
) -> None:
    """Profile FILE and optionally save JSON and HTML reports."""

    if not file.is_file():
        typer.echo(f"error: file not found: {file}", err=True)
        raise typer.Exit(1)

    try:
        result = profile_table(
            load_table(file, sheet=sheet, fmt=fmt),
            top_k=top_k,
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
