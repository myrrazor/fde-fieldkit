# WP10 — tell: deterministic un-slop rewrite

Read AGENTS.md. This work package makes no language-model calls. Automatic changes are
limited to conservative deletion and fixed table lookup; judgment calls remain explicit
suggestions.

## Files you may create/edit

```
src/fieldkit/tell/rewrite.py
src/fieldkit/tell/cli.py
src/fieldkit/tell/render.py
tests/test_tell_unslop.py
specs/wp10-tell-unslop.md
```

## Result model

```python
@dataclass(frozen=True)
class Edit:
    start: int; end: int; replacement: str; transform: str; note: str

@dataclass(frozen=True)
class Suggestion:
    start: int; end: int; excerpt: str; pattern: str
    advice: str; llm_instruction: str

@dataclass(frozen=True)
class IterationRecord:
    index: int; edits: list[Edit]; report: SignalReport

@dataclass(frozen=True)
class UnslopResult:
    original: str; final: str
    iterations: list[IterationRecord]; suggestions: list[Suggestion]

@dataclass(frozen=True)
class DiffOp:
    op: Literal["equal", "delete", "insert"]; text: str
```

Iteration edit offsets address the text before that iteration. Suggestion offsets always
address `UnslopResult.final`. `word_diff` uses `difflib.SequenceMatcher` over words,
punctuation, and preserved whitespace.

`LLMRewriter` is a documented `typing.Protocol` seam for a later opt-in implementation.
Version 1 never instantiates or calls it.

## Automatic transforms

`TRANSFORMS` has this priority order:

1. `banned_swap` — conservative swap table plus fixed fake-strong verb replacements;
2. `throat_clearing` — remove sentence-initial empty phrases and recapitalize;
3. `setup_deletion` — remove the “Here's the thing:” family of setup openers;
4. `recap_adverb` — remove only final-paragraph-initial “In conclusion,”, “Overall,”, or
   “Ultimately,”;
5. `puffery_table` — replace the fixed importance-inflation phrases;
6. `em_dash_normalize` — above the documented density floor, turn paired appositives into
   commas and clause-joining dashes into a period plus capitalization;
7. `formatting_cleanup` — in Markdown, remove emoji from headings and unbold bullet
   lead-ins.

Each transform returns source-coordinate `Edit` values. Overlaps resolve by transform
priority, then leftmost position. Selected edits splice right-to-left. The loop segments,
collects, resolves, applies, re-analyzes, and records; it stops at no edits or the
`max_iterations` cap (default 3).

## Suggestions only

The final text is scanned for ten judgment-required patterns:

- binary contrasts;
- colon reveals;
- trailing `-ing` pseudo-analysis clauses;
- unattributed authority;
- dramatic fragmentation;
- negative listing;
- rhetorical setup questions;
- fake-profound kickers;
- whole recap paragraphs;
- robotic rhythm.

Each match includes concrete editing advice and a ready-to-use future LLM instruction,
but never changes text automatically.

## CLI

```
fieldkit tell unslop FILE -o OUT [--max-iterations 3] [--diff] [--json PATH]
```

`-o` is required and cannot resolve to the input path. The output is written only after a
successful rewrite. `--diff` uses terminal insert/delete styling; JSON contains the
dataclass result plus the diff operations.

## Acceptance

- Every automatic transform has an exact input/output test.
- Priority overlap resolution keeps the higher-priority edit.
- A second pass over cleaned output produces zero edits.
- Repeated runs are byte-identical.
- The slop fixture loses all swap-table phrases, reduces em-dash density, has no strong
  phrase-tell or puffery result, retains judgment suggestions, and honors the iteration
  cap.
- CLI tests cover output, parseable JSON, stdin, missing output, and overwrite refusal.
- `uv run pytest -q` passes and `uv run ruff check .` is clean.
