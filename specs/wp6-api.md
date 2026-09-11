# WP6 — FastAPI layer + `fieldkit serve`

Read AGENTS.md. Core and all five tools are frozen — routes adapt existing functions to
HTTP, they do not reimplement logic. Stateless by design: uploads are processed in
memory and the response carries everything back; nothing is written server-side
(debrief's SQLite is the one exception, same file the CLI uses).

## Files you may create/edit

```
src/fieldkit/web/__init__.py
src/fieldkit/web/app.py
src/fieldkit/web/routes/__init__.py
src/fieldkit/web/routes/{xray,scrub,mimic,datadiff,debrief}.py
src/fieldkit/web/static/index.html          # placeholder hub — real UI comes in WP7
src/fieldkit/cli.py                          # ONLY the serve command body
tests/test_api.py
```

## app.py

```python
def create_app(*, debrief_db: Path | None = None) -> FastAPI
```
- Mounts the five routers under `/api`, serves `web/static/` at `/` (html=True).
- The accepted dataset/request size is 50 MiB total, including multipart framing. Enforce
  it before multipart parsing or disk spooling → 413
  `{"error": "request too large (50 MB total max)"}` (starlette won't do
  this for you — check content-length and the cumulative receive stream). XLSX logical,
  uncompressed content uses the same 50 MiB dataset contract before openpyxl loads it.
- Browser mutation requests are same-origin only. Every non-GET/HEAD/OPTIONS request must
  carry exactly one non-null `Origin` equal to `http://` plus the validated loopback Host,
  including its port. When `Sec-Fetch-Site` is present it must be `same-origin`. Missing,
  malformed, multiple, cross-site, and merely same-site origins fail with 403 before body
  parsing. The CLI does not call HTTP; there is intentionally no headerless API exception.
- Any ValueError from core/tools → 422 `{"error": str(e)}` via exception handler.
  Unexpected errors → 500 `{"error": "internal error"}` (don't leak tracebacks).
- `debrief_db` param exists so tests can point at a tmp db (dependency override or
  app.state — your call, keep it simple).
- CORS: none (same-origin only). No auth — this is a localhost tool.

## Routes

```
GET  /api/health                    → {"status": "ok", "version": fieldkit.__version__}

POST /api/xray                      multipart: file; query: output=json|html (default json)
                                    → ProfileResult as JSON dict | {"html": "..."}

POST /api/scrub                     multipart: file; form: kinds (csv string, optional),
                                    include_mapping (bool, default false)
                                    → {"summary": ScrubSummary dict,
                                       "file": {"filename": "scrubbed_<name>", "content_b64": ...},
                                       "mapping": {...} | null}
                                    Salt: load_or_create_salt() default path — the
                                    server reuses the operator's local salt.

POST /api/mimic/learn               multipart: file → {"spec_yaml": str}
POST /api/mimic/generate            multipart: file OR form spec_yaml; form: n (≤ 100_000),
                                    seed (default 0), fmt (csv|jsonl, default csv)
                                    → {"preview": [first 20 rows as dicts],
                                       "file": {"filename", "content_b64"}}

POST /api/datadiff                  multipart: file_a, file_b; form: keys (csv, optional)
                                    → DiffResult as JSON dict (incl. key_detection);
                                    query output=html → {"html": "..."}

GET    /api/debrief/entries?week=&tag=      → [Entry dicts]
POST   /api/debrief/entries {"text": str, "tag": str}   → Entry dict (201)
DELETE /api/debrief/entries/{id}            → 204 | 404 {"error": "no entry <id>"}
GET    /api/debrief/report?week=&fmt=md|html|json       → {"markdown": ...} | {"html": ...}
                                                          | ReportData dict; week defaults
                                                          to current ISO week
```

Pydantic request/response models where bodies are JSON; plain dicts from dataclasses
(`asdict`) are fine for responses. Filenames in Content-Disposition-style names must be
sanitized (basename only).

## cli.py serve

`fieldkit serve [--port]` binds 127.0.0.1 only (`host="127.0.0.1"`). The host is not configurable. With no `--port`, it prefers 8765 and falls back to a free port if that one is taken. `--port N` pins N and fails if it is busy. Print the URL that actually bound on startup.

## Acceptance (TestClient via httpx)

- health returns version.
- xray: upload customers.csv → 200, row_count 150; output=html contains "<html".
- scrub: upload customers.csv kinds=email → summary counts > 0, b64 decodes to a CSV
  with 150 data rows and no original email addresses; include_mapping=true → mapping
  non-empty, absent otherwise.
- mimic: learn returns YAML containing "customer_id"; generate n=25 → 25 preview rows
  ≤ 20 shown, file decodes to 25 rows.
- datadiff: the fixture pair → added 12 / removed 10 / changed 25 (same asserts as WP4,
  through HTTP).
- debrief: POST → GET shows it → report contains it → DELETE 204 → 404 on re-delete.
  All against a tmp db (no real home).
- Errors: 8-byte garbage file → 422 with "error" key; fake content-length > 50MB (or a
  real >50MB body if cheap to synthesize) → 413.
- `uv run fieldkit serve --help` works; app importable without starting a server.
- pytest green, ruff clean.
