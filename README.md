# Fieldkit

[Documentation](https://fde-tools.vercel.app/docs/) · [Contributing](CONTRIBUTING.md) · [Changelog](CHANGELOG.md) · [Security](SECURITY.md)

The FDE toolkit: one install, then add the tools you need as plugins.

It is built for forward-deployed engineers, for the days you get handed a
mystery CSV, a locked-down laptop, and a Friday status deadline. Eight tools
ship today: profile a file, scrub the PII out of it, fake a demo dataset, diff
two dumps, keep a running debrief, check a draft for AI tells, watch what
your coding agent connects to, and check an AI workload spec before you share
it. The tools run locally by default, with no telemetry. Remote text
classifiers, model downloads, package installation, and supervised network relays
require the explicit actions described below.

## Install

Not on PyPI yet. From a checkout of this repo, with
[uv](https://docs.astral.sh/uv/) installed:

```
uv sync
uv run fieldkit --help
```

That one `uv sync` installs the core and all eight plugins, editable. Every
command below is `uv run fieldkit ...`; activate `.venv` if you would rather
drop the prefix. Python 3.12 or newer.

To install the toolkit from locally built wheels:

```
uv build --all-packages -o dist
uv venv --seed --python 3.12 fresh
uv pip install --python fresh/bin/python dist/fieldkit-0.2.0-py3-none-any.whl
fresh/bin/fieldkit plugin add xray scrub --wheelhouse dist
fresh/bin/fieldkit plugin add netwatch --wheelhouse dist
```

These commands build Fieldkit wheels, not a complete offline dependency bundle.
The installer may still contact a package index for dependencies. For an
air-gapped machine, prepare compatible wheels for the complete dependency set
and an offline installer separately; `--wheelhouse` alone does not disable
network access.

## Sixty seconds with each tool

Sample data lives in `examples/`.

### xray: what is this file?

```
uv run fieldkit xray examples/customers.csv
uv run fieldkit xray examples/customers.csv --html profile.html
```

```
customers.csv · CSV · 150 × 14
┃ column      ┃ type        ┃ nulls % ┃     distinct ┃ top value ┃ PII flags   ┃
│ customer_id │ id_like     │    0.0% │ 150 (100.0%) │ —         │ —           │
│ email       │ text        │    0.0% │ 150 (100.0%) │ —         │ EMAIL 1.00  │
│ ssn         │ id_like     │    0.0% │ 150 (100.0%) │ —         │ SSN 1.00    │
│ notes       │ text        │   24.0% │  114 (76.0%) │ —         │ —           │
```

Schema, inferred types, null rates, distinct counts, and a PII flag with a
confidence for every column. Reads csv, tsv, xlsx, json, and jsonl (UTF-8).
Pass `--fmt` when detection is wrong or the extension is misleading. Parquet and
other columnar formats are not supported. Inputs are capped at 50 MB total
(`MAX_DATASET_BYTES`); larger files fail with an error that names the limit.
`--html` writes a report you can hand over; `--json profile.json` writes the
same thing for machines. Sample values are redacted unless you pass
`--include-values`.

### scrub: take the PII out before you share it

```
uv run fieldkit scrub examples/customers.csv -o customers_safe.csv
uv run fieldkit scrub examples/app.log -o app_safe.log --text
```

```
     Replacements
┃ Kind        ┃ Count ┃
│ email       │   150 │
│ phone       │   150 │
│ ssn         │   150 │
│ credit_card │   150 │
│ ip          │   150 │
│ name        │   300 │
```

Emails, phones, SSNs, card numbers, IPs, names, and secrets become realistic
fakes. It is deterministic: the same input value always maps to the same fake,
so joins across files still line up. `--text` is line mode for logs.
`--kinds email,phone` narrows it, and `--mapping` writes the reversal key, which
is as sensitive as the original file. Detection is not a guarantee. Common names
can collide with dictionary hits, and free-text notes are only scrubbed where the
scanner finds a match — read the output before you send it.

### mimic: demo data that looks real

```
uv run fieldkit mimic learn examples/customers.csv -o spec.yaml
uv run fieldkit mimic generate spec.yaml -n 10000 --seed 42 -o demo.csv
```

```
wrote spec.yaml
wrote demo.csv (10000 rows)
```

`learn` writes a plain YAML spec: types, category pools, distributions. Edit it,
then generate as many rows as you need. Same seed, same output. PII columns get
independent fake values, never fingerprints of the source. Learned `unique`
flags for email/phone/ssn/card/ip mirror whether the sample column was unique,
and generation retries to keep that promise. In a hurry, skip the spec:

```
uv run fieldkit mimic generate examples/customers.csv -n 500 -o demo.csv
```

### datadiff: what changed between these dumps?

```
uv run fieldkit datadiff examples/customers.csv examples/customers_v2.csv
```

```
customers.csv (150 rows) → customers_v2.csv (152 rows)
┃ change  ┃ column ┃ old     ┃ new     ┃
│ added   │ region │ —       │ present │
│ removed │ ssn    │ present │ —       │
│ type    │ seats  │ INTEGER │ FLOAT   │
         Rows · key: customer_id
┃ added ┃ removed ┃ changed ┃ unchanged ┃
│    12 │      10 │      25 │       115 │
```

Schema changes, then row adds, removes, and edits keyed on a column it detects
for you (`--key customer_id` to override, comma-separated for compound keys),
then per-column drift. Raw row values stay redacted by default.

### debrief: log it now, report it Friday

```
uv run fieldkit debrief add "shipped ingestion pipeline to prod" --tag win
uv run fieldkit debrief add "waiting on VPN access for staging" --tag blocker
uv run fieldkit debrief report
```

```
# Weekly Status

**2026-W36 · Aug 31 – Sep 6, 2026**

## Wins

- shipped ingestion pipeline to prod

## Blockers & Asks

- waiting on VPN access for staging
```

Tags are `win`, `blocker`, `decision`, `note`, and `next`. `report` prints a
stakeholder-ready week in markdown, or `--html status.html`. Entries live in `~/.fieldkit/debrief.db`, or wherever `FIELDKIT_DEBRIEF_DB`
points (same idea as Netwatch's `FIELDKIT_NETWATCH_DB`).

### tell: find the AI tells in a draft

```
uv run fieldkit tell check draft.md
uv run fieldkit tell adapters
```

```
71 words · 7 sentences · 4 paragraphs · mean sentence 10.1 words
NOTICE  Phrase tells   tell-density 0.94   2 overrepresented phrases found
STRONG  Recap ending   tell-density 1.00   final paragraph opens with "in conclusion"
Remote classifier scores
│ Pangram     │ skipped │ offline mode │
│ GPTZero     │ skipped │ offline mode │
```

Ten local stylometric checks, each reported on its own instead of being rolled
into a verdict. These signals and third-party scores do not establish who wrote
a draft. Remote detectors (Pangram, GPTZero, Originality, Copyleaks,
Sapling, Winston, ZeroGPT) stay off unless you set their keys and pass
`--remote` for that run, and the CLI names every destination before any text
leaves the machine. An optional `ml` extra adds a local RoBERTa detector behind
`--ml`; the tell docs page has the install.

### netwatch: where did this agent connect?

```
uv run fieldkit netwatch doctor
uv run fieldkit netwatch run -- codex
uv run fieldkit netwatch run -- claude
```

```
$ uv run fieldkit netwatch run -- codex --version
netwatch session 0f6af3ca44b94eae97021ce595fd1883
HTTP http://127.0.0.1:60573 · SOCKS socks5h://127.0.0.1:60574 · audit · codex
codex-cli 0.144.5

session 0f6af3ca44b94eae97021ce595fd1883 · complete · audit · 0 network event(s)
· 0 tool event(s)
```

`run` starts loopback-only HTTP and SOCKS5 proxies, launches the command with
invocation-local Codex or Claude Code settings (your global config is never
edited), and records what it connected to: host, port, scope, decision, bytes.
No bodies, no headers, no query strings, no TLS interception, no certificate
authority. `doctor` prints exactly what this machine can and cannot capture.
`sessions` and `report <id>` bring a run back later.

Audit mode is the default and never blocks. Enforcement needs a policy:

```
uv run fieldkit netwatch policy init netwatch-policy.json
uv run fieldkit netwatch policy add netwatch-policy.json --action allow --id openai --host api.openai.com
uv run fieldkit netwatch policy check netwatch-policy.json https://example.com
uv run fieldkit netwatch run --mode enforce --policy netwatch-policy.json -- codex
```

```
$ uv run fieldkit netwatch policy check netwatch-policy.json https://example.com
blocked: example.com:443 (104.20.23.154) · no rule matched; policy default is deny
$ uv run fieldkit netwatch policy check netwatch-policy.json https://api.openai.com
allowed: api.openai.com:443 (162.159.140.245) · matched openai
```

Rules match hosts, wildcard hosts, IPs and CIDRs, ports, and protocols. Deny
wins over allow. Private and loopback targets need an allow rule with
`allow_private: true`; the starter policy allows loopback and denies the rest.
`examples/netwatch-policy.json` is a worked example.

Limits, stated plainly: DNS, UDP and QUIC, and sockets from software that
ignores proxies are not seen. `netwatch attach <pid>` samples the sockets of a
process that is already running and cannot block anything. Whole-machine
enforcement on macOS would need a signed Network Extension, which this is not.

### awcp: is this workload spec honest enough to share?

```
uv run fieldkit awcp check examples/awcp/support-ticket-triage.yaml
uv run fieldkit awcp diff examples/awcp/support-ticket-triage.yaml examples/awcp/support-ticket-triage-v2.yaml
uv run fieldkit awcp eval examples/awcp/support-ticket-triage.yaml --suite examples/awcp/support-triage-golden.yaml
```

```
support-ticket-triage · customer-success-ai · ok
config  sha256:bada678688eef6c479f592f47f2f682541a8be62b4c5c6f0a1f9fb205b953839
prompts 2 (system=content, userTemplate=content)
┃ name                      ┃ approval ┃ risk                                  ┃
│ jira.create_internal_note │ none     │ —                                     │
│ zendesk.draft_reply       │ required │ —                                     │
│ denied                    │ —        │ zendesk.send_reply, customer_db.write │
local check only — no model, control plane, or network call
```

`check` loads a WorkloadSpec (YAML or JSON), validates the shape, fingerprints
config and prompt files, and lists declared tools with approval and risk.
`diff` is a categorized spec diff. `eval` scores a recorded golden suite
against the spec's gates; it compares stored actual/expected values or explicit
scores. It does not call a model, run promptfoo, or talk to a control plane.
`--json PATH` and `--html PATH` write the same result for tickets and scripts.

## The plugin manager

```
fieldkit plugin list
fieldkit plugin add xray scrub --wheelhouse dist
fieldkit plugin remove xray
fieldkit plugin update netwatch
```

`add` resolves a tool from the checkout you are running in when there is one,
otherwise from this repository's git subdirectory (PyPI only once the packages
are published). `--wheelhouse <dir>` selects local Fieldkit wheels; other
dependencies may still be retrieved from a package index. It does not make
an install offline. `update` reinstalls only the tools you name (or everything
installed) and leaves the core alone.

A tool you have not added tells you how to get it, and exits 2:

```
$ fieldkit xray
'xray' is a Fieldkit tool that isn't installed yet.
  fieldkit plugin add xray
```

## The web hub

```
uv run fieldkit serve
```

Open http://127.0.0.1:8765. Every installed tool gets a drag-and-drop page;
tools you have not added show dimmed with their `plugin add` command. The
server binds to 127.0.0.1 only, answers 400 to any other `Host` header, and
refuses cross-origin writes with 403. Handy when you are pairing with someone
who does not live in a terminal.

## The tools

| tool | what it does | status |
|---|---|---|
| xray | Profile any table in seconds | shipped |
| scrub | Find and mask PII before sharing | shipped |
| mimic | Generate realistic fake datasets | shipped |
| datadiff | Explain why two tables disagree | shipped |
| debrief | Turn field notes into reports | shipped |
| tell | Inspect a draft's writing patterns, locally | shipped |
| netwatch | Observe and control agent network access | shipped |
| awcp | Check workload specs, diff versions, score golden evals | shipped |

## Site and docs

The product site is https://fde-tools.vercel.app, with a page per tool
under https://fde-tools.vercel.app/docs/. It is static, loads nothing
from third parties, and its command blocks are contract-tested against this
README by `python3 site/check_site.py`.

## How it stays local

No telemetry, no update checks, no analytics, in the CLI or the hub. Analysis
runs locally except for these actions you explicitly request:

- `tell check --remote` sends the draft to the detector services whose keys
  you set, and names them first. Keys alone never trigger it. The web flow
  requires a one-use confirmation for the selected text and vendors; Python
  adapter callers must pass `offline=False`.
- `netwatch run` relays the connections the supervised command asks for,
  through loopback proxies, under your policy. It is a deliberate relay for
  someone else's traffic, and it never phones home itself.

The optional `tell check --ml` detector may download model weights on first
use, then evaluates the text locally. Installing Fieldkit or adding plugins
also retrieves packages. These downloads are separate from sending a draft
to a detector service.

## Blueprint skill

The repository also includes `fde-blueprint`, a planning skill discovered by
Codex and Claude Code. It interviews an engineer, validates the answers, and
writes an architecture and implementation packet with pending evidence. It
does not generate application code or register a `fieldkit blueprint` command.

```sh
python3 skills/fde-blueprint/scripts/blueprint.py questions --format json
python3 skills/fde-blueprint/scripts/blueprint.py interview --output answers.json
python3 skills/fde-blueprint/scripts/blueprint.py render --answers answers.json --output blueprint --dry-run
```

The [skill instructions](skills/fde-blueprint/SKILL.md) cover packet review and
rendering. Its product catalog is a dated set of candidates, not a license or
procurement approval; verify a selected product's current terms before reuse.

## Contributing

```
uv sync
uv run pytest -q
uv run ruff check .
python3 site/check_site.py
```

The repo is a uv workspace. The core in `src/fieldkit` is the CLI shell, shared
table IO and PII scanning, the web hub, and the plugin manager. Each tool is its
own package under `plugins/fieldkit-<tool>` with its own dependencies, web
module, static page, and tests. A ninth tool is one new package there plus one
line in the registry in `src/fieldkit/plugins.py`. `AGENTS.md` has the house
rules.

Built with pandas, FastAPI, typer, rich, and Faker. The web UI is plain HTML,
CSS, and JavaScript with no build step.

## License

Fieldkit is available under the [MIT License](LICENSE). Bundled third-party
materials retain their own notices; see [Third-party notices](THIRD_PARTY_NOTICES.md).

## Support

Maintained by [@myrrazor](https://github.com/myrrazor) and contributors.
Use [GitHub issues](https://github.com/myrrazor/fde-fieldkit/issues) for reproducible
bugs and feature requests. Report vulnerabilities privately through
[GitHub Security Advisories](https://github.com/myrrazor/fde-fieldkit/security/advisories/new).

This is early development software. Package version 0.2.0 describes the current
source; it is not a claim of a PyPI release, a hosted account service, or
whole-machine network enforcement. The included examples are synthetic.
Read the [fixture notes](tests/fixtures/README.md) before substituting real data.
