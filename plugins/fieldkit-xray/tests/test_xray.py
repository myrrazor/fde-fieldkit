from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
from rich.console import Console
from typer.testing import CliRunner

from fieldkit.cli import app
from fieldkit.core.io import LoadedTable, load_table
from fieldkit_xray.profile import profile_table, to_json
from fieldkit_xray.render import render_html, render_terminal


@pytest.mark.parametrize(
    "filename",
    ["customers.csv", "events.jsonl", "orders.json", "inventory.xlsx", "messy.tsv"],
)
def test_profiles_every_table_format(fixture_dir: Path, filename: str) -> None:
    result = profile_table(load_table(fixture_dir / filename))

    assert result.row_count > 0
    assert result.column_count == len(result.columns)


def test_customer_profile(fixture_dir: Path) -> None:
    result = profile_table(load_table(fixture_dir / "customers.csv"))
    columns = {column.name: column for column in result.columns}

    assert result.row_count == 150
    assert columns["email"].pii["email"] >= 0.9
    assert columns["plan"].top_values == []
    assert any("raw top values" in warning for warning in result.warnings)
    assert columns["notes"].null_pct == pytest.approx(20, abs=5)
    assert columns["seats"].numeric is not None
    assert columns["mrr"].outlier_count >= 0


def test_empty_column_profile(fixture_dir: Path) -> None:
    result = profile_table(load_table(fixture_dir / "messy.tsv"))
    legacy_code = next(column for column in result.columns if column.name == "legacy_code")

    assert legacy_code.inferred_type == "empty"
    assert legacy_code.null_pct == 100
    assert legacy_code.top_values == []


def test_numeric_stats_and_outlier_examples_use_raw_values() -> None:
    table = LoadedTable(
        pd.DataFrame({"score": ["1", "2", "3", "100"]}, dtype="string"),
        fmt="csv",
        source="scores.csv",
        warnings=[],
    )

    score = profile_table(table, include_values=True).columns[0]

    assert score.numeric is not None
    assert score.numeric.min == 1
    assert score.numeric.max == 100
    assert score.outlier_count == 1
    assert score.outlier_examples == ["100"]


def test_json_round_trip_preserves_profile(fixture_dir: Path) -> None:
    result = profile_table(load_table(fixture_dir / "customers.csv"), top_k=3, include_values=True)

    payload = json.loads(to_json(result))

    assert list(payload) == sorted(payload)
    assert payload["source"] == "customers.csv"
    assert payload["row_count"] == 150
    assert len(payload["columns"][0]["top_values"]) <= 3


def test_renderers_include_summary_and_every_column(fixture_dir: Path) -> None:
    result = profile_table(load_table(fixture_dir / "customers.csv"))
    console = Console(record=True, width=180)

    render_terminal(result, console)
    terminal = console.export_text()
    html = render_html(result)

    assert "customers.csv" in terminal
    assert "150 × 14" in terminal
    assert "<!doctype html>" in html
    assert all(column.name in html for column in result.columns)


def test_default_reports_do_not_embed_source_values(fixture_dir: Path) -> None:
    result = profile_table(load_table(fixture_dir / "customers.csv"))
    payload = to_json(result)
    html = render_html(result)

    assert "shelbyjoyce1@example.com" not in payload
    assert "shelbyjoyce1@example.com" not in html
    assert all(column.top_values == [] for column in result.columns)
    assert all(column.outlier_examples == [] for column in result.columns)


def test_cli_raw_values_require_explicit_flag(fixture_dir: Path, tmp_path: Path) -> None:
    default_path = tmp_path / "default.json"
    raw_path = tmp_path / "raw.json"
    source = fixture_dir / "customers.csv"

    default = CliRunner().invoke(app, ["xray", str(source), "--json", str(default_path)])
    raw = CliRunner().invoke(
        app,
        ["xray", str(source), "--json", str(raw_path), "--include-values"],
    )

    assert default.exit_code == 0, default.output
    assert raw.exit_code == 0, raw.output
    assert "shelbyjoyce1@example.com" not in default_path.read_text(encoding="utf-8")
    assert "shelbyjoyce1@example.com" in raw_path.read_text(encoding="utf-8")


def test_cli_writes_json_and_html_reports(fixture_dir: Path, tmp_path: Path) -> None:
    json_path = tmp_path / "profile.json"
    html_path = tmp_path / "profile.html"

    result = CliRunner().invoke(
        app,
        [
            "xray",
            str(fixture_dir / "customers.csv"),
            "--json",
            str(json_path),
            "--html",
            str(html_path),
            "--top-k",
            "3",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "wrote" in result.output
    assert json_path.stat().st_size > 0
    assert html_path.stat().st_size > 0
    assert json.loads(json_path.read_text(encoding="utf-8"))["row_count"] == 150


def test_cli_missing_file_is_clean_error(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"

    result = CliRunner().invoke(app, ["xray", str(missing)])

    assert result.exit_code == 1
    assert "error: file not found" in result.output
    assert "Traceback" not in result.output


def test_pii_numeric_columns_get_no_numeric_stats(fixture_dir: Path) -> None:
    result = profile_table(load_table(fixture_dir / "customers.csv"))
    by_name = {c.name: c for c in result.columns}

    assert by_name["credit_card"].numeric is None
    assert by_name["mrr"].numeric is not None
