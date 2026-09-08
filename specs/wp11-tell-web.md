# WP11 — tell: web workbench and printable report

Read AGENTS.md. Keep local stylometric signals and remote classifier scores as separate
evidence classes. There is no aggregate verdict anywhere in this work package.

## Files you may create/edit

```
src/fieldkit/tell/cli.py
src/fieldkit/tell/render.py
src/fieldkit/tell/templates/tell.html
src/fieldkit/web/routes/tell.py
src/fieldkit/web/app.py
src/fieldkit/web/static/tell/index.html
src/fieldkit/web/static/tell/app.js
src/fieldkit/web/static/index.html
tests/test_api.py
specs/wp11-tell-web.md
```

## Printable report

`render_html(report, detectors, *, rewrite=None)` uses the shared report environment
through a `ChoiceLoader` for the tell template. The report is self-contained and
printable. It renders:

- source statistics and a fixed honesty preamble;
- a remote-checker table with every row, its run/skip/error state, normalized score
  where available, verbatim vendor label, detail, and latency;
- all ten stylometric signal sections with severity, summary, score/stats, and marked
  evidence;
- when a rewrite is supplied, its iteration history with per-signal before/after
  severity, word-level insert/delete diff, judgment-only suggestions, and final text.

The preamble says that stylometric tells are patterns overrepresented in machine text
but also present in human writing, including historical prose and writing by non-native
speakers. It says local tell-density scores are not P(AI), and it keeps vendor
probabilities in a separate section. No template computes or displays a composite.

`fieldkit tell check` gains `--html PATH`. The same check run supplies the terminal,
JSON, and HTML outputs, so remote services are never called a second time just to render
the report.

## HTTP routes

All three handlers are synchronous `def` endpoints so FastAPI runs blocking detector
work in its threadpool.

```
GET  /api/tell/adapters
POST /api/tell/egress-intent
POST /api/tell/check[?output=html]
POST /api/tell/unslop
```

`GET /adapters` reports only adapter names, display names, environment-variable names,
and key presence, plus optional local-model availability. It makes no network request.

`POST /check` accepts multipart `text` XOR `file`, where uploads are UTF-8 `.txt` or
`.md`. Form options are `offline` (true by default), `ml`, positive `timeout`, and an
egress token. The browser obtains that opaque token from `/egress-intent` only after an
explicit user action. It is bound to the browser session, exact text digest, and exact
eligible vendor set, then consumed once. A direct or replayed remote check fails with
403. Issuing another intent replaces the previous one, so the process retains only the
immediate action. The route returns `asdict()` data for `SignalReport` and every `DetectorResult`;
`output=html` adds the report string. The remote registry remains complete for run,
skipped, and error outcomes.

`POST /unslop` accepts the same text XOR file input and `max_iterations` from 1 through
10. It returns `asdict()` data for `UnslopResult`, a lossless word diff, and a base64
text file named `unslopped_<safe stem>.txt`.

XOR, extension, decoding, and bounds failures raise `ValueError`, which the existing
application handler returns as 422. Uploads use the shared size limit and filename
sanitizer. Routes only validate transport input and adapt tool dataclasses; all analysis,
detector, rewrite, and diff logic remains in `fieldkit.tell`.

## Browser workbench

The page keeps the suite's field-paper shell and implements the complete draft workflow:

1. a persistent local/remote honesty strip and CLI example;
2. labeled text entry, `.txt`/`.md` dropzone, character count, offline and explicit local
   ML controls, plus live adapter key status;
3. offline is checked by default; every enabled remote submission requires a native
   confirmation naming the exact eligible destinations;
4. a complete checker table, including muted skipped rows with their exact remedies;
5. ten signal controls and one source-text view built from server-provided absolute spans;
   selecting a signal filters highlights without reparsing text;
6. a deterministic un-slop result with severity transition timeline, word diff,
   judgment-only suggestion marks, final text, copy, and `.txt` download.

Loading, validation, empty, skipped, error, keyboard-focus, narrow-screen, and
reduced-motion states use the existing shared helpers and tokens. User content is escaped
before insertion. HTML reports are generated in the initial check request and downloaded
without a second detector run.

The hub gains tool 06 and updates its local-default language so it does not contradict
tell's opt-in remote adapters.

## Acceptance

- Adapter status has the documented shape and never opens a socket.
- Default `/check` returns all remote rows as offline-skipped, in registry order.
- Remote `/check` rejects missing, mismatched, cross-session, and replayed egress tokens.
- HTML output contains the honesty preamble, all checker names, and all ten signals.
- `/unslop` returns a lossless diff and decodable cleaned-text file.
- text XOR file violations and unsupported uploads return 422.
- The browser names remote destinations before submission and renders server offsets
  without client-side signal parsing.
- Hub card 06 links to `/tell/` with the requested copy.
- `uv run pytest -q` passes and `uv run ruff check .` is clean.
