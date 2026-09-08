from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from fieldkit.core.io import load_table
from fieldkit.core.types import ColType, coerce, infer_column, infer_types


def test_customer_column_types(fixture_dir: Path) -> None:
    df = load_table(fixture_dir / "customers.csv").df
    inferred = infer_types(df)
    expected = {
        "customer_id": ColType.ID_LIKE,
        "email": ColType.TEXT,
        "plan": ColType.CATEGORICAL,
        "mrr": ColType.FLOAT,
        "seats": ColType.INTEGER,
        "churned": ColType.BOOLEAN,
        "signup_date": ColType.DATE,
        "notes": ColType.TEXT,
    }

    assert {column: inferred[column] for column in expected} == expected


def test_messy_empty_and_mixed_date_columns(fixture_dir: Path) -> None:
    df = load_table(fixture_dir / "messy.tsv").df

    assert infer_column(df["legacy_code"]) == ColType.EMPTY
    assert infer_column(df["started"]) == ColType.DATE


@pytest.mark.parametrize(
    ("values", "expected"),
    [
        (["yes", "no", "true", "false"], ColType.BOOLEAN),
        (["0", "1", "0", "1"], ColType.BOOLEAN),
        (["1", "1", "1"], ColType.INTEGER),
        (["1,234", "2,345", "3,456"], ColType.INTEGER),
        (["1.25", "2", "3.75"], ColType.FLOAT),
        (["2025-01-01T12:30:00", "2025-01-02T08:00:00"], ColType.DATETIME),
        ([pd.NA, None], ColType.EMPTY),
    ],
)
def test_infer_column_table(values: list[object], expected: ColType) -> None:
    assert infer_column(pd.Series(values, dtype="string")) == expected


def test_type_threshold_allows_one_bad_value_in_twenty() -> None:
    values = [str(index) for index in range(19)] + ["not-a-number"]

    assert infer_column(pd.Series(values)) == ColType.INTEGER


def test_coerce_returns_typed_copy(fixture_dir: Path) -> None:
    original = load_table(fixture_dir / "customers.csv").df.head(12)
    types = infer_types(original)

    typed = coerce(original, types)

    assert typed is not original
    assert original["seats"].dtype.name == "string"
    assert typed["seats"].dtype.name == "Int64"
    assert typed["mrr"].dtype.name == "Float64"
    assert typed["churned"].dtype.name == "boolean"
    assert str(typed["signup_date"].dtype) == "datetime64[ns]"
    assert typed["customer_id"].dtype.name == "string"
    assert typed["seats"].astype("string").tolist() == original["seats"].tolist()


def test_coerce_turns_invalid_values_into_missing() -> None:
    df = pd.DataFrame({"count": ["10", "bad"], "when": ["2025-01-01", "eventually"]})

    typed = coerce(df, {"count": ColType.INTEGER, "when": ColType.DATE})

    assert typed["count"].tolist()[0] == 10
    assert pd.isna(typed.loc[1, "count"])
    assert pd.isna(typed.loc[1, "when"])
