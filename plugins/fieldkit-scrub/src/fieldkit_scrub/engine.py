from __future__ import annotations

import hashlib
import hmac
import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

import pandas as pd
from faker import Faker

from fieldkit.core.io import LoadedTable
from fieldkit.core.pii import PIIMatch, PIIKind, scan_dataframe, scan_text

_MATCH_PRIORITY = {
    PIIKind.CREDIT_CARD: 7,
    PIIKind.SECRET: 6,
    PIIKind.EMAIL: 5,
    PIIKind.SSN: 4,
    PIIKind.IP: 3,
    PIIKind.PHONE: 2,
    PIIKind.NAME: 1,
}
_FAKE_SECRET_RE = re.compile(r"FK_SECRET_[0-9a-f]{8}")


@dataclass
class ScrubSummary:
    """Replacement totals for one scrub operation."""

    replaced: dict[str, int]
    by_column: dict[str, dict[str, int]]


class Scrubber:
    """Pseudonymize detected PII using an exact-value HMAC mapping."""

    def __init__(self, salt: bytes, *, kinds: set[PIIKind] | None = None):
        self.salt = salt
        self.kinds = set(PIIKind) if kinds is None else set(kinds)
        self.mapping: dict[str, str] = {}
        self._faker = Faker("en_US")

    def scrub_value(self, value: str, kind: PIIKind) -> str:
        """Return the stable pseudonym for one exact string value."""

        if value in self.mapping:
            return self.mapping[value]

        digest = hmac.new(self.salt, value.encode(), hashlib.sha256).digest()
        n = int.from_bytes(digest[:8], "big")
        fake = self._fake_value(value, kind, digest, n)
        self.mapping[value] = fake
        return fake

    def scrub_text(self, text: str) -> tuple[str, ScrubSummary]:
        """Scrub scanner matches one line at a time without changing line boundaries."""

        replaced: Counter[str] = Counter()
        scrubbed_lines: list[str] = []
        for line in text.splitlines(keepends=True):
            scrubbed, line_counts = self._scrub_spans(line)
            replaced.update(line_counts)
            scrubbed_lines.append(scrubbed)

        output = "".join(scrubbed_lines)
        self._raise_for_residuals([output])
        return output, ScrubSummary(_ordered_counts(replaced), {})

    def scrub_dataframe(self, table: LoadedTable) -> tuple[pd.DataFrame, ScrubSummary]:
        """Scrub every non-null value in scanner-flagged dataframe columns."""

        scrubbed = table.df.copy()
        replaced: Counter[str] = Counter()
        by_column: dict[str, dict[str, int]] = {}

        reports = scan_dataframe(table.df)
        for column, report in reports.items():
            candidates = {kind: score for kind, score in report.kinds.items() if kind in self.kinds}
            column_counts: Counter[str] = Counter()
            values: list[object] = []
            whole_column_kind = max(candidates, key=candidates.__getitem__) if candidates else None
            for value in table.df[column]:
                if pd.isna(value):
                    values.append(value)
                    continue
                if whole_column_kind is not None:
                    values.append(self.scrub_value(str(value), whole_column_kind))
                    column_counts[whole_column_kind.value] += 1
                else:
                    scrubbed_value, value_counts = self._scrub_spans(str(value))
                    values.append(scrubbed_value)
                    column_counts.update(value_counts)
            scrubbed[column] = pd.Series(values, index=table.df.index, dtype="string")
            if column_counts:
                replaced.update(column_counts)
                by_column[column] = _ordered_counts(column_counts)

        self._raise_for_residuals(
            str(value) for column in scrubbed.columns for value in scrubbed[column].dropna()
        )
        return scrubbed, ScrubSummary(_ordered_counts(replaced), by_column)

    def _scrub_spans(self, text: str) -> tuple[str, Counter[str]]:
        matches = [match for match in scan_text(text) if match.kind in self.kinds]
        matches = _non_overlapping(matches)
        scrubbed = text
        replaced: Counter[str] = Counter()
        for match in sorted(matches, key=lambda item: item.start, reverse=True):
            fake = self.scrub_value(match.value, match.kind)
            scrubbed = f"{scrubbed[: match.start]}{fake}{scrubbed[match.end :]}"
            replaced[match.kind.value] += 1
        return scrubbed, replaced

    def _raise_for_residuals(self, values: Iterable[object]) -> None:
        known_fakes = set(self.mapping.values())
        residuals: Counter[str] = Counter()
        for value in values:
            for match in scan_text(str(value)):
                if match.kind in self.kinds and not _covered_by_known_fake(
                    match.value, known_fakes, self.kinds
                ):
                    residuals[match.kind.value] += 1
        if residuals:
            details = ", ".join(
                f"{kind}={count}" for kind, count in _ordered_counts(residuals).items()
            )
            raise ValueError(
                f"scrub stopped: detected selected PII remained after replacement ({details})"
            )

    def _fake_value(self, value: str, kind: PIIKind, digest: bytes, n: int) -> str:
        if kind == PIIKind.EMAIL:
            return self._fake_email(value, n)
        if kind == PIIKind.NAME:
            return self._fake_name(value, n)
        if kind == PIIKind.PHONE:
            return _fake_phone(value, digest)
        if kind == PIIKind.SSN:
            return _fake_ssn(value, digest)
        if kind == PIIKind.CREDIT_CARD:
            return _fake_credit_card(value, digest)
        if kind == PIIKind.IP:
            return _fake_ip(value, digest)
        if kind == PIIKind.SECRET:
            return f"FK_SECRET_{digest.hex()[:8]}"
        raise ValueError(f"unsupported PII kind: {kind}")

    def _fake_email(self, value: str, n: int) -> str:
        # flagged columns get scrubbed wholesale, so stragglers like "unknown"
        # land here too — fall back to a plain fake instead of blowing up
        self._faker.seed_instance(n)
        if "@" not in value:
            return f"{self._faker.user_name()}@{self._faker.domain_word()}.com"
        _, domain = value.rsplit("@", 1)
        tld = domain.rsplit(".", 1)[-1] if "." in domain else "com"
        return f"{self._faker.user_name()}@{self._faker.domain_word()}.{tld}"

    def _fake_name(self, value: str, n: int) -> str:
        self._faker.seed_instance(n)
        if len(value.split()) == 1:
            return self._faker.first_name()
        return f"{self._faker.first_name()} {self._faker.last_name()}"


def _non_overlapping(matches: list[PIIMatch]) -> list[PIIMatch]:
    ranked = sorted(
        matches,
        key=lambda match: (-_MATCH_PRIORITY[match.kind], match.end - match.start, match.start),
    )
    coverage = _SpanCoverage(ranked)
    selected: list[PIIMatch] = []
    for match in ranked:
        if coverage.overlaps(match):
            continue
        selected.append(match)
        coverage.add(match)
    return selected


class _SpanCoverage:
    """Index accepted spans without rescanning every earlier match."""

    def __init__(self, matches: list[PIIMatch]) -> None:
        self._points = sorted({point for match in matches for point in (match.start, match.end)})
        self._indices = {point: index for index, point in enumerate(self._points)}
        self._tree = [0] * (len(self._points) + 1)

    def overlaps(self, match: PIIMatch) -> bool:
        left, right = self._bounds(match)
        return self._prefix(right) != self._prefix(left)

    def add(self, match: PIIMatch) -> None:
        left, right = self._bounds(match)
        # Accepted spans are disjoint, so every compressed segment is marked once.
        for segment in range(left, right):
            cursor = segment + 1
            while cursor < len(self._tree):
                self._tree[cursor] += 1
                cursor += cursor & -cursor

    def _bounds(self, match: PIIMatch) -> tuple[int, int]:
        return self._indices[match.start], self._indices[match.end]

    def _prefix(self, end: int) -> int:
        total = 0
        while end:
            total += self._tree[end]
            end -= end & -end
        return total


def _ordered_counts(counts: Counter[str]) -> dict[str, int]:
    return {kind.value: counts[kind.value] for kind in PIIKind if counts[kind.value]}


def _covered_by_known_fake(value: str, known_fakes: set[str], kinds: set[PIIKind]) -> bool:
    if value in known_fakes:
        return True

    # Prefix-secret matches include labels such as ``token=`` around our tombstone.
    # Pull only the fixed-format tombstones, then use the set index instead of
    # searching every generated fake for every output match.
    fragments: list[str] = []
    cursor = 0
    found = False
    for match in _FAKE_SECRET_RE.finditer(value):
        if match.group() not in known_fakes:
            continue
        fragments.append(value[cursor : match.start()])
        cursor = match.end()
        found = True
    if not found:
        return False
    fragments.append(value[cursor:])
    remainder = "".join(fragments)
    return not any(match.kind in kinds for match in scan_text(remainder))


def _map_digits(value: str, digits: str) -> str:
    mapped = iter(digits)
    return "".join(next(mapped) if char.isdigit() else char for char in value)


def _fake_phone(value: str, digest: bytes) -> str:
    count = sum(char.isdigit() for char in value)
    if count == 0:
        d = [str(byte % 10) for byte in digest[:10]]
        return f"({d[0]}{d[1]}{d[2]}) {d[3]}{d[4]}{d[5]}-{d[6]}{d[7]}{d[8]}{d[9]}"
    digits = "".join(str(byte % 10) for byte in digest[:count])
    fake = _map_digits(value, digits)
    if fake == value:
        replacement = str((int(digits[0]) + 1) % 10) + digits[1:]
        return _map_digits(value, replacement)
    return fake


def _fake_ssn(value: str, digest: bytes) -> str:
    area = 100 + int.from_bytes(digest[:2], "big") % 566
    group = 1 + digest[2] % 99
    serial = 1 + int.from_bytes(digest[3:5], "big") % 9999
    digits = f"{area:03d}{group:02d}{serial:04d}"
    if not any(char.isdigit() for char in value):
        return f"{area:03d}-{group:02d}-{serial:04d}"
    fake = _map_digits(value, digits)
    if fake == value:
        serial = serial % 9999 + 1
        fake = _map_digits(value, f"{area:03d}{group:02d}{serial:04d}")
    return fake


def _fake_credit_card(value: str, digest: bytes) -> str:
    length = sum(char.isdigit() for char in value)
    if length < 8:
        # too few digits to be worth shape-preserving; emit a standard 16
        payload = "".join(str(byte % 10) for byte in digest[:15])
        return payload + _luhn_check_digit(payload)
    payload = "".join(str(byte % 10) for byte in digest[: length - 1])
    digits = payload + _luhn_check_digit(payload)
    fake = _map_digits(value, digits)
    if fake == value:
        payload = str((int(payload[0]) + 1) % 10) + payload[1:]
        fake = _map_digits(value, payload + _luhn_check_digit(payload))
    return fake


def _luhn_check_digit(payload: str) -> str:
    for digit in "0123456789":
        candidate = payload + digit
        parity = len(candidate) % 2
        total = 0
        for index, char in enumerate(candidate):
            value = int(char)
            if index % 2 == parity:
                value = value * 2 - 9 if value > 4 else value * 2
            total += value
        if total % 10 == 0:
            return digit
    raise AssertionError("a Luhn check digit always exists")


def _fake_ip(value: str, digest: bytes) -> str:
    octets = [min(254, max(1, byte % 256)) for byte in digest[:4]]
    fake = ".".join(str(octet) for octet in octets)
    if fake == value:
        octets[-1] = octets[-1] % 254 + 1
        fake = ".".join(str(octet) for octet in octets)
    return fake
