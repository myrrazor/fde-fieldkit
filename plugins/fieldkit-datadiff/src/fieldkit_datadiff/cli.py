from pathlib import Path

import typer
from rich.console import Console

from fieldkit.cli import SingleCommandGroup
from fieldkit.core.io import (
    SUPPORTED_FORMATS,
    _clean_format,
    detect_format,
    load_table,
    require_regular_file,
)
from fieldkit_datadiff.diff import diff_tables, to_json
from fieldkit_datadiff.render import render_html, render_terminal

app = typer.Typer(
    cls=SingleCommandGroup,
    help="Schema-aware diff of two data dumps",
    context_settings={"allow_interspersed_args": True},
)


@app.callback(invoke_without_command=True)
def main(
    old: Path = typer.Argument(..., metavar="OLD", dir_okay=False, help="Original data dump."),
    new: Path = typer.Argument(..., metavar="NEW", dir_okay=False, help="New data dump."),
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
    fmt: str | None = typer.Option(
        None,
        "--fmt",
        help=f"Force table format for both files ({', '.join(SUPPORTED_FORMATS)}).",
    ),
) -> None:
    """Compare OLD and NEW and optionally save JSON and HTML reports."""

    for path in (old, new):
        try:
            require_regular_file(path)
        except ValueError as exc:
            typer.echo(f"error: {exc}", err=True)
            raise typer.Exit(1) from exc

    try:
        keys = _parse_key(key)
        old_sheet, new_sheet = _sheets_for(old, new, sheet, fmt)
        result = diff_tables(
            load_table(old, sheet=old_sheet, fmt=fmt),
            load_table(new, sheet=new_sheet, fmt=fmt),
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


def _format_of(path: Path, fmt: str | None) -> str:
    if fmt is not None:
        return _clean_format(fmt)
    with path.open("rb") as handle:
        sample = handle.read(4096)
    return detect_format(path.name, sample)


def _sheets_for(
    old: Path, new: Path, sheet: str | None, fmt: str | None
) -> tuple[str | None, str | None]:
    if sheet is None:
        return None, None
    old_fmt = _format_of(old, fmt)
    new_fmt = _format_of(new, fmt)
    if old_fmt != "xlsx" and new_fmt != "xlsx":
        raise ValueError(
            f"sheet {sheet!r} applies to Excel workbooks — "
            f"neither {old.name!r} ({old_fmt}) nor {new.name!r} ({new_fmt}) is Excel"
        )
    return (
        sheet if old_fmt == "xlsx" else None,
        sheet if new_fmt == "xlsx" else None,
    )


def _parse_key(value: str | None) -> list[str] | None:
    if value is None:
        return None
    keys = [item.strip() for item in value.split(",") if item.strip()]
    if not keys:
        raise ValueError("--key needs at least one column")
    if len(set(keys)) != len(keys):
        raise ValueError("--key columns must not repeat")
    return keys
