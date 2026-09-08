from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from fieldkit_tell.adapters import (
    ADAPTERS,
    active_remote_adapters,
    adapter_is_keyed,
    run_detectors,
)
from fieldkit_tell.render import (
    render_detectors,
    render_html,
    render_terminal,
    render_unslop,
    render_word_diff,
)
from fieldkit_tell.rewrite import unslop, word_diff
from fieldkit_tell.signals import analyze

app = typer.Typer(help="Inspect stylometric tells without inventing an overall verdict")


@app.command()
def check(
    file: str = typer.Argument(..., help="Text or Markdown file; use - for stdin."),
    remote: bool = typer.Option(
        False,
        "--remote",
        help="Send this run to eligible configured checkers after naming them.",
    ),
    ml: bool = typer.Option(
        False,
        "--ml",
        help="Run the optional local RoBERTa detector; first use downloads model weights.",
    ),
    timeout: float = typer.Option(
        20.0,
        "--timeout",
        min=0.1,
        max=120.0,
        help="Per-checker timeout in seconds.",
    ),
    json_path: Path | None = typer.Option(
        None, "--json", metavar="PATH", help="Also write the signal report as JSON."
    ),
    html_path: Path | None = typer.Option(
        None, "--html", metavar="PATH", help="Also write a printable HTML report."
    ),
) -> None:
    """Check text for local stylometric tells."""

    try:
        text = _read_text(file)
        report = analyze(text)
        active = active_remote_adapters(text, offline=not remote)
        if active:
            names = ", ".join(adapter.display_name for adapter in active)
            typer.echo(
                f"sending text to {len(active)} remote services: {names}",
                err=True,
            )
        detectors = run_detectors(
            text,
            offline=not remote,
            include_ml=ml,
            timeout=timeout,
        )
        console = Console()
        render_terminal(report, console)
        render_detectors(detectors, console)
        if json_path is not None:
            payload = asdict(report)
            payload["detectors"] = [asdict(result) for result in detectors]
            json_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            console.print("wrote", str(json_path))
        if html_path is not None:
            html_path.write_text(
                render_html(report, detectors),
                encoding="utf-8",
            )
            console.print("wrote", str(html_path))
    except (OSError, UnicodeError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


@app.command("adapters")
def list_adapters() -> None:
    """Show adapter credential status without making a network request."""

    table = Table(title="tell adapters")
    table.add_column("adapter", style="bold")
    table.add_column("environment variables")
    table.add_column("keyed")
    for adapter in ADAPTERS:
        table.add_row(
            adapter.display_name,
            ", ".join(adapter.env_vars),
            "yes" if adapter_is_keyed(adapter) else "no",
        )
    Console().print(table)


@app.command("unslop")
def unslop_command(
    file: str = typer.Argument(..., help="Text or Markdown file; use - for stdin."),
    out: Path | None = typer.Option(
        None, "-o", "--output", metavar="PATH", help="Required cleaned output path."
    ),
    max_iterations: int = typer.Option(
        3,
        "--max-iterations",
        min=1,
        max=10,
        help="Maximum deterministic rewrite passes.",
    ),
    show_diff: bool = typer.Option(False, "--diff", help="Show a word-level terminal diff."),
    json_path: Path | None = typer.Option(
        None, "--json", metavar="PATH", help="Also write rewrite provenance as JSON."
    ),
) -> None:
    """Remove deterministic slop patterns and flag judgment calls."""

    if out is None:
        typer.echo("error: -o/--output is required; unslop never overwrites in place", err=True)
        raise typer.Exit(1)
    if file != "-" and Path(file).resolve() == out.resolve():
        typer.echo("error: input and output must be different files", err=True)
        raise typer.Exit(1)

    try:
        text = _read_text(file)
        result = unslop(text, max_iterations=max_iterations)
        operations = word_diff(result.original, result.final)
        out.write_text(result.final, encoding="utf-8")
        console = Console()
        render_unslop(result, console)
        if show_diff:
            render_word_diff(operations, console)
        console.print("wrote", str(out))
        if json_path is not None:
            payload = asdict(result)
            payload["diff"] = [asdict(operation) for operation in operations]
            json_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            console.print("wrote", str(json_path))
    except (OSError, UnicodeError, ValueError) as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from exc


def _read_text(file: str) -> str:
    if file == "-":
        return typer.get_text_stream("stdin").read()
    path = Path(file)
    if not path.is_file():
        raise ValueError(f"file not found: {path}")
    return path.read_text(encoding="utf-8")
