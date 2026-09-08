# fde-fieldkit — agent notes

The FDE toolkit: a small `fieldkit` core (CLI shell, shared table IO + PII scanning,
web hub, plugin manager) with seven tools shipped as plugin packages under
`plugins/fieldkit-<tool>` (xray, scrub, mimic, datadiff, debrief, tell, netwatch). A uv
workspace ties them together; a dev `uv sync` installs everything, end users
`fieldkit plugin add <tool>`. The suite runs local by default. Configured detector
keys never authorize `tell` egress on their own: a CLI run needs `--remote`, a Python
caller needs `offline=False`, and the web flow needs its one-use confirmation. The
local model may download only after the user explicitly opts in. `netwatch` is the
other narrow exception: it relays only traffic initiated by the command a user
explicitly runs through its loopback proxy, under the selected policy.

## Commands

```
uv sync                  # workspace install: core + all seven plugins, editable
uv run pytest -q         # root tests + every plugin's tests; green before you're done
uv run ruff check .      # must be clean before you're done
uv run fieldkit --help
uv run fieldkit plugin list
```

## Hard rules

- You are working one work package at a time. The spec in `specs/` names the exact files
  you may create or edit. **Do not touch anything else.** `src/fieldkit/core/` is frozen
  after WP0 — if you genuinely need a core fix, make the smallest possible change and call
  it out clearly in your final message so the reviewer sees it.
- Plugin packages import `fieldkit.core.*` and the upload helpers in
  `fieldkit.web.routes` only. Never import one plugin from another.
- A plugin's `web.py` adapts its tool to HTTP (`router` + `STATIC_DIR`); no business
  logic there. The hub (`src/fieldkit/web/app.py`) mounts whatever entry points exist —
  it must never name a tool.
- A new tool = a new `plugins/fieldkit-<name>` package (entry points
  `fieldkit.plugins` → typer app, `fieldkit.web` → web module) plus one registry line in
  `src/fieldkit/plugins.py` and a dev-group entry in the root pyproject.
- **Do not run `git commit` or `git add`.** Leave the working tree dirty; the orchestrator
  reviews the diff and commits.
- No new dependencies beyond what's in pyproject.toml unless the spec says so.
- Runtime code makes zero network calls except `tell` remote adapters and Netwatch's explicit
  proxy relay. Environment keys alone never activate an adapter: each CLI run needs
  `fieldkit tell check --remote`, while the web flow needs its payload/session/vendor-bound
  one-use confirmation. Python adapter helpers default offline and
  require explicit `offline=False`. Every egress path names its destinations. Netwatch binds
  only to loopback, sends no telemetry, never installs a CA, and opens an upstream connection
  only for a destination requested by the supervised command and allowed by the selected
  policy.
  The optional `ml` extra may download model weights only after the user passes the
  explicit `--ml` flag. Faker data generation is local.

## Style

- Write like a senior engineer, not a code generator. Comments are sparse and earn their
  place — explain the weird bit, not the obvious line. No docstrings on trivial functions.
- Practical error messages: `raise ValueError("can't detect a format for 'foo.bin' — pass fmt=")`,
  not ceremony.
- Type hints on public functions. Dataclasses in core/tools; pydantic only in `web/`.
- Tests are plain pytest — functions, fixtures, `tmp_path`. Table-driven where it helps.
