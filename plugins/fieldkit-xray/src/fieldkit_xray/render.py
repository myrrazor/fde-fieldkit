from __future__ import annotations

import jinja2
from rich.console import Console
from rich.table import Table
from rich.text import Text

from fieldkit.core.report import jinja_env
from fieldkit_xray.profile import ColumnProfile, ProfileResult


def render_terminal(result: ProfileResult, console: Console) -> None:
    """Render a compact profile summary to a Rich console."""

    summary = Text.assemble(
        (result.source, "bold"),
        f" · {result.fmt.upper()} · {result.row_count:,} × {result.column_count:,}",
    )
    console.print(summary)

    table = Table()
    table.add_column("column", style="bold")
    table.add_column("type")
    table.add_column("nulls %", justify="right")
    table.add_column("distinct", justify="right")
    table.add_column("top value")
    table.add_column("PII flags")
    for column in result.columns:
        table.add_row(
            column.name,
            column.inferred_type,
            f"{column.null_pct:.1f}%",
            f"{column.distinct_count:,} ({column.distinct_pct:.1f}%)",
            _top_value(column),
            _pii_flags(column),
        )
    console.print(table)


def render_html(result: ProfileResult) -> str:
    """Render a self-contained, printable HTML profile."""

    env = jinja_env()
    env.loader = jinja2.ChoiceLoader([jinja2.PackageLoader("fieldkit_xray"), env.loader])
    return env.get_template("xray.html").render(title=f"xray · {result.source}", result=result)


def _top_value(column: ColumnProfile) -> str:
    if not column.top_values:
        return "—"
    value, count = column.top_values[0]
    return f"{value} ({count:,})"


def _pii_flags(column: ColumnProfile) -> Text:
    flags = [(kind, confidence) for kind, confidence in column.pii.items() if kind != "hit_rate"]
    if not flags:
        return Text("—")

    rendered = Text()
    for index, (kind, confidence) in enumerate(flags):
        if index:
            rendered.append(", ")
        label = f"{kind.upper()} {confidence:.2f}"
        if confidence < 1:
            label = label.replace(" 0.", " .")
        rendered.append(label, style="red" if confidence >= 0.9 else None)
    return rendered
