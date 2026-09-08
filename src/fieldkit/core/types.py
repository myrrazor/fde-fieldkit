from __future__ import annotations

import math
import re
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum

import pandas as pd

_THRESHOLD = 0.95
_INTEGER_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)$")
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y")
_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f%z",
)


class ColType(StrEnum):
    """Column types shared by profiling, diffing, and synthetic data tools."""

    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATETIME = "datetime"
    DATE = "date"
    CATEGORICAL = "categorical"
    ID_LIKE = "id_like"
    TEXT = "text"
    EMPTY = "empty"


def infer_column(s: pd.Series) -> ColType:
    """Infer one column using the 95 percent parse threshold."""

    values = s.dropna().map(str)
    if values.empty:
        return ColType.EMPTY

    lowered = values.str.strip().str.lower()
    bool_words = {"true", "false", "yes", "no"}
    bool_rate = lowered.isin(bool_words).mean()
    if bool_rate >= _THRESHOLD:
        return ColType.BOOLEAN
    if set(lowered) == {"0", "1"}:
        return ColType.BOOLEAN

    if _parse_rate(values, _parse_integer) >= _THRESHOLD:
        return ColType.INTEGER
    if _parse_rate(values, _parse_float) >= _THRESHOLD:
        return ColType.FLOAT
    if _parse_rate(values, _parse_date) >= _THRESHOLD:
        return ColType.DATE
    if _parse_rate(values, _parse_datetime) >= _THRESHOLD:
        return ColType.DATETIME
    if _is_id_like(values):
        return ColType.ID_LIKE

    distinct = values.nunique()
    if distinct <= 20 or distinct / len(values) <= 0.05:
        return ColType.CATEGORICAL
    return ColType.TEXT


def infer_types(df: pd.DataFrame) -> dict[str, ColType]:
    """Infer every column in a dataframe."""

    return {str(column): infer_column(df[column]) for column in df.columns}


def coerce(df: pd.DataFrame, types: dict[str, ColType]) -> pd.DataFrame:
    """Return a typed copy, coercing invalid values to missing values."""

    typed = df.copy()
    for column, col_type in types.items():
        if column not in typed.columns:
            continue
        series = typed[column]
        if col_type == ColType.INTEGER:
            cleaned = series.astype("string").str.replace(",", "", regex=False)
            typed[column] = pd.to_numeric(cleaned, errors="coerce").astype("Int64")
        elif col_type == ColType.FLOAT:
            cleaned = series.astype("string").str.replace(",", "", regex=False)
            typed[column] = pd.to_numeric(cleaned, errors="coerce").astype("Float64")
        elif col_type == ColType.BOOLEAN:
            lowered = series.astype("string").str.strip().str.lower()
            typed[column] = lowered.map(
                {"true": True, "yes": True, "1": True, "false": False, "no": False, "0": False}
            ).astype("boolean")
        elif col_type == ColType.DATE:
            typed[column] = _coerce_temporal(series, _parse_date)
        elif col_type == ColType.DATETIME:
            typed[column] = _coerce_temporal(series, _parse_datetime)
        else:
            typed[column] = series.astype("string")
    return typed


def _parse_rate(values: pd.Series, parser: Callable[[str], object | None]) -> float:
    return sum(parser(value) is not None for value in values) / len(values)


def _parse_integer(value: str) -> int | None:
    text = value.strip()
    if not _INTEGER_RE.fullmatch(text):
        return None
    return int(text.replace(",", ""))


def _parse_float(value: str) -> float | None:
    try:
        parsed = float(value.strip().replace(",", ""))
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_date(value: str) -> datetime | None:
    return _parse_formats(value.strip(), _DATE_FORMATS)


def _parse_datetime(value: str) -> datetime | None:
    return _parse_formats(value.strip(), _DATETIME_FORMATS)


def _parse_formats(value: str, formats: tuple[str, ...]) -> datetime | None:
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _is_id_like(values: pd.Series) -> bool:
    if len(values) < 3 or values.nunique() != len(values):
        return False

    integers = [_parse_integer(value) for value in values]
    if all(value is not None for value in integers):
        nums = [value for value in integers if value is not None]
        deltas = [right - left for left, right in zip(nums, nums[1:], strict=False)]
        increasing = sum(delta > 0 for delta in deltas)
        decreasing = sum(delta < 0 for delta in deltas)
        if max(increasing, decreasing) / len(deltas) >= 0.9:
            return True

    shapes = {_shape(value) for value in values}
    if len(shapes) != 1:
        return False
    shape = next(iter(shapes))
    return any(char != "A" for char in shape)


def _shape(value: str) -> str:
    return "".join("A" if char.isalpha() else "9" if char.isdigit() else char for char in value)


def _coerce_temporal(
    series: pd.Series, parser: Callable[[str], datetime | None]
) -> pd.Series:
    parsed = [parser(str(value)) if not pd.isna(value) else None for value in series]
    return pd.Series(parsed, index=series.index, dtype="datetime64[ns]")
