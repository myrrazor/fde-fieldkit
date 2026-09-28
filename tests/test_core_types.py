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


def test_coerce_normalizes_timezone_aware_iso_datetimes_to_utc() -> None:
    df = pd.DataFrame(
        {"when": ["2025-01-01T12:30:00+02:00", "2025-01-01T10:30:00Z"]}
    )

    assert infer_column(df["when"]) == ColType.DATETIME
    typed = coerce(df, {"when": ColType.DATETIME})

    assert str(typed["when"].dtype) == "datetime64[ns]"
    assert typed["when"].tolist() == [pd.Timestamp("2025-01-01T10:30:00")] * 2


def test_datetime_edges_match_strptime_and_do_not_crash() -> None:
    # Long enough to take the vectorized parser, which is where mixed offsets raised.
    mixed = pd.Series(
        ["2024-03-09T10:00:00-05:00", "2024-03-11T10:00:00-04:00"] * 100, dtype="string"
    )
    doubled = pd.Series(["2024-01-17  10:00:00"] * 200, dtype="string")
    offset = pd.Series(["2024-01-17T10:00:00+05:30:00"] * 200, dtype="string")
    leap = pd.Series(["2024-01-17 10:00:60"] * 200, dtype="string")
    sentinel = pd.Series(["9999-12-31"] * 200, dtype="string")
    tabbed = pd.Series(["2024-01-17\t10:00:00"] * 200, dtype="string")
    early = pd.Series(["1677-09-22"] * 200, dtype="string")
    late = pd.Series(["2261-12-31"] * 200, dtype="string")

    assert infer_column(mixed) == ColType.DATETIME
    assert infer_column(doubled) == ColType.DATETIME
    assert infer_column(offset) == ColType.DATETIME
    assert infer_column(leap) == ColType.CATEGORICAL
    assert infer_column(sentinel) == ColType.CATEGORICAL
    assert infer_column(tabbed) == ColType.DATETIME
    assert infer_column(pd.Series(["2024-01-17\t10:00:00"] * 4, dtype="string")) == ColType.DATETIME
    assert infer_column(early) == ColType.DATE
    assert infer_column(late) == ColType.DATE

    typed = coerce(
        pd.DataFrame({"when": mixed, "gap": doubled, "zone": offset, "sent": sentinel}),
        {
            "when": ColType.DATETIME,
            "gap": ColType.DATETIME,
            "zone": ColType.DATETIME,
            "sent": ColType.DATE,
        },
    )

    assert list(typed["when"].iloc[:2]) == [
        pd.Timestamp("2024-03-09 15:00:00"),
        pd.Timestamp("2024-03-11 14:00:00"),
    ]
    assert list(typed["gap"].iloc[:2]) == [pd.Timestamp("2024-01-17 10:00:00")] * 2
    assert list(typed["zone"].iloc[:2]) == [pd.Timestamp("2024-01-17 04:30:00")] * 2
    assert typed["sent"].isna().all()
