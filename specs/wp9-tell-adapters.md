# WP9 — tell: opt-in detector adapters

Read AGENTS.md. Remote egress is an explicit exception for `tell` only: adapters are
disabled unless their environment keys are present, offline mode performs no socket work,
and the CLI warns on stderr before sending text anywhere.

## Files you may create/edit

```
src/fieldkit/tell/adapters.py
src/fieldkit/tell/ml.py
src/fieldkit/tell/cli.py
src/fieldkit/tell/render.py
pyproject.toml
uv.lock
AGENTS.md
README.md
tests/test_tell_adapters.py
specs/wp9-tell-adapters.md
```

`uv.lock` is the derived lockfile for the requested dependency metadata change.

## Adapter contract

```python
class AdapterStatus(StrEnum): RAN; SKIPPED; ERROR

@dataclass(frozen=True)
class DetectorRequest:
    text: str
    timeout: float = 20.0

@dataclass(frozen=True)
class DetectorSpan:
    start: int
    end: int
    score: float

@dataclass(frozen=True)
class DetectorResult:
    adapter: str
    display_name: str
    status: AdapterStatus
    ai_probability: float | None
    label: str
    spans: list[DetectorSpan]
    detail: str
    latency_ms: float

@dataclass(frozen=True)
class Adapter:
    name: str
    display_name: str
    env_vars: tuple[str, ...]
    min_chars: int
    max_chars: int
    call: AdapterCall
```

`ADAPTERS` has a fixed order: Pangram, GPTZero, Originality, Copyleaks, Sapling,
Winston, ZeroGPT. Parsers normalize only the documented score field:

- Pangram `ai_likelihood`;
- GPTZero `documents[0].class_probabilities.ai`;
- Originality `score.ai`;
- Copyleaks AI summary fraction;
- Sapling `score`;
- Winston human score 0–100, inverted to an AI probability;
- ZeroGPT `data.fakePercentage / 100`.

Vendor labels pass through unchanged. Malformed payloads, HTTP failures, and timeouts
become one `ERROR` row rather than aborting the report.

## Execution and privacy

```python
def run_detectors(
    text: str,
    *,
    offline: bool = True,
    include_ml: bool = False,
    timeout: float = 20.0,
    client: httpx.Client | None = None,
) -> list[DetectorResult]
```

Preflight happens before a client is created:

- omitted `offline` → every remote row is `SKIPPED`; Python callers must pass
  `offline=False` for an intentional vendor send;
- offline → every remote row is `SKIPPED` with `offline mode`;
- missing credentials → `SKIPPED` with `no <ENV> set`;
- below a vendor minimum → `SKIPPED` with `text under vendor minimum`;
- above a vendor maximum → `SKIPPED` with `text over vendor maximum`.

Eligible adapters fan out in a thread pool. Results return in registry order regardless
of completion order. A supplied `client` is never closed and is the test injection seam.

The optional local detector is `roberta-openai (local)`. It imports transformers only
when `--ml` is set. A missing extra produces `install with: uv sync --extra ml`; a run
includes a GPT-2-era limitation note. The first model download is therefore always behind
explicit user intent.

## CLI and dependency policy

```
fieldkit tell adapters
fieldkit tell check FILE [--remote] [--ml] [--timeout SECONDS] [--json PATH]
```

`adapters` shows environment-variable names and keyed yes/no without network work. Checks
are offline unless the user supplies `--remote` for that run. Before an eligible remote
call, `check` writes:

`sending text to N remote services: <names>`

to stderr. Local signal panels remain separate from a detector table; no score is averaged
or promoted to an overall verdict. Every remote adapter row appears in terminal and JSON
output, including skipped and error rows.

`httpx` moves into runtime dependencies. The `ml` extra contains transformers and torch.
README and AGENTS describe six tools, local-by-default behavior, the adapter exception,
and the explicit model-download flag.

## Acceptance

- Every adapter success fixture normalizes the requested score and preserves its label.
- HTTP 500 and timeout become `ERROR`.
- Missing keys and the default offline mode invoke no transport.
- Minimum-length checks invoke no transport.
- Results always include one row per registered remote adapter in fixed order.
- Default CLI output has explicit offline skipped rows, even when keys are configured.
- `uv run pytest -q` passes and `uv run ruff check .` is clean.
