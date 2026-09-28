from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from enum import StrEnum

import numpy as np
import pandas as pd

_THRESHOLD = 0.95
_INTEGER_RE = re.compile(r"^[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)$")
# Python's float() literal, including underscores between digits. Non-finite
# values still have to be rejected after the match.
_FLOAT_RE = re.compile(
    r"^[+-]?(?:"
    r"(?:[0-9](?:_?[0-9])*)(?:\.(?:[0-9](?:_?[0-9])*)?)?"
    r"|\.[0-9](?:_?[0-9])*"
    r")(?:[eE][+-]?[0-9](?:_?[0-9])*)?$"
)
_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y")
_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f%z",
)
# Supersets of what strptime accepts for the formats above. A column that
# misses the shape cannot clear the 95% threshold, so plain text never pays
# for a parse. Matches still go through the real formats, in the same order.
_DATE_SHAPE = re.compile(r"^(?:[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}|[0-9]{1,2}/[0-9]{1,2}/[0-9]{4})$")
# One or more spaces (exports pad the gap), and offsets with optional seconds
# (`+05:30:00`). Hours, minutes, and seconds are still checked for real ranges
# so `10:00:60` is not a timestamp pandas would roll into the next minute.
_DATETIME_SHAPE = re.compile(
    r"^[0-9]{4}-[0-9]{1,2}-[0-9]{1,2}[Tt ]+[0-9]{1,2}:[0-9]{1,2}:[0-9]{1,2}"
    r"(?:\.[0-9]{1,6})?(?:[Zz]|[+-][0-9]{2}:?[0-9]{2}(?::?[0-9]{2})?)?$"
)
_CLOCK_RE = re.compile(r"[T ](\d{1,2}):(\d{1,2}):(\d{1,2})")
# pandas datetime64[ns] runs from 1677-09-21 00:12:43.145224193 through
# 2262-04-11 23:47:16.854775807. Stay a second inside those edges so a value
# pandas itself stores is kept. Year 9999 is still outside and must not be coerced.
_NS_MIN_US = np.datetime64("1677-09-21T00:12:44", "us")
_NS_MAX_US = np.datetime64("2262-04-11T23:47:16", "us")
_NS_MIN_PY = datetime(1677, 9, 21, 0, 12, 44)
_NS_MAX_PY = datetime(2262, 4, 11, 23, 47, 16)
# Wide files are short per column. The vectorized path's Series overhead
# dominates there; a few dozen Python parses do not.
_SHORT_COLUMN = 128


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

    if len(s) <= _SHORT_COLUMN:
        return _infer_short(s)

    values = s.dropna().map(str)
    if values.empty:
        return ColType.EMPTY
    values = values.astype("string")

    lowered = values.str.strip().str.lower()
    bool_words = {"true", "false", "yes", "no"}
    if float(lowered.isin(bool_words).mean()) >= _THRESHOLD:
        return ColType.BOOLEAN
    if bool(lowered.isin(("0", "1")).all()) and int(lowered.nunique()) == 2:
        return ColType.BOOLEAN

    if _integer_rate(values) >= _THRESHOLD:
        return ColType.INTEGER
    if _float_rate(values) >= _THRESHOLD:
        return ColType.FLOAT
    if _temporal_rate(values, _DATE_SHAPE, _DATE_FORMATS) >= _THRESHOLD:
        return ColType.DATE
    if _temporal_rate(values, _DATETIME_SHAPE, _DATETIME_FORMATS) >= _THRESHOLD:
        return ColType.DATETIME
    if _is_id_like(values):
        return ColType.ID_LIKE

    distinct = int(values.nunique())
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
            typed[column] = _coerce_temporal(series, _DATE_FORMATS)
        elif col_type == ColType.DATETIME:
            typed[column] = _coerce_temporal(series, _DATETIME_FORMATS)
        else:
            typed[column] = series.astype("string")
    return typed


def _integer_rate(values: pd.Series) -> float:
    return float(values.str.strip().str.fullmatch(_INTEGER_RE, na=False).mean())


def _float_rate(values: pd.Series) -> float:
    cleaned = values.str.strip().str.replace(",", "", regex=False)
    matched = cleaned.str.fullmatch(_FLOAT_RE, na=False)
    count = 0
    if bool(matched.any()):
        bare = cleaned.loc[matched].str.replace("_", "", regex=False)
        nums = pd.to_numeric(bare, errors="coerce").to_numpy(dtype="float64", na_value=np.nan)
        count = int(np.isfinite(nums).sum())
    if count / len(cleaned) >= _THRESHOLD:
        return count / len(cleaned)
    # float() also accepts non-ASCII digits. Only scan those when the ASCII
    # literal rate cannot already settle the column.
    if bool(matched.all()):
        return count / len(cleaned)
    rest = cleaned.loc[~matched]
    exotic = rest.str.contains(r"[^\x00-\x7F]", na=False)
    if bool(exotic.any()):
        count += sum(_parse_float(value) is not None for value in rest.loc[exotic])
    return count / len(cleaned)


def _temporal_rate(values: pd.Series, shape: re.Pattern[str], formats: tuple[str, ...]) -> float:
    stripped = _collapse_spaces(values.str.strip())
    pending = stripped.str.fullmatch(shape, na=False)
    if float(pending.mean()) < _THRESHOLD:
        return 0.0
    ok = _match_formats(stripped, pending, formats)
    return float(ok.sum()) / len(stripped)


def _match_formats(text: pd.Series, pending: pd.Series, formats: tuple[str, ...]) -> pd.Series:
    """True where ``text`` matches a format. Earlier formats win the cell."""

    text = _collapse_spaces(text)
    pending = pending & ~_invalid_clock(text)
    matched = pd.Series(False, index=text.index)
    still = pending.fillna(False).to_numpy(dtype=bool, copy=True)
    for fmt in formats:
        positions = np.flatnonzero(still)
        if len(positions) == 0:
            break
        parsed = _to_datetime(text.iloc[positions], fmt)
        good = _within_ns(parsed)
        if not good.any():
            continue
        hit = positions[good]
        matched.iloc[hit] = True
        still[hit] = False
    return matched


def _parse_float(value: str) -> float | None:
    try:
        parsed = float(value.strip().replace(",", ""))
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _parse_integer(value: str) -> int | None:
    text = value.strip()
    if not _INTEGER_RE.fullmatch(text):
        return None
    return int(text.replace(",", ""))


def _is_id_like(values: pd.Series) -> bool:
    if len(values) < 3 or values.nunique() != len(values):
        return False

    stripped = values.str.strip()
    if bool(stripped.str.fullmatch(_INTEGER_RE, na=False).all()):
        nums = [_parse_integer(value) for value in values]
        if all(value is not None for value in nums):
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


def _coerce_temporal(series: pd.Series, formats: tuple[str, ...]) -> pd.Series:
    present = series.notna()
    text = pd.Series(pd.NA, index=series.index, dtype="string")
    if bool(present.any()):
        text.loc[present] = series.loc[present].map(lambda value: str(value).strip())
    text = _collapse_spaces(text)
    pending = text.notna() & text.ne("") & ~_invalid_clock(text)
    parsed_at = pd.Series(pd.NaT, index=series.index, dtype="datetime64[ns]")
    still = pending.fillna(False).to_numpy(dtype=bool, copy=True)
    for fmt in formats:
        positions = np.flatnonzero(still)
        if len(positions) == 0:
            break
        parsed = _to_datetime(text.iloc[positions], fmt)
        good = _within_ns(parsed)
        if not good.any():
            continue
        chosen = _naive_ns(parsed.iloc[np.flatnonzero(good)])
        hit = positions[good]
        parsed_at.iloc[hit] = chosen
        still[hit] = False
    return parsed_at


def _collapse_spaces(text: pd.Series) -> pd.Series:
    if text.dtype.name != "string":
        return text
    # A tab between the date and the clock is whitespace to strptime's %X
    # formats only after it has been folded into a single space.
    if not bool(text.str.contains(r"\t|  ", regex=True, na=False).any()):
        return text
    return text.str.replace(r"\s+", " ", regex=True)


def _invalid_clock(text: pd.Series) -> pd.Series:
    if text.dtype.name != "string":
        return pd.Series(False, index=text.index)
    parts = text.str.extract(_CLOCK_RE)
    if bool(parts.isna().all().all()):
        return pd.Series(False, index=text.index)
    hours = pd.to_numeric(parts[0], errors="coerce")
    minutes = pd.to_numeric(parts[1], errors="coerce")
    seconds = pd.to_numeric(parts[2], errors="coerce")
    return (hours.gt(23) | minutes.gt(59) | seconds.gt(59)).fillna(False)


def _to_datetime(values: pd.Series, fmt: str) -> pd.Series:
    kwargs: dict[str, object] = {"format": fmt, "errors": "coerce"}
    # pandas 3 raises (it does not coerce) when one column mixes offsets
    # such as -05:00 and -04:00. utc=True folds them to one zone first.
    if "%z" in fmt:
        kwargs["utc"] = True
    try:
        return pd.to_datetime(values, **kwargs)
    except (ValueError, pd.errors.OutOfBoundsDatetime, OverflowError):
        return pd.Series(pd.NaT, index=values.index)


def _within_ns(parsed: pd.Series) -> np.ndarray:
    ok = parsed.notna().to_numpy()
    if not ok.any():
        return ok
    us = _as_us(parsed)
    inbound = (us >= _NS_MIN_US) & (us <= _NS_MAX_US)
    return ok & inbound


def _naive_ns(parsed: pd.Series) -> np.ndarray:
    us = _as_us(parsed).copy()
    bad = (us < _NS_MIN_US) | (us > _NS_MAX_US)
    us[bad] = np.datetime64("NaT", "us")
    return us.astype("datetime64[ns]")


def _as_us(parsed: pd.Series) -> np.ndarray:
    tz = getattr(parsed.dtype, "tz", None)
    if tz is not None:
        parsed = parsed.dt.tz_convert(timezone.utc).dt.tz_localize(None)
    return parsed.astype("datetime64[us]").to_numpy()


def _infer_short(series: pd.Series) -> ColType:
    values: list[str] = []
    for value in series.tolist():
        if value is None or value is pd.NA:
            continue
        if isinstance(value, float) and math.isnan(value):
            continue
        values.append(str(value))
    if not values:
        return ColType.EMPTY

    count = len(values)
    lowered = [value.strip().lower() for value in values]
    if sum(value in {"true", "false", "yes", "no"} for value in lowered) / count >= _THRESHOLD:
        return ColType.BOOLEAN
    if set(lowered) == {"0", "1"}:
        return ColType.BOOLEAN
    if sum(_parse_integer(value) is not None for value in values) / count >= _THRESHOLD:
        return ColType.INTEGER
    if sum(_parse_float(value) is not None for value in values) / count >= _THRESHOLD:
        return ColType.FLOAT
    if _short_temporal_rate(values, _DATE_SHAPE, _DATE_FORMATS) >= _THRESHOLD:
        return ColType.DATE
    if _short_temporal_rate(values, _DATETIME_SHAPE, _DATETIME_FORMATS) >= _THRESHOLD:
        return ColType.DATETIME
    if _short_id_like(values):
        return ColType.ID_LIKE

    distinct = len(set(values))
    if distinct <= 20 or distinct / count <= 0.05:
        return ColType.CATEGORICAL
    return ColType.TEXT


def _short_temporal_rate(
    values: list[str], shape: re.Pattern[str], formats: tuple[str, ...]
) -> float:
    ok = sum(_parse_temporal_value(value.strip(), shape, formats) is not None for value in values)
    return ok / len(values)


def _parse_temporal_value(
    value: str, shape: re.Pattern[str], formats: tuple[str, ...]
) -> datetime | None:
    if "\t" in value or "  " in value:
        value = re.sub(r"\s+", " ", value)
    if shape.fullmatch(value) is None or not _clock_ok_text(value):
        return None
    parsed = _parse_formats(value, formats)
    if parsed is None:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    if parsed < _NS_MIN_PY or parsed > _NS_MAX_PY:
        return None
    return parsed


def _clock_ok_text(value: str) -> bool:
    match = _CLOCK_RE.search(value)
    if match is None:
        return True
    hour, minute, second = (int(part) for part in match.groups())
    return hour <= 23 and minute <= 59 and second <= 59


def _parse_formats(value: str, formats: tuple[str, ...]) -> datetime | None:
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def _short_id_like(values: list[str]) -> bool:
    if len(values) < 3 or len(set(values)) != len(values):
        return False
    numbers = [_parse_integer(value) for value in values]
    if all(value is not None for value in numbers):
        deltas = [right - left for left, right in zip(numbers, numbers[1:], strict=False)]
        increasing = sum(delta > 0 for delta in deltas)
        decreasing = sum(delta < 0 for delta in deltas)
        if max(increasing, decreasing) / len(deltas) >= 0.9:
            return True
    shapes = {_shape(value) for value in values}
    if len(shapes) != 1:
        return False
    return any(char != "A" for char in next(iter(shapes)))
