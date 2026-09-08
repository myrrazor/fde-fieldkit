# WP1 — xray: instant data profiler

Read AGENTS.md. Core is frozen — you consume `fieldkit.core.*`, you don't edit it.

## Files you may create/edit

```
src/fieldkit/xray/__init__.py
src/fieldkit/xray/cli.py          # replace the stub
src/fieldkit/xray/profile.py
src/fieldkit/xray/render.py
src/fieldkit/xray/templates/xray.html
tests/test_xray.py
```

## profile.py

```python
@dataclass
class NumericStats:
    min: float; max: float; mean: float; median: float; std: float; p5: float; p95: float

@dataclass
class ColumnProfile:
    name: str
    inferred_type: str               # ColType value
    null_count: int; null_pct: float
    distinct_count: int; distinct_pct: float
    top_values: list[tuple[str, int]]        # up to top_k, by count desc
    numeric: NumericStats | None             # INTEGER/FLOAT only
    outlier_count: int                       # 1.5×IQR rule, numeric cols only
    outlier_examples: list[str]              # up to 5
    pii: dict                                # PIIColumnReport as plain dict (kind -> confidence), plus hit_rate

@dataclass
class ProfileResult:
    source: str; fmt: str
    row_count: int; column_count: int
    columns: list[ColumnProfile]
    warnings: list[str]

def profile_table(table: LoadedTable, *, top_k: int = 10) -> ProfileResult
def to_json(result: ProfileResult) -> str          # stable key order, 2-space indent
```

Flow: `infer_types` → `coerce` for stats; nulls/distinct/top-k computed on the raw
string frame (post-NA-normalization). top_values stringified. Keep it one pass, no
cleverness — files fit in memory.

## render.py

- `render_terminal(result, console)` — rich: a summary line (source, fmt, rows × cols)
  then one table: column | type | nulls % | distinct | top value | PII flags. PII flags
  as comma-joined kinds with confidence, e.g. `EMAIL .98`. Red style when confidence ≥ 0.9.
- `render_html(result) -> str` — via `core.report.render_page` with `xray.html`
  extending base.html: summary strip + a per-column table incl. numeric stats and top-5
  values. Self-contained, printable.

## cli.py

`fieldkit xray FILE [--json PATH] [--html PATH] [--top-k 10] [--sheet NAME] [--include-values]`
Terminal render always; `--json`/`--html` additionally write files and print
"wrote PATH" lines. Raw top values and outlier examples are omitted by default.
`--include-values` is an explicit per-invocation opt-in for an authorized sensitive
report; the browser does not expose this option. Non-existent file → clean error,
exit 1. Exit 0 on success.

## Acceptance

- All five formats profile without error:
  `for f in customers.csv events.jsonl orders.json inventory.xlsx messy.tsv` →
  `uv run fieldkit xray tests/fixtures/$f`.
- Asserts on customers.csv: row_count 150; email column pii contains EMAIL ≥ 0.9;
  plan top_values are redacted by default; notes null_pct ≈ 20 (±5); seats numeric stats present;
  mrr outlier_count ≥ 0.
- messy.tsv: legacy_code inferred EMPTY, null_pct == 100.
- to_json → json.loads round-trips; `--json`/`--html` write non-empty files, HTML
  contains every column name.
- pytest green, ruff clean.
