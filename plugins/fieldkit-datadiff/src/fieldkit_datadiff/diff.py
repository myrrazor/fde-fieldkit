from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from fieldkit.core.io import LoadedTable
from fieldkit.core.pii import PIIKind, scan_column
from fieldkit.core.types import ColType, coerce, infer_column, infer_types

# card/ssn/phone columns parse as numbers, but "mean credit card" is noise
_DRIFT_EXCLUDED_PII = {PIIKind.CREDIT_CARD, PIIKind.SSN, PIIKind.PHONE}

_NUMERIC_TYPES = {ColType.INTEGER, ColType.FLOAT}


@dataclass
class SchemaDiff:
    """Column-level differences between two tables."""

    added_columns: list[str]
    removed_columns: list[str]
    type_changes: list[tuple[str, str, str]]
    nullability_changes: list[tuple[str, float, float]]


@dataclass
class RowDiff:
    """Keyed row counts, cell changes, and representative samples."""

    key_columns: list[str]
    added: int
    removed: int
    changed: int
    unchanged: int
    changed_by_column: dict[str, int]
    samples: dict[str, list[dict[str, Any]]]


@dataclass
class CategoricalDrift:
    """Categorical movement counts plus optional raw category values."""

    new_count: int
    vanished_count: int
    new: list[str]
    vanished: list[str]


@dataclass
class DriftReport:
    """Categorical and numeric distribution movement."""

    categorical: dict[str, CategoricalDrift]
    numeric: dict[str, dict[str, float]]


@dataclass
class DiffResult:
    """A complete schema, row, and drift comparison."""

    source_a: str
    source_b: str
    rows_a: int
    rows_b: int
    schema: SchemaDiff
    rows: RowDiff | None
    drift: DriftReport
    key_detection: dict[str, Any]
    warnings: list[str]


@dataclass
class _PreparedColumn:
    raw: pd.Series
    typed: pd.Series
    failed: pd.Series


def detect_candidate_keys(df: pd.DataFrame) -> list[list[str]]:
    """Return unique, non-null single columns in preference order."""

    if df.empty:
        return []

    columns = [str(column) for column in df.columns]
    singles = [
        column
        for column in columns
        if df[column].notna().all() and not df[column].duplicated().any()
    ]
    id_like = [column for column in singles if infer_column(df[column]) == ColType.ID_LIKE]
    candidates = [[column] for column in id_like]
    candidates.extend([column] for column in singles if column not in id_like)
    return candidates


def diff_tables(
    a: LoadedTable,
    b: LoadedTable,
    *,
    keys: list[str] | None = None,
    sample_limit: int = 20,
    include_values: bool = False,
) -> DiffResult:
    """Compare tables, omitting source values unless explicitly requested."""

    if sample_limit < 0:
        raise ValueError("sample_limit must not be negative")

    raw_a = a.df.reset_index(drop=True)
    raw_b = b.df.reset_index(drop=True)
    columns_a = [str(column) for column in raw_a.columns]
    columns_b = [str(column) for column in raw_b.columns]
    shared = [column for column in columns_a if column in columns_b]
    types_a = infer_types(raw_a)
    types_b = infer_types(raw_b)
    warnings = [*a.warnings, *b.warnings]

    schema = _schema_diff(raw_a, raw_b, columns_a, columns_b, shared, types_a, types_b)
    drift = _drift_report(
        raw_a,
        raw_b,
        shared,
        types_a,
        types_b,
        include_values=include_values,
    )
    if not include_values:
        warnings.append(
            "raw row samples and category values omitted; "
            "use the CLI --include-values flag only for an authorized report"
        )

    if keys is None:
        candidates = _shared_candidates(raw_a, raw_b, shared)
        key_columns = candidates[0] if candidates else None
        auto = True
    else:
        key_columns = _validated_keys(keys, shared)
        candidates = [key_columns]
        auto = False

    rows = None
    if key_columns is None:
        warnings.append("no usable key — row-level diff skipped (pass --key)")
    else:
        prepared_a, prepared_b = _prepare_shared_columns(raw_a, raw_b, shared, types_a, types_b)
        rows, row_warning = _row_diff(
            raw_a,
            raw_b,
            shared,
            key_columns,
            prepared_a,
            prepared_b,
            source_a=a.source,
            source_b=b.source,
            sample_limit=sample_limit,
            include_values=include_values,
        )
        if row_warning is not None:
            warnings.append(row_warning)

    return DiffResult(
        source_a=a.source,
        source_b=b.source,
        rows_a=len(raw_a),
        rows_b=len(raw_b),
        schema=schema,
        rows=rows,
        drift=drift,
        key_detection={"auto": auto, "candidates": candidates},
        warnings=warnings,
    )


def to_json(result: DiffResult) -> str:
    """Serialize a diff report with stable ordering and JSON-safe sample values."""

    return json.dumps(asdict(result), indent=2, sort_keys=True, allow_nan=False)


def _schema_diff(
    a: pd.DataFrame,
    b: pd.DataFrame,
    columns_a: list[str],
    columns_b: list[str],
    shared: list[str],
    types_a: dict[str, ColType],
    types_b: dict[str, ColType],
) -> SchemaDiff:
    type_changes = [
        (column, types_a[column].name, types_b[column].name)
        for column in shared
        if types_a[column] != types_b[column]
    ]
    nullability_changes = []
    for column in shared:
        old_pct = _null_pct(a[column])
        new_pct = _null_pct(b[column])
        if abs(new_pct - old_pct) > 5:
            nullability_changes.append((column, old_pct, new_pct))

    return SchemaDiff(
        added_columns=[column for column in columns_b if column not in columns_a],
        removed_columns=[column for column in columns_a if column not in columns_b],
        type_changes=type_changes,
        nullability_changes=nullability_changes,
    )


def _shared_candidates(a: pd.DataFrame, b: pd.DataFrame, shared: list[str]) -> list[list[str]]:
    if not shared:
        return []
    candidates_a = detect_candidate_keys(a[shared])
    candidates_b = {tuple(candidate) for candidate in detect_candidate_keys(b[shared])}
    return [candidate for candidate in candidates_a if tuple(candidate) in candidates_b]


def _validated_keys(keys: list[str], shared: list[str]) -> list[str]:
    if not keys:
        raise ValueError("keys needs at least one column")
    if len(set(keys)) != len(keys):
        raise ValueError("key columns must not repeat")
    missing = [column for column in keys if column not in shared]
    if missing:
        label = ", ".join(missing)
        raise ValueError(f"key column not present in both tables: {label}")
    return list(keys)


def _prepare_shared_columns(
    a: pd.DataFrame,
    b: pd.DataFrame,
    shared: list[str],
    types_a: dict[str, ColType],
    types_b: dict[str, ColType],
) -> tuple[dict[str, _PreparedColumn], dict[str, _PreparedColumn]]:
    prepared_a = {}
    prepared_b = {}
    for column in shared:
        target = types_b[column]
        prepared_a[column] = _prepare_column(a[column], column, target)
        prepared_b[column] = _prepare_column(b[column], column, target)
    return prepared_a, prepared_b


def _prepare_column(series: pd.Series, name: str, target: ColType) -> _PreparedColumn:
    typed = coerce(pd.DataFrame({name: series}), {name: target})[name]
    failed = series.notna() & typed.isna()
    return _PreparedColumn(raw=series, typed=typed, failed=failed)


def _row_diff(
    raw_a: pd.DataFrame,
    raw_b: pd.DataFrame,
    shared: list[str],
    keys: list[str],
    prepared_a: dict[str, _PreparedColumn],
    prepared_b: dict[str, _PreparedColumn],
    *,
    source_a: str,
    source_b: str,
    sample_limit: int,
    include_values: bool,
) -> tuple[RowDiff | None, str | None]:
    tokens_a = [_row_token(prepared_a, keys, position) for position in range(len(raw_a))]
    tokens_b = [_row_token(prepared_b, keys, position) for position in range(len(raw_b))]
    label = ", ".join(keys)
    if len(set(tokens_a)) != len(tokens_a):
        warning = f"duplicate key values for {label!r} in {source_a} — row-level diff skipped"
        return None, warning
    if len(set(tokens_b)) != len(tokens_b):
        warning = f"duplicate key values for {label!r} in {source_b} — row-level diff skipped"
        return None, warning

    positions_a = {token: position for position, token in enumerate(tokens_a)}
    positions_b = {token: position for position, token in enumerate(tokens_b)}
    added_tokens = [token for token in tokens_b if token not in positions_a]
    removed_tokens = [token for token in tokens_a if token not in positions_b]
    common_tokens = [token for token in tokens_a if token in positions_b]
    compared_columns = [column for column in shared if column not in keys]

    changed = 0
    unchanged = 0
    changed_by_column: dict[str, int] = {}
    changed_samples: list[dict[str, Any]] = []
    for token in common_tokens:
        position_a = positions_a[token]
        position_b = positions_b[token]
        row_changed = False
        for column in compared_columns:
            if _values_equal(prepared_a[column], position_a, prepared_b[column], position_b):
                continue
            row_changed = True
            changed_by_column[column] = changed_by_column.get(column, 0) + 1
            if include_values and len(changed_samples) < sample_limit:
                changed_samples.append(
                    {
                        "key": _key_sample(raw_b, position_b, keys),
                        "col": column,
                        "old": _sample_value(raw_a.at[position_a, column]),
                        "new": _sample_value(raw_b.at[position_b, column]),
                    }
                )
        if row_changed:
            changed += 1
        else:
            unchanged += 1

    samples = {
        "added": [_row_sample(raw_b, positions_b[token]) for token in added_tokens[:sample_limit]]
        if include_values
        else [],
        "removed": [
            _row_sample(raw_a, positions_a[token]) for token in removed_tokens[:sample_limit]
        ]
        if include_values
        else [],
        "changed": changed_samples,
    }
    return (
        RowDiff(
            key_columns=list(keys),
            added=len(added_tokens),
            removed=len(removed_tokens),
            changed=changed,
            unchanged=unchanged,
            changed_by_column=changed_by_column,
            samples=samples,
        ),
        None,
    )


def _row_token(
    prepared: dict[str, _PreparedColumn], keys: list[str], position: int
) -> tuple[tuple[str, Any], ...]:
    return tuple(_value_token(prepared[column], position) for column in keys)


def _value_token(column: _PreparedColumn, position: int) -> tuple[str, Any]:
    raw = column.raw.iat[position]
    if _is_missing(raw):
        return ("missing", None)
    if bool(column.failed.iat[position]):
        return ("raw", str(raw))
    return ("typed", _sample_value(column.typed.iat[position]))


def _values_equal(a: _PreparedColumn, position_a: int, b: _PreparedColumn, position_b: int) -> bool:
    raw_a = a.raw.iat[position_a]
    raw_b = b.raw.iat[position_b]
    missing_a = _is_missing(raw_a)
    missing_b = _is_missing(raw_b)
    if missing_a or missing_b:
        return missing_a and missing_b

    failed_a = bool(a.failed.iat[position_a])
    failed_b = bool(b.failed.iat[position_b])
    if failed_a or failed_b:
        return failed_a and failed_b and str(raw_a) == str(raw_b)
    return bool(a.typed.iat[position_a] == b.typed.iat[position_b])


def _drift_report(
    a: pd.DataFrame,
    b: pd.DataFrame,
    shared: list[str],
    types_a: dict[str, ColType],
    types_b: dict[str, ColType],
    *,
    include_values: bool,
) -> DriftReport:
    categorical = {}
    numeric = {}
    for column in shared:
        if ColType.CATEGORICAL in {types_a[column], types_b[column]}:
            values_a = {str(value) for value in a[column].dropna().unique()}
            values_b = {str(value) for value in b[column].dropna().unique()}
            new = sorted(values_b - values_a)
            vanished = sorted(values_a - values_b)
            categorical[column] = CategoricalDrift(
                new_count=len(new),
                vanished_count=len(vanished),
                new=new if include_values else [],
                vanished=vanished if include_values else [],
            )

        if types_a[column] in _NUMERIC_TYPES and types_b[column] in _NUMERIC_TYPES:
            flagged = scan_column(a[column], column_name=column).kinds
            if _DRIFT_EXCLUDED_PII & set(flagged):
                continue
            values_a = coerce(a[[column]], {column: types_a[column]})[column].dropna()
            values_b = coerce(b[[column]], {column: types_b[column]})[column].dropna()
            mean_a, std_a = _mean_std(values_a)
            mean_b, std_b = _mean_std(values_b)
            mean_delta = mean_b - mean_a
            numeric[column] = {
                "mean_delta": mean_delta,
                "std_delta": std_b - std_a,
                "mean_pct_change": mean_delta / mean_a * 100 if mean_a else 0.0,
            }
    return DriftReport(categorical=categorical, numeric=numeric)


def _mean_std(values: pd.Series) -> tuple[float, float]:
    numeric = values.astype("float64")
    if numeric.empty:
        return 0.0, 0.0
    mean = float(numeric.mean())
    std = float(numeric.std()) if len(numeric) > 1 else 0.0
    return mean, std


def _null_pct(series: pd.Series) -> float:
    return float(series.isna().mean() * 100) if len(series) else 0.0


def _key_sample(frame: pd.DataFrame, position: int, keys: list[str]) -> dict[str, Any]:
    return {column: _sample_value(frame.at[position, column]) for column in keys}


def _row_sample(frame: pd.DataFrame, position: int) -> dict[str, Any]:
    return {str(column): _sample_value(value) for column, value in frame.iloc[position].items()}


def _sample_value(value: Any) -> Any:
    if _is_missing(value):
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, "item"):
        return value.item()
    return value


def _is_missing(value: Any) -> bool:
    missing = pd.isna(value)
    return bool(missing) if not isinstance(missing, (pd.Series, pd.DataFrame)) else False
