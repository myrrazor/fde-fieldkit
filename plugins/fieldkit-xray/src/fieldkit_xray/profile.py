from __future__ import annotations

import json
from dataclasses import asdict, dataclass

import pandas as pd

from fieldkit.core.io import LoadedTable
from fieldkit.core.pii import PIIColumnReport, scan_dataframe
from fieldkit.core.types import ColType, coerce, infer_types


@dataclass
class NumericStats:
    """Descriptive statistics for one numeric column."""

    min: float
    max: float
    mean: float
    median: float
    std: float
    p5: float
    p95: float


@dataclass
class ColumnProfile:
    """Type, quality, distribution, and PII details for one column."""

    name: str
    inferred_type: str
    null_count: int
    null_pct: float
    distinct_count: int
    distinct_pct: float
    top_values: list[tuple[str, int]]
    numeric: NumericStats | None
    outlier_count: int
    outlier_examples: list[str]
    pii: dict[str, float]


@dataclass
class ProfileResult:
    """A complete profile for one loaded table."""

    source: str
    fmt: str
    row_count: int
    column_count: int
    columns: list[ColumnProfile]
    warnings: list[str]


def profile_table(
    table: LoadedTable, *, top_k: int = 10, include_values: bool = False
) -> ProfileResult:
    """Build a profile, omitting source values unless explicitly requested."""

    if top_k < 1:
        raise ValueError("top_k must be at least 1")

    raw = table.df
    inferred = infer_types(raw)
    typed = coerce(raw, inferred)
    pii_reports = scan_dataframe(raw)
    row_count = len(raw)

    columns = [
        _profile_column(
            str(name),
            raw[name],
            typed[name],
            inferred[str(name)],
            pii_reports[str(name)],
            row_count=row_count,
            top_k=top_k,
            include_values=include_values,
        )
        for name in raw.columns
    ]
    return ProfileResult(
        source=table.source,
        fmt=table.fmt,
        row_count=row_count,
        column_count=len(raw.columns),
        columns=columns,
        warnings=[
            *table.warnings,
            *(
                []
                if include_values
                else [
                    "raw top values and outlier examples omitted; "
                    "use the CLI --include-values flag only for an authorized report"
                ]
            ),
        ],
    )


def to_json(result: ProfileResult) -> str:
    """Serialize a profile with deterministic field ordering and two-space indentation."""

    return json.dumps(asdict(result), indent=2, sort_keys=True)


def _profile_column(
    name: str,
    raw: pd.Series,
    typed: pd.Series,
    col_type: ColType,
    pii_report: PIIColumnReport,
    *,
    row_count: int,
    top_k: int,
    include_values: bool,
) -> ColumnProfile:
    null_count = int(raw.isna().sum())
    distinct_count = int(raw.nunique(dropna=True))
    # card/ssn/phone columns parse as numbers, but their "stats" are noise
    if {"credit_card", "ssn", "phone"} & {kind.value for kind in pii_report.kinds}:
        numeric, outlier_count, outlier_examples = None, 0, []
    else:
        numeric, outlier_count, outlier_examples = _numeric_profile(
            raw, typed, col_type, include_values=include_values
        )

    top_values = (
        [
            (str(value), int(count))
            for value, count in raw.value_counts(dropna=True).head(top_k).items()
        ]
        if include_values
        else []
    )
    pii = {
        kind.value: float(confidence)
        for kind, confidence in sorted(pii_report.kinds.items(), key=lambda item: item[0].value)
    }
    pii["hit_rate"] = float(pii_report.hit_rate)

    return ColumnProfile(
        name=name,
        inferred_type=col_type.value,
        null_count=null_count,
        null_pct=_percentage(null_count, row_count),
        distinct_count=distinct_count,
        distinct_pct=_percentage(distinct_count, row_count),
        top_values=top_values,
        numeric=numeric,
        outlier_count=outlier_count,
        outlier_examples=outlier_examples,
        pii=pii,
    )


def _numeric_profile(
    raw: pd.Series,
    typed: pd.Series,
    col_type: ColType,
    *,
    include_values: bool,
) -> tuple[NumericStats | None, int, list[str]]:
    if col_type not in {ColType.INTEGER, ColType.FLOAT}:
        return None, 0, []

    values = typed.dropna().astype("float64")
    q1 = float(values.quantile(0.25))
    q3 = float(values.quantile(0.75))
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outliers = (typed < lower) | (typed > upper)
    outliers = outliers.fillna(False)

    stats = NumericStats(
        min=float(values.min()),
        max=float(values.max()),
        mean=float(values.mean()),
        median=float(values.median()),
        std=float(values.std()) if len(values) > 1 else 0.0,
        p5=float(values.quantile(0.05)),
        p95=float(values.quantile(0.95)),
    )
    return (
        stats,
        int(outliers.sum()),
        [str(value) for value in raw.loc[outliers].head(5)] if include_values else [],
    )


def _percentage(part: int, total: int) -> float:
    return part / total * 100 if total else 0.0
