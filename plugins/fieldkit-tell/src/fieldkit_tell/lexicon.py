"""Packaged phrase lists derived from petergyang/no-ai-slop (MIT)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

from fieldkit_tell.sentences import Span


@dataclass(frozen=True)
class Lexicon:
    banned_words: tuple[str, ...]
    swap_table: dict[str, str]
    empty_phrases: tuple[str, ...]
    puffery_table: dict[str, str]
    weasel_markers: tuple[str, ...]
    recap_openers: tuple[str, ...]


@lru_cache(maxsize=1)
def load_lexicon() -> Lexicon:
    """Load the bundled tell lexicon once per process."""

    source = resources.files("fieldkit_tell").joinpath("data", "lexicon.json")
    payload = json.loads(source.read_text(encoding="utf-8"))
    return Lexicon(
        banned_words=tuple(payload["banned_words"]),
        swap_table=dict(payload["swap_table"]),
        empty_phrases=tuple(payload["empty_phrases"]),
        puffery_table=dict(payload["puffery_table"]),
        weasel_markers=tuple(payload["weasel_markers"]),
        recap_openers=tuple(payload["recap_openers"]),
    )


def phrase_spans(text: str, phrases: tuple[str, ...] | list[str]) -> list[tuple[Span, str]]:
    """Find non-overlapping phrases case-insensitively, longest phrase first."""

    candidates: list[tuple[Span, str]] = []
    for phrase in sorted(phrases, key=lambda value: (-len(value), value)):
        pattern = re.compile(rf"(?<![\w-]){re.escape(phrase)}(?![\w-])", re.IGNORECASE)
        candidates.extend((Span(match.start(), match.end()), phrase) for match in pattern.finditer(text))

    selected: list[tuple[Span, str]] = []
    for span, phrase in sorted(candidates, key=lambda item: (item[0].start, -item[0].end)):
        if any(span.start < kept.end and kept.start < span.end for kept, _ in selected):
            continue
        selected.append((span, phrase))
    return selected
