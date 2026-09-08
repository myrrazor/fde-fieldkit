from __future__ import annotations

import jinja2
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from fieldkit.core.report import jinja_env
from fieldkit_tell.adapters import AdapterStatus, DetectorResult
from fieldkit_tell.rewrite import DiffOp, UnslopResult, word_diff
from fieldkit_tell.signals import Severity, SignalReport, SignalResult, analyze

HONESTY_CAVEAT = (
    "Stylometric tells are patterns overrepresented in machine text, but they also appear "
    "in human writing. Historical prose and non-native writers can trigger them."
)

_SEVERITY_STYLE = {
    Severity.INFO: "dim",
    Severity.NOTICE: "yellow",
    Severity.STRONG: "red",
}


def render_terminal(report: SignalReport, console: Console) -> None:
    """Render local signals without collapsing them into an overall verdict."""

    stats = report.text_stats
    console.print(
        Text.assemble(
            (f"{stats.words:,}", "bold"),
            " words · ",
            (f"{stats.sentences:,}", "bold"),
            " sentences · ",
            (f"{stats.paragraphs:,}", "bold"),
            " paragraphs · mean sentence ",
            (f"{stats.mean_sentence_len:.1f}", "bold"),
            " words",
        )
    )
    console.print(Text(HONESTY_CAVEAT, style="italic"))
    console.print()
    for signal in report.signals:
        console.print(_signal_panel(signal))


def render_detectors(results: list[DetectorResult], console: Console) -> None:
    """Render remote classifier rows separately from local stylometric signals."""

    console.rule("Remote classifier scores")
    console.print(
        "Vendor probabilities are a separate evidence class. They are not combined "
        "with local stylometric tells.",
        style="italic",
    )
    table = Table()
    table.add_column("checker", style="bold")
    table.add_column("status")
    table.add_column("AI probability", justify="right")
    table.add_column("vendor label")
    table.add_column("detail")
    table.add_column("latency", justify="right")
    for result in results:
        style = {
            AdapterStatus.RAN: "green",
            AdapterStatus.SKIPPED: "dim",
            AdapterStatus.ERROR: "red",
        }[result.status]
        probability = (
            f"{result.ai_probability:.1%}" if result.ai_probability is not None else "—"
        )
        table.add_row(
            result.display_name,
            Text(result.status.value, style=style),
            probability,
            result.label or "—",
            result.detail or "—",
            f"{result.latency_ms:.0f} ms" if result.latency_ms else "—",
            style="dim" if result.status == AdapterStatus.SKIPPED else None,
        )
    console.print(table)


def render_unslop(result: UnslopResult, console: Console) -> None:
    """Render iteration provenance and judgment-only follow-up suggestions."""

    table = Table(title="Deterministic edits")
    table.add_column("iteration", justify="right")
    table.add_column("edits", justify="right")
    table.add_column("transforms")
    for iteration in result.iterations:
        transforms = ", ".join(dict.fromkeys(edit.transform for edit in iteration.edits))
        table.add_row(str(iteration.index), str(len(iteration.edits)), transforms)
    if not result.iterations:
        table.add_row("—", "0", "already stable")
    console.print(table)

    suggestions = Table(title="Suggestions requiring judgment")
    suggestions.add_column("pattern")
    suggestions.add_column("excerpt")
    suggestions.add_column("advice")
    for item in result.suggestions:
        suggestions.add_row(
            item.pattern,
            " ".join(item.excerpt.split())[:100],
            item.advice,
        )
    if not result.suggestions:
        suggestions.add_row("—", "—", "none")
    console.print(suggestions)


def render_word_diff(operations: list[DiffOp], console: Console) -> None:
    """Render a lossless word diff using insert and delete styling."""

    text = Text()
    for operation in operations:
        style = {
            "equal": None,
            "delete": "red strike",
            "insert": "green underline",
        }[operation.op]
        text.append(operation.text, style=style)
    console.print(Panel(text, title="Word diff", border_style="dim"))


def render_html(
    report: SignalReport,
    detectors: list[DetectorResult],
    *,
    rewrite: UnslopResult | None = None,
) -> str:
    """Render a self-contained report with local and remote evidence kept separate."""

    env = jinja_env()
    env.loader = jinja2.ChoiceLoader(
        [jinja2.PackageLoader("fieldkit_tell"), env.loader]
    )
    return env.get_template("tell.html").render(
        title="tell · writing evidence",
        report=report,
        detectors=detectors,
        rewrite=rewrite,
        diff=word_diff(rewrite.original, rewrite.final) if rewrite else [],
        iteration_deltas=_iteration_deltas(report, rewrite),
        honesty_caveat=HONESTY_CAVEAT,
    )


def _signal_panel(signal: SignalResult) -> Panel:
    style = _SEVERITY_STYLE[signal.severity]
    body = Text()
    body.append(signal.summary)
    if signal.stats:
        rendered_stats = " · ".join(f"{key}={value}" for key, value in signal.stats.items())
        body.append(f"\n{rendered_stats}", style="dim")
    for evidence in signal.evidence[:3]:
        excerpt = " ".join(evidence.excerpt.split())
        body.append(f"\n• {excerpt}", style="default")
        body.append(f" — {evidence.note}", style="dim")
    if len(signal.evidence) > 3:
        body.append(f"\n• {len(signal.evidence) - 3} more", style="dim")

    title = Text()
    title.append(signal.severity.value.upper(), style=f"bold {style}")
    title.append(f"  {signal.title}")
    title.append(f"  tell-density {signal.score:.2f}", style="dim")
    return Panel(body, title=title, border_style=style, padding=(0, 1))


def _iteration_deltas(
    initial: SignalReport, rewrite: UnslopResult | None
) -> list[dict[str, object]]:
    if rewrite is None:
        return []

    previous = initial
    rows: list[dict[str, object]] = []
    for iteration in rewrite.iterations:
        before = {signal.signal: signal.severity for signal in previous.signals}
        changes = [
            {
                "title": signal.title,
                "before": before[signal.signal].value,
                "after": signal.severity.value,
            }
            for signal in iteration.report.signals
            if before[signal.signal] != signal.severity
        ]
        rows.append(
            {
                "index": iteration.index,
                "edits": len(iteration.edits),
                "changes": changes,
            }
        )
        previous = iteration.report

    if not rewrite.iterations and rewrite.original != rewrite.final:
        # Defensive only: current unslop always records every applied pass.
        final_report = analyze(rewrite.final)
        rows.append(
            {
                "index": 1,
                "edits": 0,
                "changes": [
                    {
                        "title": signal.title,
                        "before": before_signal.severity.value,
                        "after": signal.severity.value,
                    }
                    for before_signal, signal in zip(
                        initial.signals, final_report.signals, strict=True
                    )
                    if before_signal.severity != signal.severity
                ],
            }
        )
    return rows
