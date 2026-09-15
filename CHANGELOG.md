# Changelog

Dates describe published GitHub releases. Fieldkit is not on PyPI; the PyPI
project named `fieldkit` is unrelated.

## Unreleased

## 0.2.0 — 2026-09-15

First public GitHub release of the Fieldkit 0.2.0 packages. Install the
core and all eight plugin wheels from
[GitHub Releases](https://github.com/myrrazor/fde-fieldkit/releases/latest).
This is not a PyPI publication and is not a 1.0 maturity claim.

### Fixes

- Tell sentence and Markdown recognition scans linearly instead of running
  suffix regexes on growing prefixes, so long digit/letter non-matches stay
  cheap. Abbreviations, initialisms, decimals, punctuation, and span offsets
  are unchanged.
- Tell's browser `/egress-intent` always issues a fresh server-generated
  session cookie. An attacker-chosen cookie is not reflected; confirmations
  still bind token, session, payload, and vendor set, and remain one-use.
- The static-site checker extracts JSON-LD script bodies with HTMLParser so
  messy closing tags cannot poison CSP hashes.
- Phone detection rejects ISO and EU/US dashed datetimes (`YYYY-MM-DD HH…`,
  `DD-MM-YYYY HH…`, `MM-DD-YYYY HH…`) so scrub/xray no longer abort on those
  columns; real phone numbers still match.
- Netwatch attach success-path tests mock `lsof` discovery so the suite stays
  green on machines without `lsof` installed.
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

### Docs

- README and the public site show real local-hub and tool screenshots with
  synthetic sample data, and link the GitHub Release.
- Public docs use https://fde-tools-review.vercel.app as the hosted site, with
  the in-repo `site/` tree as the fallback copy. They no longer describe that
  URL as SSO-gated.
- Install copy tells people to install every Fieldkit wheel by explicit local
  path, then use `--wheelhouse` for later plugin operations. A pinned `v0.2.0`
  source checkout remains supported.

### Toolkit

- `fieldkit serve` prefers loopback port 8765 and falls back to a free port
  when that one is taken. `--port N` still pins N and fails if it is busy.
  The command prints the URL that actually bound.
- A standalone FDE Blueprint planning skill with a questionnaire, validated
  answers, architecture packets, and explicit pending-evidence gates.
- A local CLI and browser hub with a uv workspace and independently installable
  xray, scrub, mimic, datadiff, debrief, tell, netwatch, and awcp plugins.
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

### Public release

- MIT licensing, third-party notices, contributor guidance, a code of conduct,
  and private security-reporting instructions.
- Reproducible GitHub Release packaging: nine wheels, nine sdists, a wheel
  bundle, `release-manifest.json`, and `SHA256SUMS`. Hatchling is pinned at
  1.32.0 for builds only.
- Public documentation distinguishes local behavior, explicit network access,
  generated sample evidence, and unsupported enforcement claims.

The public baseline intentionally starts with the accepted source snapshot.
Private development history and local test logs are not part of this release.
