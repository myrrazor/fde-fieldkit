# WP3 — mimic: synthetic data from a sample or spec

Read AGENTS.md. Core is frozen. The same spec + same seed must produce byte-identical
output. Recognized sensitive columns use independent generators. Portable specs must never
contain their source values or stable fingerprints; ordinary categorical strings and exact
distribution endpoints remain by design. Review the spec and generated data before sharing.

## Files you may create/edit

```
src/fieldkit/mimic/__init__.py
src/fieldkit/mimic/cli.py         # replace the stub
src/fieldkit/mimic/learn.py
src/fieldkit/mimic/generate.py
tests/test_mimic.py
```

## Spec format (YAML — hand-editable is the point)

```yaml
name: customers
rows_sampled: 150
columns:
  - name: customer_id
    kind: id_pattern          # digits→'#', letters→'?', literals kept: "CUST-####"
    params: {pattern: "CUST-####", start: 1}
    unique: true
    null_rate: 0.0
  - name: plan
    kind: categorical
    params: {values: {free: 0.5, pro: 0.3, enterprise: 0.2}}
  - name: mrr
    kind: numeric
    params: {quantiles: [20.0, 45.5, ...], decimals: 2}   # 21-point grid, p0..p100
  - name: signup_date
    kind: datetime
    params: {min: "2024-01-05", max: "2026-06-30", format: "%Y-%m-%d"}
  - name: email
    kind: email               # sensitive kinds always use source-free generators
  - name: churned
    kind: boolean
    params: {true_rate: 0.2}
  - name: notes
    kind: text
    params: {avg_words: 9}
    null_rate: 0.2
```

## learn.py

```python
def learn_spec(table: LoadedTable, *, name: str = "") -> MimicSpec
def load_spec(path: Path) -> MimicSpec
def dump_spec(spec: MimicSpec) -> str        # YAML, stable ordering
```

Uses `core.types.infer_types` + cell-level `core.pii.scan_text`:
- Any recognized sensitive cell makes the whole column source-free, including sparse
  email, phone, SSN, credit-card, IP, name, and secret matches. Sensitive values never
  become categorical keys, even when most cells in the column are ordinary labels.
- ID_LIKE strings → id_pattern (generalize: digit→`#`, ascii letter→`?`, keep literals;
  if all patterns identical use it, else fall back to the most common + unique counter
  suffix). ID_LIKE ints → id_pattern `{pattern: "####", start: max+1}`-style.
- CATEGORICAL → observed values + observed weights (2dp). Categories are fine to reuse
  — they're categories, not identities.
- INTEGER/FLOAT → 21-point quantile grid (p0, p5, …, p100) from the coerced column;
  decimals = max observed decimal places (0 for int).
- DATE/DATETIME → min/max + the dominant format string.
- BOOLEAN → observed true rate. TEXT → avg word count. EMPTY → null_rate 1.0.
- null_rate = observed per column (2dp).

## generate.py

```python
def generate(spec: MimicSpec, n: int, seed: int = 0, *, fmt: str = "csv") -> pd.DataFrame
def generate_serialized(spec: MimicSpec, n: int, *, seed: int = 0,
                        fmt: str = "csv") -> tuple[bytes, list[dict[str, Any]]]
```

One `random.Random(seed)` and one `Faker` with `seed_instance(seed)` drive everything;
iterate rows and then columns in spec order — fully deterministic and streamable. numeric: pick a
uniform position on the quantile grid and interpolate linearly (empirical shape, no
distribution fitting). id_pattern with unique: counter from `start`; without: random
digits/letters per mask. Nulls: rng.random() < null_rate. PII kinds use independent
Faker providers; secrets use deterministic values marked with a `fake_` prefix.
The browser path serializes rows incrementally and rejects output past the authoritative
50 MiB dataset size instead of allocating an attacker-shaped rows-by-columns frame.
Imported generator parameters are type/finite/range checked and compiled once; categorical
cumulative weights are reused rather than rebuilt for every generated row.

## cli.py

```
fieldkit mimic learn SAMPLE -o spec.yaml
fieldkit mimic generate SPEC_OR_SAMPLE -n 1000 [--seed 0] -o out.csv
```
`generate` accepts either a .yaml spec or a data file (one-shot: learn then generate).
Output format from `-o` extension (csv/tsv/jsonl/json/xlsx via core.io.write_table).
Prints "wrote out.csv (1000 rows)".

## Acceptance

- learn(customers.csv) → generate(n=500, seed=42): 500 rows, same columns in order;
  plan values ⊆ {free, pro, enterprise}; null rate of notes within ±5pp of source;
  mrr within [source min, source max]; customer_id all unique matching `CUST-\d{4,}`.
- Portable YAML contains neither source PII nor hashes of source PII.
- The deterministic fixture's generated email/name/phone values are disjoint from its
  source values, without claiming that all possible inputs can never collide.
- Same seed twice → byte-identical CSV; different seed → different.
- Hand-edit respected: learned spec with plan pool changed to {alpha: 1.0} generates
  only "alpha".
- One-shot `fieldkit mimic generate tests/fixtures/customers.csv -n 50 -o /tmp/x.jsonl`
  works and emits jsonl.
- pytest green, ruff clean.
