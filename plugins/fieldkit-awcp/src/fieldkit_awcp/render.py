from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

import jinja2
from rich.console import Console
from rich.table import Table
from rich.text import Text

from fieldkit.core.report import jinja_env
from fieldkit_awcp.check import SpecCheck
from fieldkit_awcp.diff import WorkloadChange
from fieldkit_awcp.evals import EvalRun


def render_check_terminal(result: SpecCheck, console: Console) -> None:
    status = Text("ok", style="green") if result.ok else Text("failed", style="red")
    name = result.validation.workload_name or result.source
    project = result.validation.project or "—"
    console.print(Text.assemble((name, "bold"), " · ", project, " · ", status))
    console.print(f"config  {result.fingerprint.config_hash}")
    if result.fingerprint.prompt_hashes:
        modes = ", ".join(
            f"{name}={prompt.mode}" for name, prompt in result.fingerprint.prompt_hashes.items()
        )
        console.print(f"prompts {len(result.fingerprint.prompt_hashes)} ({modes})")

    if result.validation.errors:
        errors = Table(title="Errors")
        errors.add_column("error")
        for error in result.validation.errors:
            errors.add_row(error)
        console.print(errors)

    tools = Table(title="Tools")
    tools.add_column("name", style="bold")
    tools.add_column("approval")
    tools.add_column("risk")
    for tool in result.tools:
        tools.add_row(
            tool.name,
            "required" if tool.requires_approval else "none",
            ", ".join(tool.risk_tokens) or "—",
        )
    if result.denied_tools:
        tools.add_row("denied", "—", ", ".join(result.denied_tools))
    if tools.row_count:
        console.print(tools)

    for warning in result.warnings:
        console.print(f"warning: {warning}", style="yellow")
    if result.ok and not result.warnings:
        console.print("local check only — no model, control plane, or network call")


def render_diff_terminal(
    changes: list[WorkloadChange],
    *,
    before: str,
    after: str,
    console: Console,
) -> None:
    console.print(Text.assemble((before, "bold"), " → ", (after, "bold")))
    table = Table(title=f"Changes · {len(changes)}")
    table.add_column("kind", overflow="fold")
    table.add_column("path", style="bold", overflow="fold", no_wrap=False)
    table.add_column("before", overflow="fold")
    table.add_column("after", overflow="fold")
    if not changes:
        table.add_row("none", "—", "—", "—")
    for change in changes:
        table.add_row(
            change.category,
            change.path,
            _short(change.before),
            _short(change.after),
        )
    console.print(table)


def render_eval_terminal(run: EvalRun, console: Console) -> None:
    status = Text(run.status, style="green" if run.status == "passed" else "red")
    console.print(
        Text.assemble(
            (run.suite_name or run.eval_suite_id, "bold"),
            " · ",
            status,
            f" · {run.score:.2f} · {run.metrics.get('case_count', 0)} cases",
        )
    )
    metrics = Table(title="Gates")
    metrics.add_column("gate")
    metrics.add_column("value", justify="right")
    metrics.add_column("limit", justify="right")
    metrics.add_row(
        "overall",
        f"{run.metrics.get('overall_score', 0):.2f}",
        f"{run.metrics.get('min_overall_score', 0):.2f}",
    )
    metrics.add_row(
        "p95 ms",
        str(run.metrics.get("p95_latency_ms", "—")),
        _limit(run.metrics.get("max_p95_latency_ms")),
    )
    metrics.add_row(
        "pii leak",
        _rate(run.metrics.get("pii_leakage_rate")),
        _limit(run.metrics.get("max_pii_leakage_rate")),
    )
    metrics.add_row(
        "unsupported",
        _rate(run.metrics.get("unsupported_claim_rate")),
        _limit(run.metrics.get("max_unsupported_claim_rate")),
    )
    console.print(metrics)

    cases = Table(title="Cases")
    cases.add_column("id", style="bold")
    cases.add_column("score", justify="right")
    cases.add_column("pass")
    cases.add_column("reason")
    for result in run.results:
        cases.add_row(
            result.case_id,
            f"{result.score:.2f}",
            "yes" if result.passed else "no",
            result.reason,
        )
    console.print(cases)
    console.print("scored locally from recorded cases — no model ran")
    if run.artifact_uri:
        console.print(f"wrote {run.artifact_uri}")


def render_check_html(result: SpecCheck) -> str:
    return _template("awcp.html").render(
        title=f"awcp check · {result.source}",
        kind="check",
        check=result,
        changes=None,
        run=None,
        before="",
        after="",
    )


def render_diff_html(
    changes: list[WorkloadChange], *, before: str, after: str
) -> str:
    return _template("awcp.html").render(
        title=f"awcp diff · {before} → {after}",
        kind="diff",
        check=None,
        changes=changes,
        run=None,
        before=before,
        after=after,
    )


def render_eval_html(run: EvalRun) -> str:
    return _template("awcp.html").render(
        title=f"awcp eval · {run.suite_name or run.eval_suite_id}",
        kind="eval",
        check=None,
        changes=None,
        run=run,
        before="",
        after="",
    )


def check_to_json(result: SpecCheck) -> str:
    return json.dumps(
        {
            "ok": result.ok,
            "source": result.source,
            "workload_name": result.validation.workload_name,
            "project": result.validation.project,
            "errors": result.validation.errors,
            "warnings": list(result.warnings),
            "fingerprint": result.fingerprint.to_dict(),
            "tools": [asdict(tool) for tool in result.tools],
            "denied_tools": list(result.denied_tools),
        },
        indent=2,
        sort_keys=True,
    )


def diff_to_json(changes: list[WorkloadChange], *, before: str, after: str) -> str:
    return json.dumps(
        {
            "ok": True,
            "before": before,
            "after": after,
            "changes": [change.to_dict() for change in changes],
        },
        indent=2,
        sort_keys=True,
        default=str,
    )


def eval_to_json(run: EvalRun) -> str:
    payload = run.to_dict()
    payload["ok"] = run.status == "passed"
    payload["honesty"] = "scored locally from recorded cases; no model or promptfoo process ran"
    return json.dumps(payload, indent=2, sort_keys=True)


def _template(name: str) -> jinja2.Template:
    env = jinja_env()
    env.loader = jinja2.ChoiceLoader([jinja2.PackageLoader("fieldkit_awcp"), env.loader])
    return env.get_template(name)


def _short(value: Any) -> str:
    text = json.dumps(value, default=str) if isinstance(value, (dict, list)) else str(value)
    return text if len(text) <= 48 else text[:45] + "…"


def _limit(value: object) -> str:
    return "—" if value is None else str(value)


def _rate(value: object) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value):.3f}"
    except (TypeError, ValueError):
        return str(value)
