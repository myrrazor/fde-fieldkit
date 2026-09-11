from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from fieldkit_awcp.check import check_spec
from fieldkit_awcp.diff import diff_workload_specs
from fieldkit_awcp.evals import EvalError, EvalSafetyMeasurementError, load_eval_suite, run_eval
from fieldkit_awcp.render import (
    check_to_json,
    diff_to_json,
    eval_to_json,
    render_check_html,
    render_check_terminal,
    render_diff_html,
    render_diff_terminal,
    render_eval_html,
    render_eval_terminal,
)
from fieldkit_awcp.spec import WorkloadSpecError, load_workload_spec

app = typer.Typer(
    name="awcp",
    help="Check AI workload specs, diff versions, and score golden eval suites locally",
    no_args_is_help=True,
)


@app.command("check")
def check_command(
    spec: Path = typer.Argument(..., dir_okay=False, help="WorkloadSpec YAML or JSON file."),
    json_path: Path | None = typer.Option(
        None, "--json", metavar="PATH", help="Also write the check as JSON."
    ),
    html_path: Path | None = typer.Option(
        None, "--html", metavar="PATH", help="Also write a printable HTML report."
    ),
) -> None:
    """Validate a workload spec, fingerprint it, and flag high-risk tools."""

    try:
        loaded = load_workload_spec(spec)
        result = check_spec(loaded, source=spec.name, base_dir=spec.parent)
    except (OSError, WorkloadSpecError, ValueError) as exc:
        _fail(exc)

    console = Console()
    render_check_terminal(result, console)
    _write_outputs(
        json_path,
        html_path,
        json_text=check_to_json(result),
        html_text=render_check_html(result),
        console=console,
    )
    if not result.ok:
        raise typer.Exit(1)


@app.command("diff")
def diff_command(
    before: Path = typer.Argument(..., dir_okay=False, help="Earlier WorkloadSpec."),
    after: Path = typer.Argument(..., dir_okay=False, help="Later WorkloadSpec."),
    json_path: Path | None = typer.Option(
        None, "--json", metavar="PATH", help="Also write the diff as JSON."
    ),
    html_path: Path | None = typer.Option(
        None, "--html", metavar="PATH", help="Also write a printable HTML report."
    ),
) -> None:
    """Show what changed between two workload specs."""

    try:
        left = load_workload_spec(before)
        right = load_workload_spec(after)
        changes = diff_workload_specs(left, right)
    except (OSError, WorkloadSpecError, ValueError) as exc:
        _fail(exc)

    console = Console()
    render_diff_terminal(changes, before=before.name, after=after.name, console=console)
    _write_outputs(
        json_path,
        html_path,
        json_text=diff_to_json(changes, before=before.name, after=after.name),
        html_text=render_diff_html(changes, before=before.name, after=after.name),
        console=console,
    )


@app.command("eval")
def eval_command(
    spec: Path = typer.Argument(..., dir_okay=False, help="WorkloadSpec YAML or JSON file."),
    suite: Path = typer.Option(
        ..., "--suite", dir_okay=False, help="Golden eval suite YAML or JSON file."
    ),
    artifact_dir: Path = typer.Option(
        Path(".awcp-artifacts"),
        "--artifact-dir",
        file_okay=False,
        help="Where the local result.json is written.",
    ),
    json_path: Path | None = typer.Option(
        None, "--json", metavar="PATH", help="Also write the eval run as JSON."
    ),
    html_path: Path | None = typer.Option(
        None, "--html", metavar="PATH", help="Also write a printable HTML report."
    ),
) -> None:
    """Score a recorded golden suite against the spec's gates. No model runs."""

    try:
        workload = load_workload_spec(spec)
        suite_payload = load_eval_suite(suite)
        run = run_eval(
            workload,
            suite_payload,
            artifact_dir=artifact_dir,
            source=spec.name,
        )
    except (OSError, WorkloadSpecError, EvalError, EvalSafetyMeasurementError, ValueError) as exc:
        _fail(exc)

    console = Console()
    render_eval_terminal(run, console)
    _write_outputs(
        json_path,
        html_path,
        json_text=eval_to_json(run),
        html_text=render_eval_html(run),
        console=console,
    )
    if run.status != "passed":
        raise typer.Exit(1)


def _write_outputs(
    json_path: Path | None,
    html_path: Path | None,
    *,
    json_text: str,
    html_text: str,
    console: Console,
) -> None:
    if json_path is not None:
        json_path.write_text(json_text + "\n", encoding="utf-8")
        console.print(f"wrote {json_path}")
    if html_path is not None:
        html_path.write_text(html_text, encoding="utf-8")
        console.print(f"wrote {html_path}")


def _fail(exc: Exception) -> None:
    typer.echo(f"error: {exc}", err=True)
    raise typer.Exit(1) from exc
