# WP8 — tell: offline stylometric signal engine

Read AGENTS.md. Core stays frozen. `tell` is independent of every other tool package and
imports only standard-library modules plus `fieldkit.core.*` where shared infrastructure
is needed.

## Files you may create/edit

```
src/fieldkit/tell/__init__.py
src/fieldkit/tell/sentences.py
src/fieldkit/tell/lexicon.py
src/fieldkit/tell/signals.py
src/fieldkit/tell/render.py
src/fieldkit/tell/cli.py
src/fieldkit/tell/data/lexicon.json
src/fieldkit/cli.py
tests/test_tell_signals.py
tests/fixtures/slop_sample.md
tests/fixtures/human_sample.md
specs/wp8-tell-core.md
```

## Coordinate space and lexicon

`segment(text) -> Doc` is the one tokenizer used by every signal and later rewrite.
Sentence spans are absolute offsets into `Doc.text`; paragraph spans and words preserve
that same source coordinate system. The regex splitter guards common abbreviations such
as `Dr.`, `e.g.`, and `etc.` and handles Markdown headings and list items without a
runtime dependency.

`data/lexicon.json` packages the complete banned-word, conservative swap, empty-phrase,
puffery, weasel-marker, and recap-opener lists. The list is derived from the MIT-licensed
petergyang/no-ai-slop ruleset; loading is local and deterministic.

## Signal model

```python
class Severity(StrEnum): INFO; NOTICE; STRONG

@dataclass(frozen=True)
class Evidence:
    start: int; end: int; excerpt: str; note: str

@dataclass(frozen=True)
class SignalResult:
    signal: str; title: str; severity: Severity; score: float
    summary: str; evidence: list[Evidence]; stats: dict[str, int | float | str]

@dataclass(frozen=True)
class TextStats:
    chars: int; words: int; sentences: int; paragraphs: int
    mean_sentence_len: float; sentence_len_cv: float

@dataclass(frozen=True)
class SignalReport:
    text_stats: TextStats
    signals: list[SignalResult]
```

`score` is a bounded tell-density metric, never a probability that text was written by
AI. `SignalReport` deliberately has no aggregate or overall verdict.

`SIGNALS` is a fixed tuple of ten pure `Doc -> SignalResult` functions:

1. sentence-length burstiness;
2. lexicon phrase tells;
3. em-dash density and sentence clusters;
4. binary contrast constructions;
5. prose colon reveals;
6. importance puffery;
7. unattributed-authority weasel markers;
8. paragraph/list structural uniformity;
9. recap endings and opening/final n-gram overlap;
10. Markdown formatting slop.

Every signal is returned, including clean `INFO` rows. Thresholds live beside the
implementation and favor false negatives over labeling ordinary prose.

## CLI and rendering

```
fieldkit tell check FILE [--remote] [--json PATH]
```

`FILE` may be `-` for stdin. The terminal header includes text statistics and this
caveat before any signal panels:

> Stylometric tells are patterns overrepresented in machine text, but they also appear
> in human writing. Historical prose and non-native writers can trigger them.

The renderer emits one compact Rich panel per signal and uses the danger style family
for `STRONG`. Remote adapters remain off unless `--remote` is supplied for that run.
Errors use the suite's clean `error: ...` stderr format.

## Acceptance

- Table-driven goldens cover severity and evidence counts for all ten signals.
- Segmentation keeps abbreviation and Markdown boundaries in absolute coordinates.
- The planted slop fixture produces at least four `STRONG` signals.
- The messy human negative control produces zero `STRONG` signals.
- JSON contains every signal and no aggregate/overall field.
- `fieldkit tell check tests/fixtures/slop_sample.md` renders all ten signals offline.
- `uv run pytest -q` passes and `uv run ruff check .` is clean.
