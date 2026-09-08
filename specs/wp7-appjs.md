# WP7 — the five tool-page app.js files

Read AGENTS.md. The HTML pages, CSS, and shared helpers already exist and are the
design source of truth — do not edit any .html or .css file, and do not edit
fieldkit.js. You are writing exactly five files:

```
src/fieldkit/web/static/xray/app.js
src/fieldkit/web/static/scrub/app.js
src/fieldkit/web/static/mimic/app.js
src/fieldkit/web/static/datadiff/app.js
src/fieldkit/web/static/debrief/app.js
```

ES modules, vanilla JS, no libraries. Import from `/fieldkit.js`:

```js
esc(v)                         // html-escape — use it on EVERY interpolated value
api(url, {method, body})      // fetch wrapper; throws Error with a human message
dropzone(el, onFile)          // wires click/keyboard/drag; stores file on el.file
fmtBytes(n)
renderTable(rows, columns)    // columns: [{key, label, className?, render?}] -> html string
downloadB64(file)             // file = {filename, content_b64}
downloadText(filename, text)
toast(message)                // error toast, use in every catch
withBusy(container, label, task)  // spinner while task() runs
```

Every page already has `<section id="result" aria-live="polite"></section>` (except
debrief, which has its own structure). Render results as a `.report` panel:

```html
<div class="report">
  <div class="report-head"><span class="title">…</span><div class="actions">…buttons…</div></div>
  <div class="report-body">…</div>
</div>
```

Inside report bodies use the existing classes: `.label-eng` section labels,
`.stat-row`/`.stat` (`<div class="stat"><div class="n">150</div><div class="k">rows</div></div>`),
`renderTable` for tables, `.badge badge-type|badge-pii|badge-ok|badge-warn|badge-info`,
`.note-warn`, `.empty`. Numbers right-aligned via `className: "num"`, data values
`"mono"`. Wrap every network call in try/catch → `toast(err.message)`.

## API contracts (exact, verified against the running server)

- `POST /api/xray` multipart `file` → `{source, fmt, row_count, column_count, warnings: [],
  columns: [{name, inferred_type, null_count, null_pct, distinct_count, distinct_pct,
  top_values: [[value, count], …], numeric: {min,max,mean,median,std,p5,p95}|null,
  outlier_count, outlier_examples: [], pii: {hit_rate, <kind>: <confidence>, …}}]}`
  — pii kinds are every key except `hit_rate`.
- `POST /api/xray?output=html` → `{html}` (full standalone report document).
- `POST /api/scrub` multipart `file` + form `kinds` (csv string, optional) +
  `include_mapping` ("true"/"false") → `{summary: {replaced: {kind: n},
  by_column: {col: {kind: n}}}, file: {filename, content_b64}, mapping: {orig: fake}|null}`.
- `POST /api/mimic/learn` multipart `file` → `{spec_yaml}`.
- `POST /api/mimic/generate` form `spec_yaml` + `n` + `seed` + `fmt` (csv|jsonl)
  → `{preview: [{col: value, …}, …], file: {filename, content_b64}}` (preview ≤ 20 rows).
- `POST /api/datadiff` multipart `file_a`, `file_b` + form `keys` (csv, optional) →
  `{source_a, source_b, rows_a, rows_b,
  schema: {added_columns, removed_columns, type_changes: [[col, old, new]…],
           nullability_changes: [[col, old_pct, new_pct]…]},
  rows: null | {key_columns, added, removed, changed, unchanged,
                changed_by_column: {col: n},
                samples: {added: [rowdict…], removed: [rowdict…],
                          changed: [{key, column, old, new}…]}},
  drift: {categorical: {col: {new: [], vanished: []}}, numeric: {col: {mean_delta, std_delta, mean_pct_change}}},
  key_detection: {auto, candidates: [[col…]…]}, warnings: []}`
- debrief: `GET /api/debrief/entries?week=YYYY-Www` → `[{id, ts, tag, text}]`;
  `POST /api/debrief/entries` json `{text, tag}` → entry (201);
  `DELETE /api/debrief/entries/{id}` → 204;
  `GET /api/debrief/report?week=&fmt=md|html` → `{markdown}` / `{html}`.

## Per page

### xray
On file drop: withBusy → POST /api/xray → render report.
- report-head: filename title; actions: "Download JSON" (downloadText of
  `JSON.stringify(result, null, 2)`), "Download HTML report" (second call with
  `?output=html`, downloadText of `.html`).
- body: stat-row (rows, columns, format, PII columns count = columns with any pii
  kind); if warnings, a `.note-warn` listing them; then the columns table:
  column (mono) · type (badge-type) · nulls % · distinct · top value (mono, show
  `value (count)` for top_values[0], blank if none) · PII (badge-pii per kind with
  confidence like `EMAIL 1.00`, em dash if none).
- Numeric columns: append a second table "numeric detail" for columns where
  numeric != null: column · min · p5 · median · mean · p95 · max · outliers.
- Clearing the file chip (× button) empties #result and hides the chip.

### scrub
Populate #kinds with 7 `.check-pill` checkboxes (email, phone, ssn, credit_card,
ip, name, secret), all checked. #mapping toggle shows/hides #mapping-warn. Enable
#go once a file is picked. On Scrub: POST with selected kinds → report:
- head: `scrubbed_<name>` title; actions: "Download scrubbed file" (downloadB64),
  plus "Download mapping" (downloadText of JSON, only when mapping present).
- body: stat-row of totals by kind from summary.replaced; "by column" table
  (column · kind · values replaced); then a before/after preview for tabular files:
  parse the FIRST 6 data rows of the original file client-side (naive CSV parse is
  fine: handle quoted fields with a ~15-line parser; skip preview entirely for
  xlsx/json/jsonl/log — only preview csv/tsv) and the same rows from the decoded
  scrubbed output; render two stacked tables labeled "before" / "after" with
  changed cells given `className` via render: compare cell to the before value and
  wrap changed ones in `<span class="cell-changed">`… simpler: give the after-table
  td the class `cell-changed` by rendering `<td>` content through a render fn that
  wraps changed values in a `<mark class="cell-changed">`-free span — easiest
  correct approach: build the after table with renderTable and a render function
  that returns `changed ? '<span class="badge badge-warn">'+esc(v)+'</span>' : esc(v)`.
  Cap at 8 columns; add a note "first 6 rows · first 8 columns" underneath.

### mimic
On file drop: withBusy → /api/mimic/learn → fill #spec textarea, reveal
#spec-section. On Generate: POST /api/mimic/generate with the CURRENT textarea
content (user may have edited), n, seed, fmt → report:
- head: file.filename; actions "Download file" (downloadB64).
- body: stat-row (rows generated = n, seed, format); preview table of the preview
  rows (all columns, values mono) with note "first 20 rows".
- Validate n client-side (1..100000) before posting; invalid → toast.

### datadiff
Enable #go when both files picked. On Diff: POST with optional keys → report:
- head: `old → new` filenames; no actions.
- body in order:
  1. stat-row: rows before, rows after, +added / -removed / ~changed when rows
     present.
  2. If warnings: `.note-warn` with each warning.
  3. "schema" label + table of changes (kind badge: added→badge-ok,
     removed→badge-pii, type→badge-warn, nullability→badge-info · column · detail
     like `INTEGER → FLOAT` or `null % 2.0 → 11.5`). Empty → `.empty` "no schema
     changes".
  4. If rows: "rows · key: <key>" label (+ badge-info "auto-detected" when
     key_detection.auto) + changed_by_column table + up to 5 changed samples
     (key · column · old → new, mono).
     If rows is null: `.note-warn` explaining no usable key and suggesting the
     key field, listing key_detection.candidates if any.
  5. "drift" label + one table: column · kind (categorical/numeric badge-type) ·
     detail (`new: starter` / `mean Δ +23.09 (+7.7%)`, format numbers to 2–4
     significant digits). Empty → `.empty`.
- If key_detection.candidates non-empty and #keys is blank, set #keys placeholder
  to the first candidate joined by commas.

### debrief
On load: set #week to the current ISO week (`input type=week` value format
"2026-W29" — same string the API takes) and refresh().
refresh(): GET entries for the week → render into #entries as a table
(time `HH:MM ddd` mono · tag badge (win→badge-ok, blocker→badge-pii,
decision→badge-info, note→badge-type, next→badge-warn) · text · delete
btn-danger "×" with aria-label) or `.empty` "nothing logged this week yet."; then
GET report?fmt=html and inject `{html}`'s BODY content into #report-body
(strip everything outside <body>…</body> — the endpoint returns a full document),
reveal #report-section, set #report-title to "weekly status · <week>".
- Add form submit: POST entry (tag from checked radio), clear input, refresh().
- Delete: DELETE entry, refresh().
- Week input change: refresh().
- "Copy markdown": GET report?fmt=md → navigator.clipboard.writeText; flip the
  button label to "Copied" for 1.5s. "Download .md": downloadText
  `status-<week>.md`.

## Acceptance

- `uv run ruff check .` clean (ruff ignores js — just don't break the repo) and
  `uv run pytest -q` still green (you're not touching python, it must stay green).
- Serve manually and verify each page end-to-end with tests/fixtures files:
  xray on customers.csv; scrub on customers.csv (mapping on and off) and app.log;
  mimic learn+generate on customers.csv; datadiff on the fixture pair (auto key)
  and with keys=customer_id; debrief add/list/delete/report round-trip.
- Every dynamic string goes through esc() or renderTable. No innerHTML of raw API
  strings except the debrief report html (our own template) and report-head titles
  built with esc().
- No console errors on any page.
