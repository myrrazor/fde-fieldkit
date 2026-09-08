from __future__ import annotations

import re
from dataclasses import dataclass

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")
_MARKDOWN_LINE_RE = re.compile(r"(?:#{1,6}\s+|[-+*]\s+|\d+[.)]\s+)")
_ABBREVIATIONS = frozenset(
    {
        "dr.",
        "e.g.",
        "etc.",
        "i.e.",
        "jr.",
        "mr.",
        "mrs.",
        "ms.",
        "prof.",
        "sr.",
        "st.",
        "vs.",
    }
)


@dataclass(frozen=True, order=True)
class Span:
    """A half-open absolute character range."""

    start: int
    end: int


@dataclass(frozen=True)
class Doc:
    """Text plus sentence, paragraph, and word spans in one coordinate space."""

    text: str
    sentences: tuple[Span, ...]
    paragraphs: tuple[Span, ...]
    words: tuple[Span, ...]


def segment(text: str) -> Doc:
    """Segment text deterministically without normalizing or changing source offsets."""

    paragraphs = tuple(_paragraph_spans(text))
    sentences = tuple(
        sentence
        for paragraph in paragraphs
        for sentence in _sentence_spans(text, paragraph)
    )
    words = tuple(Span(match.start(), match.end()) for match in _WORD_RE.finditer(text))
    return Doc(text=text, sentences=sentences, paragraphs=paragraphs, words=words)


def _paragraph_spans(text: str) -> list[Span]:
    spans: list[Span] = []
    start: int | None = None
    offset = 0
    last_content_end = 0

    for line in text.splitlines(keepends=True):
        content_end = offset + len(line.rstrip())
        if line.strip():
            if start is None:
                leading = len(line) - len(line.lstrip())
                start = offset + leading
            last_content_end = content_end
        elif start is not None:
            spans.append(Span(start, last_content_end))
            start = None
        offset += len(line)

    if start is not None:
        spans.append(Span(start, last_content_end))
    return spans


def _sentence_spans(text: str, paragraph: Span) -> list[Span]:
    source = text[paragraph.start : paragraph.end]
    boundaries = _markdown_boundaries(source)
    index = 0
    while index < len(source):
        char = source[index]
        if char in ".!?":
            end = index + 1
            while end < len(source) and source[end] in ".!?":
                end += 1
            while end < len(source) and source[end] in "\"'”’)]":
                end += 1
            if not _guarded_period(source, index):
                boundaries.add(end)
            index = end
            continue
        index += 1
    boundaries.add(len(source))

    spans: list[Span] = []
    cursor = 0
    for boundary in sorted(boundaries):
        if boundary <= cursor:
            continue
        start, end = _trim(source, cursor, boundary)
        if start < end:
            spans.append(Span(paragraph.start + start, paragraph.start + end))
        cursor = boundary
    return spans


def _markdown_boundaries(source: str) -> set[int]:
    boundaries: set[int] = set()
    line_start = 0
    lines = source.splitlines(keepends=True)
    for index, line in enumerate(lines):
        stripped = line.strip()
        next_stripped = lines[index + 1].strip() if index + 1 < len(lines) else ""
        current_structural = bool(_MARKDOWN_LINE_RE.match(stripped))
        next_structural = bool(_MARKDOWN_LINE_RE.match(next_stripped))
        line_end = line_start + len(line.rstrip("\r\n"))
        if stripped and (current_structural or next_structural):
            boundaries.add(line_end)
        line_start += len(line)
    return boundaries


def _guarded_period(source: str, index: int) -> bool:
    if source[index] != ".":
        return False
    if 0 < index < len(source) - 1 and source[index - 1].isdigit() and source[index + 1].isdigit():
        return True
    if index + 2 < len(source) and source[index + 1].isalpha() and source[index + 2] == ".":
        return True

    prefix = source[: index + 1]
    token_match = re.search(r"(?:[A-Za-z]\.){2,}$|[A-Za-z]+[.]$", prefix)
    if token_match is None:
        return False
    token = token_match.group().lower()
    if token in _ABBREVIATIONS or re.fullmatch(r"(?:[a-z]\.){2,}", token):
        return bool(source[index + 1 :].strip())
    return False


def _trim(source: str, start: int, end: int) -> tuple[int, int]:
    while start < end and source[start].isspace():
        start += 1
    while end > start and source[end - 1].isspace():
        end -= 1
    return start, end
