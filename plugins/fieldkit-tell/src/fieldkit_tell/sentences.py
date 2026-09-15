from __future__ import annotations

import re
from dataclasses import dataclass

_WORD_RE = re.compile(r"[A-Za-z0-9]+(?:['’\-][A-Za-z0-9]+)*")
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
        next_line = lines[index + 1] if index + 1 < len(lines) else ""
        current_structural = _is_markdown_marker_line(line)
        next_structural = _is_markdown_marker_line(next_line)
        line_end = line_start + len(line.rstrip("\r\n"))
        if _line_has_content(line) and (current_structural or next_structural):
            boundaries.add(line_end)
        line_start += len(line)
    return boundaries


def _line_has_content(line: str) -> bool:
    for char in line:
        if not char.isspace():
            return True
    return False


def _is_markdown_marker_line(line: str) -> bool:
    """Heading, bullet, or ordered-list marker after Unicode strip()."""

    start = 0
    end = len(line)
    while start < end and line[start].isspace():
        start += 1
    while end > start and line[end - 1].isspace():
        end -= 1
    if start >= end:
        return False
    index = start
    if line[index] == "#":
        hashes = 0
        while index < end and line[index] == "#" and hashes < 6:
            hashes += 1
            index += 1
        return hashes >= 1 and index < end and line[index].isspace()
    if line[index] in "-+*":
        return index + 1 < end and line[index + 1].isspace()
    if line[index].isdecimal():
        while index < end and line[index].isdecimal():
            index += 1
        return index + 1 < end and line[index] in ".)" and line[index + 1].isspace()
    return False


def _ascii_letter(char: str) -> bool:
    return "A" <= char <= "Z" or "a" <= char <= "z"


def _guarded_period(source: str, index: int) -> bool:
    if source[index] != ".":
        return False
    if 0 < index < len(source) - 1 and source[index - 1].isdigit() and source[index + 1].isdigit():
        return True
    if index + 2 < len(source) and source[index + 1].isalpha() and source[index + 2] == ".":
        return True

    token = _trailing_abbrev_or_initialism(source, index)
    if token is None:
        return False
    lowered = token.lower()
    if lowered in _ABBREVIATIONS or _is_letter_period_initialism(lowered):
        return _has_nonspace_after(source, index + 1)
    return False


def _trailing_abbrev_or_initialism(source: str, index: int) -> str | None:
    """Suffix token ending at the period: 'Dr.' or 'U.S.', scanned backward."""

    units = 0
    pos = index
    while pos >= 1 and source[pos] == "." and _ascii_letter(source[pos - 1]):
        units += 1
        pos -= 2
    if units >= 2:
        return source[pos + 1 : index + 1]

    start = index
    while start > 0 and _ascii_letter(source[start - 1]):
        start -= 1
    if start < index:
        return source[start : index + 1]
    return None


def _is_letter_period_initialism(token: str) -> bool:
    length = len(token)
    if length < 4 or length % 2:
        return False
    for offset in range(0, length, 2):
        if not _ascii_letter(token[offset]) or token[offset + 1] != ".":
            return False
    return True


def _has_nonspace_after(source: str, start: int) -> bool:
    for index in range(start, len(source)):
        if not source[index].isspace():
            return True
    return False


def _trim(source: str, start: int, end: int) -> tuple[int, int]:
    while start < end and source[start].isspace():
        start += 1
    while end > start and source[end - 1].isspace():
        end -= 1
    return start, end
