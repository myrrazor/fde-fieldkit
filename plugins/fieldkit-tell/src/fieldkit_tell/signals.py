from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass
from enum import StrEnum
from typing import Callable

from fieldkit_tell.lexicon import load_lexicon, phrase_spans
from fieldkit_tell.sentences import Doc, Span, segment


class Severity(StrEnum):
    INFO = "info"
    NOTICE = "notice"
    STRONG = "strong"


@dataclass(frozen=True)
class Evidence:
    start: int
    end: int
    excerpt: str
    note: str


@dataclass(frozen=True)
class SignalResult:
    """One tell-density result. `score` is not P(AI) or an authorship verdict."""

    signal: str
    title: str
    severity: Severity
    score: float
    summary: str
    evidence: list[Evidence]
    stats: dict[str, int | float | str]


@dataclass(frozen=True)
class TextStats:
    chars: int
    words: int
    sentences: int
    paragraphs: int
    mean_sentence_len: float
    sentence_len_cv: float


@dataclass(frozen=True)
class SignalReport:
    """All local signals, deliberately without an aggregate or overall verdict."""

    text_stats: TextStats
    signals: list[SignalResult]


Signal = Callable[[Doc], SignalResult]

_BINARY_PATTERNS = (
    re.compile(
        r"\b(?:it|this|that)(?:['’]s|\s+is)\s+not\s+just\b"
        r"[^.!?\n—]{2,100}(?:—|,\s+but\b|\s+but\b)\s*"
        r"(?:it|this|that)(?:['’]s|\s+is)\b[^.!?\n]{1,100}",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bnot\s+[^.!?\n]{2,80}[.!?]\s+"
        r"(?:it|this|that)(?:['’]s|\s+is)\s+[^.!?\n]{2,100}",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:isn['’]t|is\s+not)\s+just\b[^.!?\n—]{2,100}"
        r"(?:—|,\s+but\b|\s+but\b)\s*(?:it(?:['’]s|\s+is)|rather)\b[^.!?\n]{1,100}",
        re.IGNORECASE,
    ),
)
_COLON_REVEAL_RE = re.compile(
    r"(?<![\w/])(?:the\s+)?(?:[A-Za-z][\w'’-]*\s+){0,5}[A-Za-z][\w'’-]*:\s+(?=\S)",
    re.IGNORECASE,
)
_TRIAD_RE = re.compile(
    r"\b[^,\n]{1,42},\s+[^,\n]{1,42},\s+(?:and|or)\s+[^,.;:!?\n]{1,42}",
    re.IGNORECASE,
)
_EMOJI_HEADER_RE = re.compile(
    r"(?m)^[ \t]{0,3}#{1,6}\s+[^\n]*[\U0001F300-\U0001FAFF\u2600-\u27BF][^\n]*"
)
_BOLD_LEAD_RE = re.compile(
    r"(?m)^[ \t]*(?:[-+*]\s+|\d+[.)]\s+)\*\*[^*\n]{1,40}:\*\*"
)


def analyze(text: str) -> SignalReport:
    """Run every local signal against the exact same segmented document."""

    doc = segment(text)
    return SignalReport(_text_stats(doc), [signal(doc) for signal in SIGNALS])


def burstiness(doc: Doc) -> SignalResult:
    lengths = [_word_count(doc, span) for span in doc.sentences]
    cv = _coefficient_of_variation(lengths)
    run_start, run_end = _longest_uniform_run(lengths)
    run_length = run_end - run_start
    evidence: list[Evidence] = []
    if run_length >= 3:
        span = Span(doc.sentences[run_start].start, doc.sentences[run_end - 1].end)
        evidence.append(
            _evidence(
                doc,
                span,
                f"{run_length} adjacent sentences stay within a narrow length band",
            )
        )

    # Six uniform sentences is strong even when a varied intro raises whole-doc CV.
    strong = len(lengths) >= 5 and ((cv <= 0.22 and run_length >= 4) or run_length >= 6)
    notice = len(lengths) >= 4 and (cv <= 0.42 or run_length >= 4)
    severity = Severity.STRONG if strong else Severity.NOTICE if notice else Severity.INFO
    score = _bounded(max(_inverse_density(cv, 0.55), run_length / max(1, len(lengths))))
    if len(lengths) < 4:
        score = 0.0
    return _result(
        "burstiness",
        "Sentence rhythm",
        severity,
        score,
        (
            "Sentence lengths are unusually uniform."
            if severity != Severity.INFO
            else "Sentence lengths show ordinary variation."
        ),
        evidence,
        {"sentence_len_cv": round(cv, 4), "uniform_run": run_length},
    )


def phrase_tells(doc: Doc) -> SignalResult:
    matches = phrase_spans(doc.text, list(load_lexicon().banned_words))
    count = len(matches)
    rate = count / max(1, len(doc.words)) * 100
    severity = Severity.STRONG if count >= 3 else Severity.NOTICE if count else Severity.INFO
    evidence = [
        _evidence(doc, span, f"lexicon phrase: {phrase}") for span, phrase in matches
    ]
    return _result(
        "phrase_tells",
        "Phrase tells",
        severity,
        _bounded(rate / 3),
        f"{count} overrepresented phrase{'s' if count != 1 else ''} found.",
        evidence,
        {"hits": count, "per_100_words": round(rate, 3)},
    )


def em_dash(doc: Doc) -> SignalResult:
    count = doc.text.count("—")
    rate = count / max(1, len(doc.words)) * 1000
    evidence: list[Evidence] = []
    clusters = 0
    for sentence in doc.sentences:
        source = doc.text[sentence.start : sentence.end]
        sentence_count = source.count("—")
        if not sentence_count:
            continue
        clusters += int(sentence_count >= 2)
        evidence.append(
            _evidence(
                doc,
                sentence,
                (
                    f"{sentence_count} em dashes in one sentence"
                    if sentence_count >= 2
                    else "em dash"
                ),
            )
        )

    # A two-dash sentence or 12+ dashes/1k words is a strong local cluster.
    severity = (
        Severity.STRONG
        if clusters or (count >= 2 and rate >= 12)
        else Severity.NOTICE if count else Severity.INFO
    )
    return _result(
        "em_dash",
        "Em-dash clusters",
        severity,
        _bounded(rate / 12),
        f"{count} em dash{'es' if count != 1 else ''}; {rate:.1f} per 1,000 words.",
        evidence,
        {"count": count, "per_1000_words": round(rate, 3), "clustered_sentences": clusters},
    )


def binary_contrast(doc: Doc) -> SignalResult:
    matches = _regex_spans(doc.text, _BINARY_PATTERNS)
    evidence = [
        _evidence(doc, span, "formulaic not-X / but-Y contrast") for span in matches
    ]
    severity = Severity.STRONG if matches else Severity.INFO
    return _result(
        "binary_contrast",
        "Binary contrasts",
        severity,
        _bounded(len(matches)),
        (
            f"{len(matches)} formulaic contrast{'s' if len(matches) != 1 else ''} found."
            if matches
            else "No formulaic not-X / but-Y contrasts found."
        ),
        evidence,
        {"hits": len(matches)},
    )


def colon_reveal(doc: Doc) -> SignalResult:
    matches: list[Span] = []
    for sentence in doc.sentences:
        source = doc.text[sentence.start : sentence.end]
        stripped = source.lstrip()
        if re.match(r"(?:#{1,6}\s|[-+*]\s|\d+[.)]\s|\*\*)", stripped):
            continue
        for match in _COLON_REVEAL_RE.finditer(source):
            if "://" in source[max(0, match.start() - 8) : match.end()]:
                continue
            matches.append(Span(sentence.start + match.start(), sentence.end))

    severity = (
        Severity.STRONG
        if len(matches) >= 3
        else Severity.NOTICE if matches else Severity.INFO
    )
    return _result(
        "colon_reveal",
        "Colon reveals",
        severity,
        _bounded(len(matches) / 3),
        f"{len(matches)} prose colon-reveal{'s' if len(matches) != 1 else ''} found.",
        [_evidence(doc, span, "compressed setup-and-reveal construction") for span in matches],
        {"hits": len(matches)},
    )


def puffery(doc: Doc) -> SignalResult:
    table = load_lexicon().puffery_table
    matches = phrase_spans(doc.text, list(table))
    severity = (
        Severity.STRONG
        if len(matches) >= 2
        else Severity.NOTICE if matches else Severity.INFO
    )
    return _result(
        "puffery",
        "Importance puffery",
        severity,
        _bounded(len(matches) / 2),
        f"{len(matches)} importance-inflating phrase{'s' if len(matches) != 1 else ''} found.",
        [_evidence(doc, span, f"can usually be stated as “{table[phrase]}”") for span, phrase in matches],
        {"hits": len(matches)},
    )


def weasel(doc: Doc) -> SignalResult:
    matches = phrase_spans(doc.text, list(load_lexicon().weasel_markers))
    severity = (
        Severity.STRONG
        if len(matches) >= 2
        else Severity.NOTICE if matches else Severity.INFO
    )
    return _result(
        "weasel",
        "Unattributed authority",
        severity,
        _bounded(len(matches) / 2),
        f"{len(matches)} unattributed authority marker{'s' if len(matches) != 1 else ''} found.",
        [_evidence(doc, span, "name the source or remove the claim") for span, _ in matches],
        {"hits": len(matches)},
    )


def uniform_structure(doc: Doc) -> SignalResult:
    paragraph_lengths = [_word_count(doc, span) for span in doc.paragraphs]
    paragraph_cv = _coefficient_of_variation(paragraph_lengths)
    triads = _triadic_spans(doc)
    triad_rate = len(triads) / max(1, len(doc.sentences))
    evidence = [_evidence(doc, span, "triadic list construction") for span in triads]

    monotony = len(paragraph_lengths) >= 3 and paragraph_cv <= 0.35
    if monotony and doc.paragraphs:
        evidence.insert(
            0,
            _evidence(
                doc,
                Span(doc.paragraphs[0].start, doc.paragraphs[-1].end),
                "paragraph lengths stay unusually close",
            ),
        )

    # Four near-identical paragraphs or repeated triads across 25% of sentences is strong.
    strong = (
        len(paragraph_lengths) >= 4
        and paragraph_cv <= 0.18
        or len(triads) >= 2
        and triad_rate >= 0.25
    )
    notice = monotony or bool(triads)
    severity = Severity.STRONG if strong else Severity.NOTICE if notice else Severity.INFO
    score = max(_inverse_density(paragraph_cv, 0.45) if monotony else 0.0, triad_rate / 0.25)
    return _result(
        "uniform_structure",
        "Uniform structure",
        severity,
        _bounded(score),
        (
            "Paragraph or list structure repeats at a machine-like cadence."
            if severity != Severity.INFO
            else "Paragraph and list structure is not unusually repetitive."
        ),
        evidence,
        {
            "paragraph_len_cv": round(paragraph_cv, 4),
            "triadic_lists": len(triads),
            "triadic_rate": round(triad_rate, 4),
        },
    )


def recap_ending(doc: Doc) -> SignalResult:
    if not doc.paragraphs:
        return _result(
            "recap_ending",
            "Recap ending",
            Severity.INFO,
            0.0,
            "No closing paragraph to inspect.",
            [],
            {"opening_overlap": 0.0, "recap_opener": "none"},
        )

    first = doc.text[doc.paragraphs[0].start : doc.paragraphs[0].end]
    final_span = doc.paragraphs[-1]
    final = doc.text[final_span.start : final_span.end]
    opener = next(
        (
            phrase
            for phrase in load_lexicon().recap_openers
            if re.match(rf"{re.escape(phrase)}\b", final, re.IGNORECASE)
        ),
        None,
    )
    overlap = _ngram_overlap(first, final)
    severity = (
        Severity.STRONG
        if opener or overlap >= 0.45
        else Severity.NOTICE if overlap >= 0.25 else Severity.INFO
    )
    evidence = (
        [
            _evidence(
                doc,
                final_span,
                (
                    f"final paragraph opens with “{opener}”"
                    if opener
                    else f"shares {overlap:.0%} of opening trigrams"
                ),
            )
        ]
        if severity != Severity.INFO
        else []
    )
    return _result(
        "recap_ending",
        "Recap ending",
        severity,
        _bounded(1.0 if opener else overlap / 0.45),
        (
            "The ending explicitly recaps or closely repeats the opening."
            if severity != Severity.INFO
            else "The ending does not mechanically recap the opening."
        ),
        evidence,
        {"opening_overlap": round(overlap, 4), "recap_opener": opener or "none"},
    )


def formatting_slop(doc: Doc) -> SignalResult:
    matches = [
        (Span(match.start(), match.end()), "emoji in Markdown heading")
        for match in _EMOJI_HEADER_RE.finditer(doc.text)
    ]
    matches.extend(
        (Span(match.start(), match.end()), "bold lead-in label in a bullet")
        for match in _BOLD_LEAD_RE.finditer(doc.text)
    )
    severity = (
        Severity.STRONG
        if len(matches) >= 3
        else Severity.NOTICE if matches else Severity.INFO
    )
    return _result(
        "formatting_slop",
        "Formatting slop",
        severity,
        _bounded(len(matches) / 3),
        f"{len(matches)} templated Markdown flourish{'es' if len(matches) != 1 else ''} found.",
        [_evidence(doc, span, note) for span, note in matches],
        {
            "emoji_headers": sum(note.startswith("emoji") for _, note in matches),
            "bold_bullet_leads": sum(note.startswith("bold") for _, note in matches),
        },
    )


SIGNALS: tuple[Signal, ...] = (
    burstiness,
    phrase_tells,
    em_dash,
    binary_contrast,
    colon_reveal,
    puffery,
    weasel,
    uniform_structure,
    recap_ending,
    formatting_slop,
)


def _text_stats(doc: Doc) -> TextStats:
    lengths = [_word_count(doc, span) for span in doc.sentences]
    return TextStats(
        chars=len(doc.text),
        words=len(doc.words),
        sentences=len(doc.sentences),
        paragraphs=len(doc.paragraphs),
        mean_sentence_len=round(statistics.fmean(lengths), 3) if lengths else 0.0,
        sentence_len_cv=round(_coefficient_of_variation(lengths), 4),
    )


def _word_count(doc: Doc, container: Span) -> int:
    return sum(container.start <= word.start and word.end <= container.end for word in doc.words)


def _coefficient_of_variation(values: list[int]) -> float:
    if not values:
        return 0.0
    mean = statistics.fmean(values)
    if mean == 0:
        return 0.0
    return statistics.pstdev(values) / mean


def _longest_uniform_run(lengths: list[int]) -> tuple[int, int]:
    best = (0, min(1, len(lengths)))
    for start in range(len(lengths)):
        for end in range(start + 3, len(lengths) + 1):
            window = lengths[start:end]
            tolerance = max(3.0, statistics.fmean(window) * 0.25)
            if max(window) - min(window) <= tolerance and end - start > best[1] - best[0]:
                best = (start, end)
    return best


def _triadic_spans(doc: Doc) -> list[Span]:
    spans: list[Span] = []
    for sentence in doc.sentences:
        source = doc.text[sentence.start : sentence.end]
        spans.extend(
            Span(sentence.start + match.start(), sentence.start + match.end())
            for match in _TRIAD_RE.finditer(source)
        )

    bullet_re = re.compile(r"(?m)^(?:[ \t]*[-+*]\s+.+\n){2}[ \t]*[-+*]\s+.+$")
    spans.extend(Span(match.start(), match.end()) for match in bullet_re.finditer(doc.text))
    return _dedupe_spans(spans)


def _ngram_overlap(first: str, final: str) -> float:
    first_words = re.findall(r"[a-z0-9]+", first.lower())
    final_words = re.findall(r"[a-z0-9]+", final.lower())
    first_ngrams = set(zip(first_words, first_words[1:], first_words[2:]))
    final_ngrams = set(zip(final_words, final_words[1:], final_words[2:]))
    if not first_ngrams or not final_ngrams:
        return 0.0
    return len(first_ngrams & final_ngrams) / min(len(first_ngrams), len(final_ngrams))


def _regex_spans(text: str, patterns: tuple[re.Pattern[str], ...]) -> list[Span]:
    return _dedupe_spans(
        [Span(match.start(), match.end()) for pattern in patterns for match in pattern.finditer(text)]
    )


def _dedupe_spans(spans: list[Span]) -> list[Span]:
    selected: list[Span] = []
    for span in sorted(spans, key=lambda item: (item.start, -item.end)):
        if any(span.start < kept.end and kept.start < span.end for kept in selected):
            continue
        selected.append(span)
    return selected


def _evidence(doc: Doc, span: Span, note: str) -> Evidence:
    excerpt = doc.text[span.start : span.end]
    if len(excerpt) > 240:
        excerpt = f"{excerpt[:237].rstrip()}…"
    return Evidence(span.start, span.end, excerpt, note)


def _inverse_density(value: float, ceiling: float) -> float:
    return max(0.0, (ceiling - value) / ceiling) if ceiling else 0.0


def _bounded(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return round(max(0.0, min(1.0, value)), 4)


def _result(
    signal: str,
    title: str,
    severity: Severity,
    score: float,
    summary: str,
    evidence: list[Evidence],
    stats: dict[str, int | float | str],
) -> SignalResult:
    return SignalResult(signal, title, severity, _bounded(score), summary, evidence, stats)
