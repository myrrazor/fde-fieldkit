# WP4 — datadiff: schema-aware diff of two dumps

Read AGENTS.md. Core is frozen. The fixture pair customers.csv / customers_v2.csv was
engineered for this tool — the acceptance numbers below are exact, not approximate.

## Files you may create/edit

```
src/fieldkit/datadiff/__init__.py
src/fieldkit/datadiff/cli.py      # replace the stub
src/fieldkit/datadiff/diff.py
src/fieldkit/datadiff/render.py
src/fieldkit/datadiff/templates/datadiff.html
tests/test_datadiff.py
```

## diff.py

```python
def detect_candidate_keys(df: pd.DataFrame) -> list[list[str]]
    # unique + fully non-null single columns (ID_LIKE ranked before others).
    # Composite keys are explicit through --key rather than enumerated.

@dataclass
class SchemaDiff:
    added_columns: list[str]
    removed_columns: list[str]
    type_changes: list[tuple[str, str, str]]        # col, old, new (ColType values)
    nullability_changes: list[tuple[str, float, float]]  # col, old null_pct, new null_pct (delta > 5pp only)

@dataclass
class RowDiff:
    key_columns: list[str]
    added: int; removed: int; changed: int; unchanged: int
    changed_by_column: dict[str, int]
    samples: dict   # {"added": [row dicts], "removed": [...], "changed": [{"key":…, "col":…, "old":…, "new":…}]} capped at sample_limit

@dataclass
class DriftReport:
    categorical: dict[str, dict]     # col -> {"new": [...], "vanished": [...]}
    numeric: dict[str, dict]         # col -> {"mean_delta": float, "std_delta": float, "mean_pct_change": float}

@dataclass
class DiffResult:
    source_a: str; source_b: str
    rows_a: int; rows_b: int
    schema: SchemaDiff
    rows: RowDiff | None             # None when no usable key
    drift: DriftReport
    key_detection: dict              # {"auto": bool, "candidates": [["customer_id"], ...]}
    warnings: list[str]

def diff_tables(a: LoadedTable, b: LoadedTable, *, keys: list[str] | None = None,
                sample_limit: int = 20, include_values: bool = False) -> DiffResult
def to_json(result: DiffResult) -> str
```

Semantics that matter:
- **Row comparison happens on coerced (typed) values over shared columns** with the
  types inferred per-side. If a column's type differs between sides, compare on the
  *string* values only when both sides' coercion fails; otherwise coerce both sides to
  the newer side's type where possible. Net effect for the fixtures: seats "12" vs
  "12.0" is a type change, NOT a changed row. NA == NA counts as equal.
- keys param wins; otherwise detect single columns on the shared columns of both frames
  (a candidate must be unique + non-null in BOTH). Composite-key enumeration is avoided
  because its work and output grow quadratically with schema width; pass an explicit
  comma-separated `--key` for a composite. No candidate → rows=None + warning
  "no usable key — row-level diff skipped (pass --key)".
- Duplicate key values on either side → drop to rows=None with a warning naming the key.
- Drift is computed over shared columns on full column values (not just changed rows):
  categorical = categories present in b but not a ("new") / in a but not b ("vanished");
  numeric = mean/std deltas + pct change (guard div-by-zero).

## render.py + template

- `render_terminal(result, console)` — rich: schema section (added/removed/type/null
  changes), row section (counts + changed_by_column table), drift section. Green/red
  accents for added/removed.
- `render_html(result) -> str` — datadiff.html extends base.html; same sections plus
  sample tables (changed samples show key, column, old → new).

## cli.py

```
fieldkit datadiff OLD NEW [--key col[,col]] [--json PATH] [--html PATH] [--sheet NAME]
                           [--include-values]
```
Terminal render always; exit 0 even when diffs exist (it's a report, not a gate);
exit 1 on load errors.

Raw row samples and categorical labels are omitted by default while their counts remain.
`--include-values` is an explicit per-invocation opt-in for an authorized sensitive
report; the browser does not expose this option.

## Acceptance (exact, per fixture engineering)

Run on `tests/fixtures/customers.csv` vs `tests/fixtures/customers_v2.csv`:
- schema: added_columns == ["region"], removed_columns == ["ssn"],
  type_changes contains ("seats", "INTEGER", "FLOAT").
- key_detection: auto == True, first candidate == ["customer_id"].
- rows: added == 12, removed == 10, changed == 25, unchanged == 115.
- changed_by_column: {"mrr": 25, "plan": 8} and nothing else.
- drift: plan new category count == 1 with values redacted; mrr mean_pct_change > 0.
- Keyless path: diff messy.tsv against itself with keys=None-detection disabled by
  duplicate/whitespace — simpler: construct two tiny frames with no unique column in
  the test → rows is None + warning present.
- to_json round-trips; --json/--html files written, HTML contains "region" and "ssn".
- pytest green, ruff clean.
