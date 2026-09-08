from __future__ import annotations

import jinja2
from rich.console import Console
from rich.table import Table
from rich.text import Text

from fieldkit.core.report import jinja_env
from fieldkit_datadiff.diff import DiffResult


def render_terminal(result: DiffResult, console: Console) -> None:
    """Render schema, row, and drift changes to a Rich console."""

    console.print(
        Text.assemble(
            (result.source_a, "bold"),
            f" ({result.rows_a:,} rows) → ",
            (result.source_b, "bold"),
            f" ({result.rows_b:,} rows)",
        )
    )
    _render_schema(result, console)
    _render_rows(result, console)
    _render_drift(result, console)
    for warning in result.warnings:
        console.print(f"warning: {warning}", style="yellow")


def render_html(result: DiffResult) -> str:
    """Render a self-contained, printable HTML diff report."""

    env = jinja_env()
    env.loader = jinja2.ChoiceLoader([jinja2.PackageLoader("fieldkit_datadiff"), env.loader])
    return env.get_template("datadiff.html").render(
        title=f"datadiff · {result.source_a} → {result.source_b}", result=result
    )


def _render_schema(result: DiffResult, console: Console) -> None:
    table = Table(title="Schema")
    table.add_column("change")
    table.add_column("column", style="bold")
    table.add_column("old")
    table.add_column("new")
    for column in result.schema.added_columns:
        table.add_row(Text("added", style="green"), column, "—", "present")
    for column in result.schema.removed_columns:
        table.add_row(Text("removed", style="red"), column, "present", "—")
    for column, old, new in result.schema.type_changes:
        table.add_row("type", column, old, new)
    for column, old, new in result.schema.nullability_changes:
        table.add_row("nulls", column, f"{old:.1f}%", f"{new:.1f}%")
    if table.row_count == 0:
        table.add_row("none", "—", "—", "—")
    console.print(table)


def _render_rows(result: DiffResult, console: Console) -> None:
    if result.rows is None:
        console.print("Rows: skipped")
        return

    rows = result.rows
    counts = Table(title=f"Rows · key: {', '.join(rows.key_columns)}")
    counts.add_column("added", style="green", justify="right")
    counts.add_column("removed", style="red", justify="right")
    counts.add_column("changed", justify="right")
    counts.add_column("unchanged", justify="right")
    counts.add_row(
        f"{rows.added:,}",
        f"{rows.removed:,}",
        f"{rows.changed:,}",
        f"{rows.unchanged:,}",
    )
    console.print(counts)

    changed = Table(title="Changed by column")
    changed.add_column("column", style="bold")
    changed.add_column("cells", justify="right")
    for column, count in rows.changed_by_column.items():
        changed.add_row(column, f"{count:,}")
    if changed.row_count == 0:
        changed.add_row("—", "0")
    console.print(changed)


def _render_drift(result: DiffResult, console: Console) -> None:
    table = Table(title="Drift")
    table.add_column("column", style="bold")
    table.add_column("kind")
    table.add_column("details")
    for column, drift in result.drift.categorical.items():
        new = ", ".join(drift.new) or f"{drift.new_count} value(s)"
        vanished = ", ".join(drift.vanished) or f"{drift.vanished_count} value(s)"
        table.add_row(column, "categorical", f"new: {new}; vanished: {vanished}")
    for column, drift in result.drift.numeric.items():
        table.add_row(
            column,
            "numeric",
            (
                f"mean Δ {drift['mean_delta']:+.4g}; "
                f"std Δ {drift['std_delta']:+.4g}; "
                f"mean {drift['mean_pct_change']:+.2f}%"
            ),
        )
    if table.row_count == 0:
        table.add_row("—", "none", "—")
    console.print(table)
