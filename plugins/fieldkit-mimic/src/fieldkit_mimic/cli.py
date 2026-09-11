from pathlib import Path

import typer

from fieldkit.core.io import SUPPORTED_FORMATS, load_table, write_table
from fieldkit_mimic.generate import generate
from fieldkit_mimic.learn import dump_spec, learn_spec, load_spec

_OUTPUT_FORMATS = {
    ".csv": "csv",
    ".tsv": "tsv",
    ".json": "json",
    ".jsonl": "jsonl",
    ".ndjson": "jsonl",
    ".xlsx": "xlsx",
}

app = typer.Typer(
    help="Learn a spec from sample data and generate synthetic rows",
)


@app.command("learn")
def learn_command(
    sample: Path = typer.Argument(..., dir_okay=False, help="Sample data file."),
    out: Path = typer.Option(..., "-o", "--output", metavar="PATH", help="YAML spec path."),
    fmt: str | None = typer.Option(
        None,
        "--fmt",
        help=f"Force sample table format ({', '.join(SUPPORTED_FORMATS)}).",
    ),
) -> None:
    """Learn a hand-editable YAML spec from SAMPLE."""

    if not sample.is_file():
        typer.echo(f"error: file not found: {sample}", err=True)
        raise typer.Exit(1)

    try:
        spec = learn_spec(load_table(sample, fmt=fmt), name=sample.stem)
        out.write_text(dump_spec(spec), encoding="utf-8")
        typer.echo(f"wrote {out}")
    except (OSError, UnicodeError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("generate")
def generate_command(
    source: Path = typer.Argument(..., dir_okay=False, help="YAML spec or sample data file."),
    rows: int = typer.Option(1000, "-n", "--rows", min=0, help="Rows to generate."),
    seed: int = typer.Option(0, "--seed", help="Random seed."),
    out: Path = typer.Option(..., "-o", "--output", metavar="PATH", help="Output data path."),
    fmt: str | None = typer.Option(
        None,
        "--fmt",
        help=f"Force sample table format when learning in one shot ({', '.join(SUPPORTED_FORMATS)}).",
    ),
) -> None:
    """Generate synthetic rows from a spec or directly from a sample."""

    if not source.is_file():
        typer.echo(f"error: file not found: {source}", err=True)
        raise typer.Exit(1)

    try:
        output_format = _OUTPUT_FORMATS.get(out.suffix.lower())
        if output_format is None:
            choices = ", ".join(sorted(_OUTPUT_FORMATS))
            raise ValueError(f"can't write {out.name!r}; choose an extension from: {choices}")

        if source.suffix.lower() in {".yaml", ".yml"}:
            if fmt is not None:
                raise ValueError("--fmt applies when the source is a sample table, not a YAML spec")
            spec = load_spec(source)
        else:
            spec = learn_spec(load_table(source, fmt=fmt), name=source.stem)
        frame = generate(spec, rows, seed=seed, fmt=output_format)
        write_table(frame, out, output_format)
        typer.echo(f"wrote {out} ({rows} rows)")
    except (OSError, UnicodeError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc
