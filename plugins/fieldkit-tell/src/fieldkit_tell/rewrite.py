from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal, Protocol

from fieldkit_tell.lexicon import load_lexicon, phrase_spans
from fieldkit_tell.sentences import Doc, Span, segment
from fieldkit_tell.signals import Severity, SignalReport, analyze


@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    replacement: str
    transform: str
    note: str


@dataclass(frozen=True)
class Suggestion:
    start: int
    end: int
    excerpt: str
    pattern: str
    advice: str
    llm_instruction: str


@dataclass(frozen=True)
class IterationRecord:
    index: int
    edits: list[Edit]
    report: SignalReport


@dataclass(frozen=True)
class UnslopResult:
    original: str
    final: str
    iterations: list[IterationRecord]
    suggestions: list[Suggestion]


@dataclass(frozen=True)
class DiffOp:
    op: Literal["equal", "delete", "insert"]
    text: str


class LLMRewriter(Protocol):
    """Future opt-in seam. The deterministic v1 pipeline never calls this protocol."""

    def rewrite(self, text: str, suggestions: Sequence[Suggestion]) -> str:
        """Return a reviewed rewrite for the supplied judgment-only suggestions."""

        ...


Transform = Callable[[Doc], list[Edit]]

_PLAIN_SWAPS = {
    "delve": "examine",
    "foster": "support",
    "empower": "enable",
    "streamline": "simplify",
    "robust": "reliable",
    "cutting-edge": "new",
    "paradigm shift": "major change",
    "game changer": "major change",
    "game-changer": "major change",
    "tapestry": "mix",
    "realm": "area",
    "beacon": "guide",
    "multifaceted": "varied",
    "meticulous": "careful",
    "intricate": "complex",
    # "main" reads attributive-only ("planning is main" is broken english)
    "paramount": "essential",
    "transformative": "major",
    "elevate": "improve",
    "embark": "start",
    "supercharge": "improve",
    "harness": "use",
    "ever-evolving": "changing",
}
_SETUP_PHRASES = (
    "here's the thing",
    "the reality is",
    "the truth is",
    "let me be clear",
    "i'll be honest",
    "the uncomfortable truth is",
)
_OBJECT_TAKING_OPENERS = (
    "when it comes to",
    "in the world of",
    "in the age of",
)
_RECAP_ADVERBS = ("in conclusion", "overall", "ultimately")
_FENCE_START_RE = re.compile(
    r"(?m)^[ \t]{0,3}(?P<fence>`{3,}|~{3,})[^\r\n]*(?:\r?\n|$)"
)
_BACKTICK_RUN_RE = re.compile(r"`+")
_EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]\ufe0f?")
_BOLD_BULLET_RE = re.compile(
    r"(?m)^(?:[ \t]*(?:[-+*]|\d+[.)])\s+)\*\*(?P<label>[^*\n]{1,40}:)\*\*"
)
_TOKEN_RE = re.compile(r"\s+|[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*|.", re.DOTALL)
_TRAILING_ING_RE = re.compile(
    r",\s+(?:highlighting|underscoring|showcasing|demonstrating|reflecting|"
    r"reinforcing|emphasizing|illustrating)\b[^.!?]{0,140}[.!?]",
    re.IGNORECASE,
)
_BINARY_RE = (
    re.compile(
        r"\b(?:it|this|that)(?:['’]s|\s+is)\s+not\s+just\b"
        r"[^.!?\n—]{2,100}(?:—|[.]|,\s+but\b|\s+but\b)\s*"
        r"(?:it|this|that)(?:['’]s|\s+is)\b[^.!?\n]{1,100}",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bnot\s+[^.!?\n]{2,80}[.!?]\s+"
        r"(?:it|this|that)(?:['’]s|\s+is)\s+[^.!?\n]{2,100}",
        re.IGNORECASE,
    ),
)
_FAKE_KICKER_RE = re.compile(
    r"\b(?:the future is clear|that is the point|and that changes everything|"
    r"this is only the beginning|let that sink in|the choice is ours)\b",
    re.IGNORECASE,
)

_SUGGESTION_COPY = {
    "binary_contrast": (
        "State the claim directly; the mirrored setup adds drama without evidence.",
        "Rewrite this contrast as one direct, specific claim. Preserve the facts and remove "
        "the not-X / but-Y framing.",
    ),
    "colon_reveal": (
        "Turn the setup and reveal into an ordinary sentence unless the compression earns it.",
        "Rewrite this colon reveal as a plain declarative sentence without adding claims.",
    ),
    "trailing_ing": (
        "Name the actual consequence instead of attaching a vague -ing interpretation.",
        "Replace the trailing -ing clause with a concrete consequence supported by the text, "
        "or remove it.",
    ),
    "weasel_attribution": (
        "Name the source and finding, or remove the appeal to unnamed authority.",
        "Replace the vague authority claim with a cited, specific source. If none is present, "
        "delete the claim.",
    ),
    "dramatic_fragmentation": (
        "Join the fragment to the sentence it qualifies unless the pause carries real meaning.",
        "Combine this dramatic fragment with its neighboring sentence while keeping the same "
        "facts and tone.",
    ),
    "negative_listing": (
        "Replace the repeated negatives with the positive requirement or observed failure.",
        "Condense this sequence of negative statements into one concrete positive requirement "
        "or factual description.",
    ),
    "rhetorical_question": (
        "Ask only if the reader must answer; otherwise state the answer directly.",
        "Replace this rhetorical setup question with its direct answer using only information "
        "already in the draft.",
    ),
    "fake_profound_kicker": (
        "End on the concrete next step or consequence, not a universal-sounding flourish.",
        "Replace this kicker with the specific consequence or next action established in the "
        "draft.",
    ),
    "whole_recap": (
        "Keep only new consequences or next steps; the reader does not need the opening again.",
        "Remove repeated opening claims from this final paragraph. Keep only new decisions, "
        "consequences, or next steps.",
    ),
    "robotic_rhythm": (
        "Vary sentence length where the ideas call for it; do not vary rhythm mechanically.",
        "Revise this run so sentence boundaries follow the ideas. Combine or split sentences "
        "without changing meaning.",
    ),
    "object_opener": (
        "Keep the object or recast the sentence; deleting only this opener breaks the subject.",
        "Rewrite this object-taking opener as a direct sentence without dropping its object "
        "or changing the claim.",
    ),
}


def unslop(text: str, *, max_iterations: int = 3) -> UnslopResult:
    """Apply deterministic edits until stable, then collect judgment-only suggestions."""

    if max_iterations < 1:
        raise ValueError("max_iterations must be at least 1")

    current = text
    iterations: list[IterationRecord] = []
    for index in range(1, max_iterations + 1):
        protected = _markdown_code_spans(current)
        doc = segment(_mask_spans(current, protected))
        candidates = [edit for transform in TRANSFORMS for edit in transform(doc)]
        candidates = [
            edit
            for edit in candidates
            if not _intersects_any(Span(edit.start, edit.end), protected)
        ]
        edits = resolve_edits(candidates)
        if not edits:
            break
        current = _apply_edits(current, edits)
        iterations.append(IterationRecord(index, edits, analyze(current)))

    suggestions = collect_suggestions(segment(current))
    return UnslopResult(text, current, iterations, suggestions)


def banned_swap(doc: Doc) -> list[Edit]:
    """Replace banned phrases through fixed, intentionally plain lookup tables."""

    lexicon = load_lexicon()
    table = {**_PLAIN_SWAPS, **lexicon.swap_table}
    edits: list[Edit] = []
    for span, phrase in phrase_spans(doc.text, list(table)):
        if phrase == "leverage" and not _looks_like_leverage_verb(doc.text, span):
            continue
        if phrase == "made a decision" and not re.match(
            r"\s+to\b", doc.text[span.end :], re.IGNORECASE
        ):
            continue
        replacement = _match_case(doc.text[span.start : span.end], table[phrase])
        edits.append(
            Edit(
                span.start,
                span.end,
                replacement,
                "banned_swap",
                f"fixed swap: {phrase} → {table[phrase]}",
            )
        )
    return edits


def throat_clearing(doc: Doc) -> list[Edit]:
    unsafe = {*_SETUP_PHRASES, *_OBJECT_TAKING_OPENERS}
    phrases = tuple(
        phrase for phrase in load_lexicon().empty_phrases if phrase not in unsafe
    )
    return _opener_edits(
        doc,
        doc.sentences,
        phrases,
        transform="throat_clearing",
        note="removed empty sentence opener",
    )


def setup_deletion(doc: Doc) -> list[Edit]:
    return _opener_edits(
        doc,
        doc.sentences,
        _SETUP_PHRASES,
        transform="setup_deletion",
        note="removed rhetorical setup opener",
        require_punctuation=True,
    )


def recap_adverb(doc: Doc) -> list[Edit]:
    if not doc.paragraphs:
        return []
    return _opener_edits(
        doc,
        (doc.paragraphs[-1],),
        _RECAP_ADVERBS,
        transform="recap_adverb",
        note="removed closing recap adverb",
    )


def puffery_table(doc: Doc) -> list[Edit]:
    table = load_lexicon().puffery_table
    return [
        Edit(
            span.start,
            span.end,
            _match_case(doc.text[span.start : span.end], table[phrase]),
            "puffery_table",
            f"fixed swap: {phrase} → {table[phrase]}",
        )
        for span, phrase in phrase_spans(doc.text, list(table))
    ]


def em_dash_normalize(doc: Doc) -> list[Edit]:
    count = doc.text.count("—")
    density = count / max(1, len(doc.words)) * 1000
    # One ordinary dash is not slop. Normalization starts above 5/1k words and
    # requires at least two dashes in the document.
    if count < 2 or density <= 5:
        return []

    edits: list[Edit] = []
    for sentence in doc.sentences:
        source = doc.text[sentence.start : sentence.end]
        dashes = [
            match
            for match in re.finditer(r"[ \t]*—[ \t]*", source)
            if not _joins_digits(source, match)
        ]
        if not dashes:
            continue
        if len(dashes) == 2 and _looks_appositive(source, dashes):
            for match in dashes:
                edits.append(
                    Edit(
                        sentence.start + match.start(),
                        sentence.start + match.end(),
                        ", ",
                        "em_dash_normalize",
                        "paired appositive dash → comma",
                    )
                )
            continue
        for match in dashes:
            after = match.end()
            letter = re.search(r"[A-Za-z]", source[after:])
            if letter is None:
                continue
            letter_start = after + letter.start()
            replacement = f". {source[after:letter_start]}{source[letter_start].upper()}"
            edits.append(
                Edit(
                    sentence.start + match.start(),
                    sentence.start + letter_start + 1,
                    replacement,
                    "em_dash_normalize",
                    "clause-joining dash → sentence break",
                )
            )
    return edits


def formatting_cleanup(doc: Doc) -> list[Edit]:
    if not _looks_like_markdown(doc.text):
        return []

    edits: list[Edit] = []
    for heading in re.finditer(r"(?m)^[ \t]{0,3}#{1,6}\s+[^\n]+", doc.text):
        source = heading.group()
        for emoji in _EMOJI_RE.finditer(source):
            start = emoji.start()
            end = emoji.end()
            if end < len(source) and source[end] == " ":
                end += 1
            elif start and source[start - 1] == " ":
                start -= 1
            edits.append(
                Edit(
                    heading.start() + start,
                    heading.start() + end,
                    "",
                    "formatting_cleanup",
                    "removed emoji from heading",
                )
            )
    for match in _BOLD_BULLET_RE.finditer(doc.text):
        label_start, label_end = match.span("label")
        edits.append(
            Edit(
                label_start - 2,
                label_end + 2,
                match.group("label"),
                "formatting_cleanup",
                "removed decorative bold from bullet lead-in",
            )
        )
    return edits


TRANSFORMS: tuple[Transform, ...] = (
    banned_swap,
    throat_clearing,
    setup_deletion,
    recap_adverb,
    puffery_table,
    em_dash_normalize,
    formatting_cleanup,
)


def resolve_edits(candidates: list[Edit]) -> list[Edit]:
    """Keep non-overlapping edits by transform priority and then leftmost position."""

    priority = {transform.__name__: index for index, transform in enumerate(TRANSFORMS)}
    selected: list[Edit] = []
    for edit in sorted(
        candidates,
        key=lambda item: (priority.get(item.transform, len(priority)), item.start, -item.end),
    ):
        if edit.start < 0 or edit.end <= edit.start:
            raise ValueError(f"invalid edit span: {edit.start}:{edit.end}")
        if any(edit.start < kept.end and kept.start < edit.end for kept in selected):
            continue
        selected.append(edit)
    return sorted(selected, key=lambda item: (item.start, item.end))


def collect_suggestions(doc: Doc) -> list[Suggestion]:
    """Collect judgment-required patterns with offsets into this final document."""

    report = analyze(doc.text)
    signals = {result.signal: result for result in report.signals}
    suggestions: list[Suggestion] = []
    protected = _markdown_code_spans(doc.text)

    for span in _object_opener_spans(doc):
        suggestions.append(_suggestion(doc, span, "object_opener"))
    for pattern in _BINARY_RE:
        for match in pattern.finditer(doc.text):
            suggestions.append(_suggestion(doc, Span(*match.span()), "binary_contrast"))
    for evidence in signals["colon_reveal"].evidence:
        suggestions.append(
            _suggestion(doc, Span(evidence.start, evidence.end), "colon_reveal")
        )
    for match in _TRAILING_ING_RE.finditer(doc.text):
        suggestions.append(_suggestion(doc, Span(*match.span()), "trailing_ing"))
    for evidence in signals["weasel"].evidence:
        suggestions.append(
            _suggestion(doc, Span(evidence.start, evidence.end), "weasel_attribution")
        )

    for sentence in doc.sentences:
        source = doc.text[sentence.start : sentence.end]
        word_count = len(re.findall(r"[A-Za-z0-9]+", source))
        if (
            1 <= word_count <= 3
            and source.rstrip().endswith((".", "!"))
            and not re.match(r"\s*(?:#|[-+*]\s|\d+[.)]\s)", source)
        ):
            suggestions.append(_suggestion(doc, sentence, "dramatic_fragmentation"))

    for span in _negative_list_spans(doc):
        suggestions.append(_suggestion(doc, span, "negative_listing"))
    for sentence in doc.sentences:
        source = doc.text[sentence.start : sentence.end]
        if source.rstrip().endswith("?") and _word_count(source) <= 20:
            suggestions.append(_suggestion(doc, sentence, "rhetorical_question"))

    if doc.sentences:
        final_sentence = doc.sentences[-1]
        if _FAKE_KICKER_RE.search(doc.text[final_sentence.start : final_sentence.end]):
            suggestions.append(_suggestion(doc, final_sentence, "fake_profound_kicker"))
    if signals["recap_ending"].severity != Severity.INFO and doc.paragraphs:
        suggestions.append(_suggestion(doc, doc.paragraphs[-1], "whole_recap"))
    if signals["burstiness"].severity != Severity.INFO:
        for evidence in signals["burstiness"].evidence:
            suggestions.append(
                _suggestion(doc, Span(evidence.start, evidence.end), "robotic_rhythm")
            )

    unique = {
        (item.start, item.end, item.pattern): item
        for item in suggestions
        if item.start < item.end
        and not _intersects_any(Span(item.start, item.end), protected)
    }
    return sorted(unique.values(), key=lambda item: (item.start, item.end, item.pattern))


def word_diff(original: str, final: str) -> list[DiffOp]:
    """Return a lossless word-level diff with replace operations split into delete/insert."""

    before = _TOKEN_RE.findall(original)
    after = _TOKEN_RE.findall(final)
    matcher = SequenceMatcher(a=before, b=after, autojunk=False)
    operations: list[DiffOp] = []
    for opcode, i1, i2, j1, j2 in matcher.get_opcodes():
        if opcode in {"equal", "delete", "replace"} and i1 != i2:
            operations.append(DiffOp("equal" if opcode == "equal" else "delete", "".join(before[i1:i2])))
        if opcode in {"insert", "replace"} and j1 != j2:
            operations.append(DiffOp("insert", "".join(after[j1:j2])))
    return _merge_diff_ops(operations)


def _opener_edits(
    doc: Doc,
    containers: Sequence[Span],
    phrases: Sequence[str],
    *,
    transform: str,
    note: str,
    require_punctuation: bool = False,
) -> list[Edit]:
    edits: list[Edit] = []
    for container in containers:
        source = doc.text[container.start : container.end]
        for phrase in sorted(phrases, key=len, reverse=True):
            punctuation = r"\s*[:,]\s+" if require_punctuation else r"(?:\s*[:,]\s+|\s+)"
            match = re.match(
                rf"{re.escape(phrase)}\b{punctuation}",
                source,
                re.IGNORECASE,
            )
            if match is None:
                continue
            letter = re.search(r"[A-Za-z]", source[match.end() :])
            if letter is None:
                break
            letter_start = match.end() + letter.start()
            replacement = (
                source[match.end() : letter_start] + source[letter_start].upper()
            )
            edits.append(
                Edit(
                    container.start,
                    container.start + letter_start + 1,
                    replacement,
                    transform,
                    note,
                )
            )
            break
    return edits


def _apply_edits(text: str, edits: list[Edit]) -> str:
    rewritten = text
    for edit in reversed(edits):
        if edit.end > len(text):
            raise ValueError(f"edit ends outside text: {edit.start}:{edit.end}")
        rewritten = f"{rewritten[: edit.start]}{edit.replacement}{rewritten[edit.end :]}"
    return rewritten


def _looks_like_leverage_verb(text: str, span: Span) -> bool:
    before = re.findall(r"[A-Za-z']+", text[max(0, span.start - 40) : span.start].lower())
    after = re.findall(r"[A-Za-z']+", text[span.end : span.end + 30].lower())
    if after and after[0] in {"ratio", "ratios", "debt", "loan", "loans", "position"}:
        return False
    return bool(
        before
        and before[-1]
        in {
            "can",
            "could",
            "should",
            "would",
            "will",
            "must",
            "may",
            "might",
            "to",
            "we",
            "they",
            "teams",
            "leaders",
            "organizations",
            "companies",
            "you",
        }
    )


def _match_case(source: str, replacement: str) -> str:
    letters = [char for char in source if char.isalpha()]
    if letters and all(char.isupper() for char in letters):
        return replacement.upper()
    first = next((char for char in source if char.isalpha()), "")
    if first.isupper():
        index = next(
            (position for position, char in enumerate(replacement) if char.isalpha()),
            None,
        )
        if index is not None:
            return f"{replacement[:index]}{replacement[index].upper()}{replacement[index + 1 :]}"
    return replacement


def _looks_appositive(source: str, dashes: list[re.Match[str]]) -> bool:
    middle = source[dashes[0].end() : dashes[1].start()]
    return 1 <= _word_count(middle) <= 12 and not re.search(r"[.!?]", middle)


def _joins_digits(source: str, dash: re.Match[str]) -> bool:
    before = source[: dash.start()].rstrip()
    after = source[dash.end() :].lstrip()
    return bool(before and after and before[-1].isdigit() and after[0].isdigit())


def _looks_like_markdown(text: str) -> bool:
    return bool(
        re.search(r"(?m)^[ \t]{0,3}#{1,6}\s+", text)
        or _BOLD_BULLET_RE.search(text)
        or re.search(r"(?m)^[ \t]*[-+*]\s+", text)
    )


def _suggestion(doc: Doc, span: Span, pattern: str) -> Suggestion:
    advice, instruction = _SUGGESTION_COPY[pattern]
    return Suggestion(
        span.start,
        span.end,
        doc.text[span.start : span.end],
        pattern,
        advice,
        instruction,
    )


def _negative_list_spans(doc: Doc) -> list[Span]:
    spans: list[Span] = []
    run: list[Span] = []
    for sentence in doc.sentences:
        source = doc.text[sentence.start : sentence.end]
        if re.match(r"(?:no|not|never)\b", source, re.IGNORECASE):
            run.append(sentence)
            continue
        if len(run) >= 3:
            spans.append(Span(run[0].start, run[-1].end))
        run = []
    if len(run) >= 3:
        spans.append(Span(run[0].start, run[-1].end))
    return spans


def _object_opener_spans(doc: Doc) -> list[Span]:
    pattern = "|".join(re.escape(phrase) for phrase in _OBJECT_TAKING_OPENERS)
    spans: list[Span] = []
    for sentence in doc.sentences:
        source = doc.text[sentence.start : sentence.end]
        match = re.match(rf"(?:{pattern})\b", source, re.IGNORECASE)
        if match is None:
            continue
        punctuation = re.search(r"[:,]", source[match.end() :])
        end = (
            sentence.end
            if punctuation is None
            else sentence.start + match.end() + punctuation.end()
        )
        spans.append(Span(sentence.start, end))
    return spans


def _markdown_code_spans(text: str) -> list[Span]:
    fenced = _fenced_code_spans(text)
    inline: list[Span] = []
    cursor = 0
    for fence in fenced:
        inline.extend(_inline_code_spans(text, cursor, fence.start))
        cursor = fence.end
    inline.extend(_inline_code_spans(text, cursor, len(text)))
    return sorted([*fenced, *inline])


def _fenced_code_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    cursor = 0
    while opening := _FENCE_START_RE.search(text, cursor):
        marker = opening.group("fence")
        closing_re = re.compile(
            rf"(?m)^[ \t]{{0,3}}{re.escape(marker[0])}{{{len(marker)},}}"
            r"[ \t]*(?:\r?\n|$)"
        )
        closing = closing_re.search(text, opening.end())
        end = closing.end() if closing else len(text)
        spans.append(Span(opening.start(), end))
        cursor = end
    return spans


def _inline_code_spans(text: str, start: int, end: int) -> list[Span]:
    spans: list[Span] = []
    cursor = start
    while opener := _BACKTICK_RUN_RE.search(text, cursor, end):
        if opener.start() > start and text[opener.start() - 1] == "\\":
            cursor = opener.end()
            continue
        closing = _matching_backtick_run(text, opener, end)
        if closing is None:
            cursor = opener.end()
            continue
        spans.append(Span(opener.start(), closing.end()))
        cursor = closing.end()
    return spans


def _matching_backtick_run(
    text: str, opener: re.Match[str], end: int
) -> re.Match[str] | None:
    cursor = opener.end()
    while candidate := _BACKTICK_RUN_RE.search(text, cursor, end):
        if (
            len(candidate.group()) == len(opener.group())
            and text[candidate.start() - 1] != "\\"
        ):
            return candidate
        cursor = candidate.end()
    return None


def _mask_spans(text: str, spans: Sequence[Span]) -> str:
    masked = list(text)
    for span in spans:
        for index in range(span.start, span.end):
            if masked[index] not in "\r\n":
                masked[index] = " "
    return "".join(masked)


def _intersects_any(span: Span, protected: Sequence[Span]) -> bool:
    return any(span.start < item.end and item.start < span.end for item in protected)


def _word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*", text))


def _merge_diff_ops(operations: list[DiffOp]) -> list[DiffOp]:
    merged: list[DiffOp] = []
    for operation in operations:
        if not operation.text:
            continue
        if merged and merged[-1].op == operation.op:
            previous = merged[-1]
            merged[-1] = DiffOp(previous.op, previous.text + operation.text)
        else:
            merged.append(operation)
    return merged
