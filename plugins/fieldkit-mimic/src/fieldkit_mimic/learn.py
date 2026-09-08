from __future__ import annotations

import math
import string
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from fieldkit.core.io import LoadedTable
from fieldkit.core.pii import PIIKind, scan_text
from fieldkit.core.types import ColType, coerce, infer_types

_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y")
_DATETIME_FORMATS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S.%f%z",
)
# order matters: for multi-flagged columns the first hit wins. ssn/credit_card/ip
# are in here so their real values never end up in quantile grids or id patterns.
_SENSITIVE_KIND_ORDER = (
    PIIKind.SECRET,
    PIIKind.EMAIL,
    PIIKind.NAME,
    PIIKind.PHONE,
    PIIKind.SSN,
    PIIKind.CREDIT_CARD,
    PIIKind.IP,
)


@dataclass
class ColumnSpec:
    """Generation rules for one output column."""

    name: str
    kind: str
    params: dict[str, Any] = field(default_factory=dict)
    unique: bool = False
    null_rate: float = 0.0


@dataclass
class MimicSpec:
    """A portable description of a sampled table."""

    name: str
    rows_sampled: int
    columns: list[ColumnSpec]


def learn_spec(table: LoadedTable, *, name: str = "") -> MimicSpec:
    """Learn deterministic generation rules from a loaded sample."""

    df = table.df
    column_names = [str(column) for column in df.columns]
    _validate_column_names(column_names)
    inferred = infer_types(df)
    typed = coerce(df, inferred)
    columns: list[ColumnSpec] = []

    for raw_name in df.columns:
        column_name = str(raw_name)
        source = df[raw_name]
        null_rate = round(float(source.isna().mean()), 2)
        pii_kind = _pii_kind(source, column_name)
        if pii_kind is not None:
            params: dict[str, Any] = {}
            if pii_kind == PIIKind.NAME:
                # keep first_name columns one word wide — full names look wrong there
                word_counts = Counter(len(str(value).split()) for value in source.dropna())
                params["words"] = word_counts.most_common(1)[0][0] if word_counts else 2
            columns.append(ColumnSpec(column_name, pii_kind.value, params, null_rate=null_rate))
            continue

        col_type = inferred[column_name]
        params: dict[str, Any]
        unique = False
        if col_type == ColType.ID_LIKE:
            params, unique = _id_params(source)
            kind = "id_pattern"
        elif col_type == ColType.CATEGORICAL:
            params = _categorical_params(source)
            kind = "categorical"
        elif col_type in {ColType.INTEGER, ColType.FLOAT}:
            params = _numeric_params(source, typed[column_name], col_type)
            kind = "numeric"
        elif col_type in {ColType.DATE, ColType.DATETIME}:
            params = _temporal_params(source, col_type)
            kind = "datetime"
        elif col_type == ColType.BOOLEAN:
            params = {"true_rate": round(float(typed[column_name].dropna().mean()), 2)}
            kind = "boolean"
        elif col_type == ColType.EMPTY:
            params = {}
            kind = "text"
            null_rate = 1.0
        else:
            params = _text_params(source)
            kind = "text"
        columns.append(ColumnSpec(column_name, kind, params, unique, null_rate))

    return MimicSpec(name=_portable_name(name), rows_sampled=len(df), columns=columns)


def load_spec(path: Path) -> MimicSpec:
    """Load and validate a mimic YAML spec."""

    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid mimic spec: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("mimic spec must be a YAML mapping")

    raw_columns = payload.get("columns")
    if not isinstance(raw_columns, list):
        raise ValueError("mimic spec needs a columns list")
    columns = [_load_column(item, index) for index, item in enumerate(raw_columns)]
    _validate_column_names([column.name for column in columns])

    name = payload.get("name", "")
    rows_sampled = payload.get("rows_sampled", 0)
    if not isinstance(name, str):
        raise ValueError("spec name must be a string")
    if not isinstance(rows_sampled, int) or isinstance(rows_sampled, bool) or rows_sampled < 0:
        raise ValueError("rows_sampled must be a non-negative integer")
    return MimicSpec(name=_portable_name(name), rows_sampled=rows_sampled, columns=columns)


def dump_spec(spec: MimicSpec) -> str:
    """Serialize a mimic spec as stable, hand-editable YAML."""

    _validate_column_names([column.name for column in spec.columns])
    payload = {
        "name": _portable_name(spec.name),
        "rows_sampled": spec.rows_sampled,
        "columns": [
            {
                "name": column.name,
                "kind": column.kind,
                "params": column.params,
                "unique": column.unique,
                "null_rate": column.null_rate,
            }
            for column in spec.columns
        ],
    }
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def _pii_kind(series: pd.Series, column_name: str) -> PIIKind | None:
    detected = {
        match.kind
        for value in series.dropna()
        for match in scan_text(str(value), column_name=column_name)
    }
    for kind in _SENSITIVE_KIND_ORDER:
        if kind in detected:
            return kind
    return None


def _portable_name(name: str) -> str:
    if not isinstance(name, str):
        raise ValueError("spec name must be a string")
    return "dataset" if scan_text(name, column_name="name") else name


def _validate_column_names(names: list[str]) -> None:
    if any(not isinstance(name, str) or not name for name in names):
        raise ValueError("mimic specs need non-empty text column names")
    if len(names) != len(set(names)):
        raise ValueError("mimic specs need unique column names")
    for name in names:
        if scan_text(name, column_name=name):
            raise ValueError("a column name contains sensitive data — rename it before generating")


def _id_params(series: pd.Series) -> tuple[dict[str, Any], bool]:
    values = [str(value) for value in series.dropna()]
    unique = len(values) == len(set(values))
    if not values:
        return {"pattern": "####", "start": 1}, unique

    if all(value.lstrip("+-").isdigit() for value in values):
        width = max(len(value.lstrip("+-")) for value in values)
        start = max(int(value) for value in values) + 1
        return {"pattern": "#" * width, "start": start}, unique

    masks = [_shape_mask(value) for value in values]
    common_mask, _ = Counter(masks).most_common(1)[0]
    matching = [value for value, mask in zip(values, masks, strict=True) if mask == common_mask]
    pattern = _stable_pattern(matching)
    if len(set(masks)) > 1:
        pattern = f"{pattern}-####"
        start = 1
    else:
        counters = [int("".join(char for char in value if char.isdigit())) for value in values]
        start = min(counters) if counters and all(counter >= 0 for counter in counters) else 1
    if unique and "#" not in pattern:
        pattern = f"{pattern}-####"
    return {"pattern": pattern, "start": start}, unique


def _shape_mask(value: str) -> str:
    return "".join(
        "#" if char.isdigit() else "?" if char in string.ascii_letters else char for char in value
    )


def _stable_pattern(values: list[str]) -> str:
    pattern = []
    for chars in zip(*values, strict=True):
        if len(set(chars)) == 1 and not chars[0].isdigit():
            pattern.append(chars[0])
        elif all(char.isdigit() for char in chars):
            pattern.append("#")
        elif all(char in string.ascii_letters for char in chars):
            pattern.append("?")
        else:
            pattern.append(chars[0])
    return "".join(pattern)


def _categorical_params(series: pd.Series) -> dict[str, Any]:
    values = [str(value) for value in series.dropna()]
    counts = Counter(values)
    total = len(values)
    return {"values": {value: round(count / total, 2) for value, count in counts.items()}}


def _numeric_params(source: pd.Series, typed: pd.Series, col_type: ColType) -> dict[str, Any]:
    values = typed.dropna().astype(float)
    quantiles = [float(values.quantile(index / 20)) for index in range(21)]
    decimals = (
        0
        if col_type == ColType.INTEGER
        else max((_decimal_places(str(value)) for value in source.dropna()), default=0)
    )
    return {"quantiles": quantiles, "decimals": decimals}


def _decimal_places(value: str) -> int:
    try:
        exponent = Decimal(value.replace(",", "").strip()).as_tuple().exponent
    except InvalidOperation:
        return 0
    return max(0, -exponent)


def _temporal_params(series: pd.Series, col_type: ColType) -> dict[str, Any]:
    formats = _DATE_FORMATS if col_type == ColType.DATE else _DATETIME_FORMATS
    parsed: list[tuple[datetime, str]] = []
    for raw_value in series.dropna():
        value = str(raw_value).strip()
        for fmt in formats:
            try:
                parsed.append((datetime.strptime(value, fmt), fmt))
                break
            except ValueError:
                continue

    dominant = Counter(fmt for _, fmt in parsed).most_common(1)[0][0]
    timestamps = [value.timestamp() for value, _ in parsed]
    minimum = datetime.fromtimestamp(min(timestamps), tz=parsed[0][0].tzinfo)
    maximum = datetime.fromtimestamp(max(timestamps), tz=parsed[0][0].tzinfo)
    return {
        "min": minimum.strftime(dominant),
        "max": maximum.strftime(dominant),
        "format": dominant,
    }


def _text_params(series: pd.Series) -> dict[str, Any]:
    counts = [len(str(value).split()) for value in series.dropna()]
    average = sum(counts) / len(counts) if counts else 0
    return {"avg_words": max(1, math.floor(average + 0.5))}


def _load_column(payload: object, index: int) -> ColumnSpec:
    if not isinstance(payload, dict):
        raise ValueError(f"column {index + 1} must be a mapping")
    name = payload.get("name")
    kind = payload.get("kind")
    params = payload.get("params", {})
    unique = payload.get("unique", False)
    null_rate = payload.get("null_rate", 0.0)
    if not isinstance(name, str) or not name:
        raise ValueError(f"column {index + 1} needs a name")
    if not isinstance(kind, str) or not kind:
        raise ValueError(f"column {name!r} needs a kind")
    if not isinstance(params, dict):
        raise ValueError(f"column {name!r} params must be a mapping")
    if not isinstance(unique, bool):
        raise ValueError(f"column {name!r} unique must be true or false")
    if not isinstance(null_rate, int | float) or isinstance(null_rate, bool):
        raise ValueError(f"column {name!r} null_rate must be a number")
    if not 0 <= float(null_rate) <= 1:
        raise ValueError(f"column {name!r} null_rate must be between 0 and 1")
    return ColumnSpec(name, kind, dict(params), unique, float(null_rate))
