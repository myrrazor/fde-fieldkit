from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from rich.console import Console
from typer.testing import CliRunner

from fieldkit.cli import app
from fieldkit.core.io import LoadedTable, load_table
from fieldkit_datadiff.diff import detect_candidate_keys, diff_tables, to_json
from fieldkit_datadiff.render import render_html, render_terminal


def test_customer_diff_matches_engineered_fixture(fixture_dir: Path) -> None:
    result = diff_tables(
        load_table(fixture_dir / "customers.csv"),
        load_table(fixture_dir / "customers_v2.csv"),
    )

    assert result.schema.added_columns == ["region"]
    assert result.schema.removed_columns == ["ssn"]
    assert ("seats", "INTEGER", "FLOAT") in result.schema.type_changes
    assert result.key_detection["auto"] is True
    assert result.key_detection["candidates"][0] == ["customer_id"]
    assert result.rows is not None
    assert result.rows.added == 12
    assert result.rows.removed == 10
    assert result.rows.changed == 25
    assert result.rows.unchanged == 115
    assert result.rows.changed_by_column == {"mrr": 25, "plan": 8}
    assert result.drift.categorical["plan"].new_count == 1
    assert result.drift.categorical["plan"].new == []
    assert result.drift.numeric["mrr"]["mean_pct_change"] > 0


def test_candidate_keys_rank_id_like_singles_first() -> None:
    frame = pd.DataFrame(
        {
            "label": ["red", "green", "blue"],
            "customer_id": ["CUST-001", "CUST-002", "CUST-003"],
            "group": ["a", "a", "b"],
        },
        dtype="string",
    )

    candidates = detect_candidate_keys(frame)

    assert candidates[0] == ["customer_id"]
    assert ["label"] in candidates
    assert all(len(candidate) == 1 for candidate in candidates)


def test_wide_key_detection_stays_linear_in_schema_width() -> None:
    frame = pd.DataFrame(
        {
            f"column_{column}": [f"{column}-a", f"{column}-b", f"{column}-c"]
            for column in range(200)
        },
        dtype="string",
    )

    candidates = detect_candidate_keys(frame)

    assert len(candidates) == len(frame.columns)
    assert all(len(candidate) == 1 for candidate in candidates)


def test_explicit_composite_key_remains_supported() -> None:
    frame_a = pd.DataFrame(
        {"account": ["a", "a", "b"], "region": ["east", "west", "east"], "value": ["1", "2", "3"]},
        dtype="string",
    )
    frame_b = frame_a.copy()
    frame_b.at[1, "value"] = "4"
    a = LoadedTable(frame_a, fmt="csv", source="a.csv", warnings=[])
    b = LoadedTable(frame_b, fmt="csv", source="b.csv", warnings=[])

    result = diff_tables(a, b, keys=["account", "region"])

    assert result.rows is not None
    assert result.rows.key_columns == ["account", "region"]
    assert result.rows.changed == 1


def test_no_usable_key_skips_row_diff() -> None:
    frame_a = pd.DataFrame({"group": ["a", "a"], "value": ["1", "1"]}, dtype="string")
    frame_b = pd.DataFrame({"group": ["b", "b"], "value": ["2", "2"]}, dtype="string")
    a = LoadedTable(frame_a, fmt="csv", source="a.csv", warnings=[])
    b = LoadedTable(frame_b, fmt="csv", source="b.csv", warnings=[])

    result = diff_tables(a, b)

    assert result.rows is None
    assert "no usable key — row-level diff skipped (pass --key)" in result.warnings


def test_duplicate_explicit_key_skips_row_diff_and_names_key() -> None:
    frame = pd.DataFrame({"id": ["1", "1"], "value": ["a", "b"]}, dtype="string")
    a = LoadedTable(frame, fmt="csv", source="a.csv", warnings=[])
    b = LoadedTable(frame.copy(), fmt="csv", source="b.csv", warnings=[])

    result = diff_tables(a, b, keys=["id"])

    assert result.rows is None
    assert any("id" in warning and "duplicate key" in warning for warning in result.warnings)


def test_changed_samples_respect_limit_and_json_round_trips(fixture_dir: Path) -> None:
    result = diff_tables(
        load_table(fixture_dir / "customers.csv"),
        load_table(fixture_dir / "customers_v2.csv"),
        sample_limit=3,
        include_values=True,
    )

    assert result.rows is not None
    assert all(len(samples) <= 3 for samples in result.rows.samples.values())
    payload = json.loads(to_json(result))
    assert payload["rows"]["changed"] == 25
    assert payload["schema"]["added_columns"] == ["region"]


def test_renderers_include_schema_rows_drift_and_samples(fixture_dir: Path) -> None:
    result = diff_tables(
        load_table(fixture_dir / "customers.csv"),
        load_table(fixture_dir / "customers_v2.csv"),
        include_values=True,
    )
    console = Console(record=True, width=180)

    render_terminal(result, console)
    terminal = console.export_text()
    html = render_html(result)

    assert all(section in terminal for section in ("Schema", "Rows", "Drift"))
    assert "region" in html
    assert "ssn" in html
    assert "Changed" in html
    assert "→" in html


def test_default_reports_redact_row_and_category_values(fixture_dir: Path) -> None:
    result = diff_tables(
        load_table(fixture_dir / "customers.csv"),
        load_table(fixture_dir / "customers_v2.csv"),
    )
    payload = to_json(result)
    html = render_html(result)

    assert result.rows is not None
    assert result.rows.samples == {"added": [], "removed": [], "changed": []}
    assert result.drift.categorical["plan"].new_count == 1
    assert result.drift.categorical["plan"].new == []
    assert "shelbyjoyce1@example.com" not in payload
    assert "shelbyjoyce1@example.com" not in html
    assert any("raw row samples" in warning for warning in result.warnings)


def test_cli_raw_values_require_explicit_flag(fixture_dir: Path, tmp_path: Path) -> None:
    default_path = tmp_path / "default.json"
    raw_path = tmp_path / "raw.json"
    old = fixture_dir / "customers.csv"
    new = fixture_dir / "customers_v2.csv"

    default = CliRunner().invoke(app, ["datadiff", str(old), str(new), "--json", str(default_path)])
    raw = CliRunner().invoke(
        app,
        [
            "datadiff",
            str(old),
            str(new),
            "--json",
            str(raw_path),
            "--include-values",
        ],
    )

    assert default.exit_code == 0, default.output
    assert raw.exit_code == 0, raw.output
    assert "@example.com" not in default_path.read_text(encoding="utf-8")
    assert "@example.com" in raw_path.read_text(encoding="utf-8")


def test_cli_writes_json_and_html_reports(fixture_dir: Path, tmp_path: Path) -> None:
    json_path = tmp_path / "diff.json"
    html_path = tmp_path / "diff.html"

    result = CliRunner().invoke(
        app,
        [
            "datadiff",
            str(fixture_dir / "customers.csv"),
            str(fixture_dir / "customers_v2.csv"),
            "--key",
            "customer_id",
            "--json",
            str(json_path),
            "--html",
            str(html_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Schema" in result.output
    assert json.loads(json_path.read_text(encoding="utf-8"))["rows"]["added"] == 12
    html = html_path.read_text(encoding="utf-8")
    assert "region" in html
    assert "ssn" in html


def test_cli_load_error_is_clean(tmp_path: Path) -> None:
    missing = tmp_path / "missing.csv"

    result = CliRunner().invoke(app, ["datadiff", str(missing), str(missing)])

    assert result.exit_code == 1
    assert "error: file not found" in result.output
    assert "Traceback" not in result.output


def test_pii_numeric_columns_are_excluded_from_drift(fixture_dir: Path) -> None:
    # "mean credit card number" is not a statistic anyone needs
    a = load_table(fixture_dir / "customers.csv")
    b = load_table(fixture_dir / "customers_v2.csv")

    result = diff_tables(a, b)

    assert "credit_card" not in result.drift.numeric
    assert "mrr" in result.drift.numeric
