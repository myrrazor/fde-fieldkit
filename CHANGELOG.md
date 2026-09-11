# Changelog

Changes are recorded here before a version is tagged. Dates describe published
releases only; this repository does not claim a package release that has not happened.

## Unreleased

The current source packages use version **0.2.0**. No public release tag or PyPI
publication is implied by that number.

### Toolkit

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
