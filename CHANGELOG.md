# Changelog

Changes are recorded here before a version is tagged. Dates describe published
releases only; this repository does not claim a package release that has not happened.

## Unreleased

The current source packages use version **0.2.0**. No public release tag or PyPI
publication is implied by that number.

### Fixes

- Phone detection no longer treats ISO-like datetimes (`YYYY-MM-DD HH…`) as
  phone numbers; scrubbing `tests/fixtures/inventory.xlsx` succeeds.
- `fieldkit --version` / `-V` prints the package version.
- Tell's plugin registry blurb matches the README (writing patterns, not
  authorship detection).
- `plugin add --source pypi` fails with an honest "not published yet" error;
  `--wheelhouse` help no longer claims a full offline install.
- Table tools accept `--fmt`; unsupported parquet / non-UTF-8 inputs fail
  clearly instead of silent mis-detection. The hard 50 MB `MAX_DATASET_BYTES`
  limit is named in errors and README/xray help.
- Netwatch zero-event complete runs warn that the child may have bypassed the
  proxy; attach without `lsof` fails before pretending success.
- Hub: `/tool` redirects to `/tool/`; OpenAPI `/docs`/`/redoc` disabled on the
  loopback UI; debrief rejects empty notes and honors `FIELDKIT_DEBRIEF_DB`.
- Mimic learns email/phone/ssn/card/ip uniqueness from the sample and enforces
  it when generating.

### Toolkit

- `fieldkit serve` prefers loopback port 8765 and falls back to a free port
  when that one is taken. `--port N` still pins N and fails if it is busy.
  The command prints the URL that actually bound.
- A standalone FDE Blueprint planning skill with a questionnaire, validated
  answers, architecture packets, and explicit pending-evidence gates.
- A local CLI and browser hub with a uv workspace and independently installable
  xray, scrub, mimic, datadiff, debrief, tell, and netwatch plugins.
- Table profiling for CSV, TSV, Excel, JSON, and JSONL; raw samples are redacted
  unless the caller explicitly requests values.
- Deterministic PII replacement, reversible mapping exports, and synthetic data
  generation from editable specifications.
- Schema, keyed-row, and distribution comparisons, plus local weekly status notes.
- Local writing signals, optional remote detector adapters with explicit consent,
  and an optional local model path.
- Netwatch loopback proxies, destination policies, observation-only process
  attachment, local session evidence, and a browser control room.
- awcp: local WorkloadSpec checks, version diffs, and golden-suite scoring.
  It does not call a model or a delivery control plane.

### Public release preparation

- MIT licensing, third-party notices, contributor guidance, a code of conduct,
  and private security-reporting instructions.
- Package descriptions and source links, fixture provenance, and automated checks
  for repository privacy, secrets, dependencies, documentation, and distributions.
- Public documentation distinguishes local behavior, explicit network access,
  generated sample evidence, and unsupported enforcement claims.

The public baseline intentionally starts with the accepted source snapshot.
Private development history and local test logs are not part of this release.
