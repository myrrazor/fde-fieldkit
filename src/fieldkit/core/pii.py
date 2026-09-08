from __future__ import annotations

import math
import re
from collections.abc import Callable
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from importlib import resources

import pandas as pd

_EMAIL_RE = re.compile(r"(?<![\w.+-])[\w.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+(?![\w.-])")
_SSN_RE = re.compile(r"(?<!\d)(?:\d{3}-\d{2}-\d{4}|\d{9})(?!\d)")
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_IP_RE = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
_PHONE_RE = re.compile(r"(?<!\w)\+?\(?\d[\d()+. -]{8,}\d(?!\w)")
_PREFIX_SECRET_RE = re.compile(
    r"AKIA[A-Z0-9]{12,}|sk-[A-Za-z0-9_-]{8,}|gh[po]_[A-Za-z0-9]{8,}|"
    r"xox[bp]-[A-Za-z0-9-]{8,}|-----BEGIN[ A-Z0-9_-]+-----"
)
_ENTROPY_TOKEN_RE = re.compile(r"(?<!\S)\S{20,}(?!\S)")
_SSN_HINT_RE = re.compile(r"ssn|social", re.IGNORECASE)
_NAME_HINT_RE = re.compile(r"name|first|last|full", re.IGNORECASE)


class PIIKind(StrEnum):
    """PII categories recognized by the local scanner."""

    EMAIL = "email"
    PHONE = "phone"
    SSN = "ssn"
    CREDIT_CARD = "credit_card"
    IP = "ip"
    NAME = "name"
    SECRET = "secret"


@dataclass
class PIIMatch:
    """One validated match within a string."""

    kind: PIIKind
    start: int
    end: int
    value: str


@dataclass
class PIIColumnReport:
    """Confidence, coverage, and safe examples for a sampled column."""

    kinds: dict[PIIKind, float]
    hit_rate: float
    samples_masked: list[str]


def scan_text(text: str, *, column_name: str = "") -> list[PIIMatch]:
    """Return validated PII spans, optionally using a column-name hint."""

    return _scan(text, column_name=column_name)


def scan_column(s: pd.Series, *, column_name: str = "", sample_size: int = 500) -> PIIColumnReport:
    """Sample a series evenly and summarize PII kinds with confidence at least 0.5."""

    values = [str(value) for value in s.dropna()]
    sampled = _even_sample(values, sample_size)
    if not sampled:
        return PIIColumnReport({}, 0.0, [])

    counts: Counter[PIIKind] = Counter()
    hit_count = 0
    masked: list[str] = []
    for value in sampled:
        matches = _scan(value, column_name)
        if not matches:
            continue
        hit_count += 1
        counts.update({match.kind for match in matches})
        if len(masked) < 3:
            masked.append(_mask_value(value, matches[0].kind))

    kinds: dict[PIIKind, float] = {}
    for kind, count in counts.items():
        rate = count / len(sampled)
        confidence = rate
        if kind == PIIKind.NAME:
            confidence *= 0.7 if _NAME_HINT_RE.search(column_name) else 0.4
        if confidence >= 0.5:
            kinds[kind] = confidence
    return PIIColumnReport(kinds, hit_count / len(sampled), masked)


def scan_dataframe(df: pd.DataFrame) -> dict[str, PIIColumnReport]:
    """Scan each dataframe column using its header as a confidence hint."""

    return {str(column): scan_column(df[column], column_name=str(column)) for column in df.columns}


def _scan(text: str, column_name: str) -> list[PIIMatch]:
    matches: list[PIIMatch] = []
    matches.extend(_validated_matches(text, _EMAIL_RE, PIIKind.EMAIL, _valid_email))
    matches.extend(_validated_matches(text, _PHONE_RE, PIIKind.PHONE, _valid_phone))
    matches.extend(
        _validated_matches(
            text,
            _SSN_RE,
            PIIKind.SSN,
            lambda value: _valid_ssn(value, bool(_SSN_HINT_RE.search(column_name))),
        )
    )
    matches.extend(_validated_matches(text, _CARD_RE, PIIKind.CREDIT_CARD, _valid_card))
    matches.extend(_validated_matches(text, _IP_RE, PIIKind.IP, _valid_ip))
    matches.extend(
        PIIMatch(PIIKind.SECRET, match.start(), match.end(), match.group())
        for match in _PREFIX_SECRET_RE.finditer(text)
    )
    matches.extend(
        PIIMatch(PIIKind.SECRET, match.start(), match.end(), match.group())
        for match in _ENTROPY_TOKEN_RE.finditer(text)
        if _valid_entropy_secret(match.group())
    )
    if _valid_name(text):
        matches.append(PIIMatch(PIIKind.NAME, 0, len(text), text))

    unique = {(match.kind, match.start, match.end, match.value): match for match in matches}
    return sorted(unique.values(), key=lambda match: (match.start, match.end, match.kind.value))


def _validated_matches(
    text: str,
    pattern: re.Pattern[str],
    kind: PIIKind,
    validator: Callable[[str], bool],
) -> list[PIIMatch]:
    return [
        PIIMatch(kind, match.start(), match.end(), match.group())
        for match in pattern.finditer(text)
        if validator(match.group())
    ]


def _valid_email(value: str) -> bool:
    _, domain = value.rsplit("@", 1)
    return "." in domain and not domain.startswith(".") and not domain.endswith(".")


def _valid_phone(value: str) -> bool:
    if re.fullmatch(r"\d{3}-\d{2}-\d{4}", value):
        return False
    # dotted quads strip down to 10-12 digits and masquerade as phones
    if re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", value):
        return False
    if re.search(r"[^\d()+. -]", value):
        return False
    digits = re.sub(r"\D", "", value)
    return 10 <= len(digits) <= 15


def _valid_ssn(value: str, bare_allowed: bool) -> bool:
    if "-" not in value and not bare_allowed:
        return False
    digits = value.replace("-", "")
    if len(digits) != 9:
        return False
    area, group, serial = int(digits[:3]), int(digits[3:5]), int(digits[5:])
    return area not in {0, 666} and area < 900 and group != 0 and serial != 0


def _valid_card(value: str) -> bool:
    digits = re.sub(r"[ -]", "", value)
    if not digits.isdigit() or not 13 <= len(digits) <= 19:
        return False
    total = 0
    parity = len(digits) % 2
    for index, char in enumerate(digits):
        digit = int(char)
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        total += digit
    return total % 10 == 0


def _valid_ip(value: str) -> bool:
    return all(0 <= int(octet) <= 255 for octet in value.split("."))


def _entropy(value: str) -> float:
    counts = Counter(value)
    length = len(value)
    return -sum((count / length) * math.log2(count / length) for count in counts.values())


def _valid_entropy_secret(value: str) -> bool:
    if _EMAIL_RE.search(value):
        return False
    return _entropy(value) > 4.0


@lru_cache(maxsize=1)
def _names() -> frozenset[str]:
    data_dir = resources.files("fieldkit.core").joinpath("data")
    names: set[str] = set()
    for filename in ("first_names.txt", "last_names.txt"):
        names.update(data_dir.joinpath(filename).read_text(encoding="utf-8").splitlines())
    return frozenset(name.strip().lower() for name in names if name.strip())


def _valid_name(value: str) -> bool:
    words = value.strip().lower().split()
    return 1 <= len(words) <= 2 and all(word in _names() for word in words)


def _even_sample(values: list[str], sample_size: int) -> list[str]:
    if sample_size <= 0:
        return []
    if len(values) <= sample_size:
        return values
    if sample_size == 1:
        return [values[0]]
    positions = [
        round(index * (len(values) - 1) / (sample_size - 1)) for index in range(sample_size)
    ]
    return [values[position] for position in positions]


def _mask_value(value: str, kind: PIIKind) -> str:
    if kind == PIIKind.EMAIL and "@" in value:
        local, domain = value.split("@", 1)
        host, dot, suffix = domain.partition(".")
        return f"{local[:1]}***@{host[:1]}***{dot}{suffix}"
    if kind in {PIIKind.PHONE, PIIKind.SSN, PIIKind.CREDIT_CARD}:
        digits = re.sub(r"\D", "", value)
        return f"***{digits[-4:]}"
    if kind == PIIKind.IP:
        first = value.split(".", 1)[0]
        return f"{first}.***.***.***"
    if kind == PIIKind.NAME:
        return " ".join(f"{word[:1]}***" for word in value.split())
    if kind == PIIKind.SECRET:
        return f"{value[:4]}***"
    return f"{value[:1]}***"
