from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import re
from pathlib import Path

import pandas as pd
import pytest
from faker import Faker
from typer.testing import CliRunner

from fieldkit.cli import app
from fieldkit.core.io import LoadedTable, load_table
from fieldkit.core.pii import PIIColumnReport, PIIMatch, PIIKind, scan_text
from fieldkit_scrub import Scrubber, load_or_create_salt
from fieldkit_scrub import engine as scrub_engine


def test_salt_is_private_and_reused(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "salt"

    first = load_or_create_salt(path)
    second = load_or_create_salt(path)

    assert len(first) == 32
    assert second == first
    assert path.read_bytes() == first
    assert path.stat().st_mode & 0o777 == 0o600


def test_existing_salt_permissions_are_restricted(tmp_path: Path) -> None:
    path = tmp_path / "salt"
    path.write_bytes(b"s" * 32)
    path.chmod(0o644)

    assert load_or_create_salt(path) == b"s" * 32
    assert path.stat().st_mode & 0o777 == 0o600


def test_dirty_values_in_flagged_columns_do_not_crash() -> None:
    # field data is never clean: an email column with "unknown" in it,
    # a phone column with "n/a" — scrubbing must survive all of it
    scrubber = Scrubber(b"s" * 32)

    fake_email = scrubber.scrub_value("unknown", PIIKind.EMAIL)
    assert "@" in fake_email

    fake_phone = scrubber.scrub_value("n/a", PIIKind.PHONE)
    assert re.fullmatch(r"\(\d{3}\) \d{3}-\d{4}", fake_phone)

    fake_ssn = scrubber.scrub_value("redacted", PIIKind.SSN)
    assert re.fullmatch(r"\d{3}-\d{2}-\d{4}", fake_ssn)

    fake_card = scrubber.scrub_value("none", PIIKind.CREDIT_CARD)
    assert _valid_luhn(fake_card)

    # and identical junk still maps identically
    assert scrubber.scrub_value("unknown", PIIKind.EMAIL) == fake_email


def test_email_uses_exact_hmac_seed_and_preserves_tld() -> None:
    salt = b"s" * 32
    value = "alice@example.com"
    digest = hmac.new(salt, value.encode(), hashlib.sha256).digest()
    n = int.from_bytes(digest[:8], "big")
    faker = Faker("en_US")
    faker.seed_instance(n)
    expected = f"{faker.user_name()}@{faker.domain_word()}.com"

    assert Scrubber(salt).scrub_value(value, PIIKind.EMAIL) == expected


def test_value_formats_stay_plausible_and_change() -> None:
    scrubber = Scrubber(b"format-test" * 4)
    originals = {
        PIIKind.PHONE: "(859) 241-7111",
        PIIKind.SSN: "651-47-5041",
        PIIKind.CREDIT_CARD: "4635166185664053",
        PIIKind.IP: "163.60.235.64",
    }
    fakes = {kind: scrubber.scrub_value(value, kind) for kind, value in originals.items()}

    assert re.fullmatch(r"\(\d{3}\) \d{3}-\d{4}", fakes[PIIKind.PHONE])
    assert re.fullmatch(r"\d{3}-\d{2}-\d{4}", fakes[PIIKind.SSN])
    assert _valid_ssn(fakes[PIIKind.SSN])
    assert _valid_luhn(fakes[PIIKind.CREDIT_CARD])
    assert 1 <= min(int(part) for part in fakes[PIIKind.IP].split("."))
    assert max(int(part) for part in fakes[PIIKind.IP].split(".")) <= 254
    ipaddress.ip_address(fakes[PIIKind.IP])
    assert all(fakes[kind] != original for kind, original in originals.items())


def test_names_keep_word_count_and_secrets_are_tombstoned() -> None:
    salt = b"n" * 32
    scrubber = Scrubber(salt)
    secret = "sk-00000000000000000000000000000000"
    expected_hash = hmac.new(salt, secret.encode(), hashlib.sha256).hexdigest()[:8]

    assert len(scrubber.scrub_value("Shelby", PIIKind.NAME).split()) == 1
    assert len(scrubber.scrub_value("Shelby Joyce", PIIKind.NAME).split()) == 2
    assert scrubber.scrub_value(secret, PIIKind.SECRET) == f"FK_SECRET_{expected_hash}"


def test_exact_values_are_cached_without_normalization() -> None:
    scrubber = Scrubber(b"cache" * 7)
    formatted = scrubber.scrub_value("+1 (555) 111-2222", PIIKind.PHONE)
    compact = scrubber.scrub_value("15551112222", PIIKind.PHONE)

    assert formatted != compact
    assert scrubber.scrub_value("+1 (555) 111-2222", PIIKind.PHONE) == formatted
    assert scrubber.mapping["+1 (555) 111-2222"] == formatted


def test_dataframe_scrubbing_is_deterministic(fixture_dir: Path) -> None:
    table = load_table(fixture_dir / "customers.csv")
    first, summary = Scrubber(b"same-salt" * 4).scrub_dataframe(table)
    second, _ = Scrubber(b"same-salt" * 4).scrub_dataframe(table)
    different, _ = Scrubber(b"other-salt" * 4).scrub_dataframe(table)

    assert first.to_csv(index=False).encode() == second.to_csv(index=False).encode()
    assert first.to_csv(index=False).encode() != different.to_csv(index=False).encode()
    assert summary.replaced == {
        "email": 150,
        "phone": 150,
        "ssn": 150,
        "credit_card": 150,
        "ip": 150,
        "name": 300,
    }
    assert summary.by_column["email"] == {"email": 150}


def test_dataframe_outputs_preserve_pii_shapes(fixture_dir: Path) -> None:
    original = load_table(fixture_dir / "customers.csv")
    output, _ = Scrubber(b"shape-salt" * 4).scrub_dataframe(original)

    assert all(re.fullmatch(r"[^@\s]+@[^@\s]+\.com", value) for value in output["email"])
    assert all(re.fullmatch(r"\(\d{3}\) \d{3}-\d{4}", value) for value in output["phone"])
    assert all(re.fullmatch(r"\d{3}-\d{2}-\d{4}", value) for value in output["ssn"])
    assert all(_valid_ssn(value) for value in output["ssn"])
    assert all(_valid_luhn(value) for value in output["credit_card"])
    assert all(ipaddress.ip_address(value) for value in output["ip_address"])
    for column in ("email", "phone", "ssn", "credit_card", "ip_address"):
        assert (output[column] != original.df[column]).all()


def test_same_salt_preserves_email_joins_across_files(fixture_dir: Path) -> None:
    first = load_table(fixture_dir / "customers.csv")
    second = load_table(fixture_dir / "customers_v2.csv")
    salt = b"join-salt" * 4
    first_output, _ = Scrubber(salt).scrub_dataframe(first)
    second_output, _ = Scrubber(salt).scrub_dataframe(second)
    original_overlap = set(first.df["email"]) & set(second.df["email"])
    expected_overlap = {
        Scrubber(salt).scrub_value(value, PIIKind.EMAIL) for value in original_overlap
    }

    assert set(first_output["email"]) & set(second_output["email"]) == expected_overlap


def test_kind_filter_only_scrubs_selected_columns(fixture_dir: Path) -> None:
    table = load_table(fixture_dir / "customers.csv")
    output, summary = Scrubber(b"kinds" * 7, kinds={PIIKind.EMAIL}).scrub_dataframe(table)

    assert (output["email"] != table.df["email"]).all()
    assert output["phone"].equals(table.df["phone"])
    assert summary.replaced == {"email": 150}
    assert set(summary.by_column) == {"email"}


def test_sparse_pii_is_scrubbed_even_when_column_confidence_is_low() -> None:
    table = LoadedTable(
        pd.DataFrame(
            {
                "note": [
                    "routine field note",
                    "send the extract to sparse.person@example.com",
                    "another ordinary note",
                ]
            },
            dtype="string",
        ),
        fmt="csv",
        source="sparse.csv",
        warnings=[],
    )

    output, summary = Scrubber(b"sparse" * 6, kinds={PIIKind.EMAIL}).scrub_dataframe(table)

    assert "sparse.person@example.com" not in output.at[1, "note"]
    assert "@" in output.at[1, "note"]
    assert summary.replaced == {"email": 1}
    assert summary.by_column == {"note": {"email": 1}}


def test_scrub_fails_closed_if_selected_pii_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def staged_scan(text: str) -> list[PIIMatch]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return []
        return [PIIMatch(PIIKind.EMAIL, 0, len(text), text)]

    monkeypatch.setattr(scrub_engine, "scan_text", staged_scan)

    with pytest.raises(ValueError, match="scrub stopped: detected selected PII remained"):
        Scrubber(b"fail-closed" * 3, kinds={PIIKind.EMAIL}).scrub_text("still-sensitive")


def test_residual_verification_scans_each_unique_fake_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unique replacements must not multiply residual scanner work."""

    row_count = 2_000
    table = LoadedTable(
        pd.DataFrame(
            {"email": [f"person-{index}@example.com" for index in range(row_count)]},
            dtype="string",
        ),
        fmt="csv",
        source="unique.csv",
        warnings=[],
    )
    monkeypatch.setattr(
        scrub_engine,
        "scan_dataframe",
        lambda _frame: {
            "email": PIIColumnReport({PIIKind.EMAIL: 1.0}, 1.0, ["p***@e***.com"])
        },
    )
    scan_calls = 0

    def count_scan(text: str) -> list[PIIMatch]:
        nonlocal scan_calls
        scan_calls += 1
        return [PIIMatch(PIIKind.EMAIL, 0, len(text), text)]

    monkeypatch.setattr(scrub_engine, "scan_text", count_scan)

    output, summary = Scrubber(b"linear-check" * 3).scrub_dataframe(table)

    assert len(output) == row_count
    assert summary.replaced == {"email": row_count}
    assert scan_calls == row_count


def test_overlap_selection_does_constant_index_work_per_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Many disjoint spans and lower-priority overlaps must not rescan accepted spans."""

    span_count = 4_000
    preferred = [
        PIIMatch(PIIKind.EMAIL, index * 24, index * 24 + 18, f"p{index}@example.test")
        for index in range(span_count)
    ]
    shadowed = [
        PIIMatch(PIIKind.NAME, match.start, match.end, match.value) for match in preferred
    ]
    overlap_queries = 0
    marks = 0
    original_overlaps = scrub_engine._SpanCoverage.overlaps
    original_add = scrub_engine._SpanCoverage.add

    def count_overlap(self: object, match: PIIMatch) -> bool:
        nonlocal overlap_queries
        overlap_queries += 1
        return original_overlaps(self, match)  # type: ignore[arg-type]

    def count_add(self: object, match: PIIMatch) -> None:
        nonlocal marks
        marks += 1
        original_add(self, match)  # type: ignore[arg-type]

    monkeypatch.setattr(scrub_engine._SpanCoverage, "overlaps", count_overlap)
    monkeypatch.setattr(scrub_engine._SpanCoverage, "add", count_add)

    selected = scrub_engine._non_overlapping([*shadowed, *reversed(preferred)])

    assert selected == preferred
    assert overlap_queries == span_count * 2
    assert marks == span_count


def test_cli_scrubs_text_and_writes_mapping_only_when_requested(
    fixture_dir: Path, tmp_path: Path
) -> None:
    source = fixture_dir / "app.log"
    output = tmp_path / "scrubbed.log"
    salt = tmp_path / "salt"
    absent_mapping = tmp_path / "absent.json"
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["scrub", str(source), "-o", str(output), "--salt-file", str(salt), "--text"],
    )

    assert result.exit_code == 0, result.output
    scrubbed = output.read_text(encoding="utf-8")
    original = source.read_text(encoding="utf-8")
    raw_values = {match.value for line in original.splitlines() for match in scan_text(line)}
    assert not absent_mapping.exists()
    assert all(raw not in scrubbed for raw in raw_values)
    assert "FK_SECRET_" in scrubbed
    assert len(scrubbed.splitlines()) == len(original.splitlines())

    mapping = tmp_path / "mapping.json"
    mapped_output = tmp_path / "mapped.log"
    mapped = runner.invoke(
        app,
        [
            "scrub",
            str(source),
            "-o",
            str(mapped_output),
            "--salt-file",
            str(salt),
            "--mapping",
            str(mapping),
            "--text",
        ],
    )

    assert mapped.exit_code == 0, mapped.output
    payload = json.loads(mapping.read_text(encoding="utf-8"))
    assert payload
    assert all(original in raw_values for original in payload)
    assert "as sensitive as the original data" in mapped.output
    assert mapped_output.read_bytes() == output.read_bytes()
    assert mapping.stat().st_mode & 0o777 == 0o600


def test_cli_requires_output_and_never_overwrites(fixture_dir: Path) -> None:
    source = fixture_dir / "customers.csv"
    runner = CliRunner()

    missing = runner.invoke(app, ["scrub", str(source)])
    same = runner.invoke(app, ["scrub", str(source), "-o", str(source)])

    assert missing.exit_code == 1
    assert "output is required" in missing.output
    assert same.exit_code == 1
    assert "must be different" in same.output


def _valid_luhn(value: str) -> bool:
    digits = re.sub(r"\D", "", value)
    parity = len(digits) % 2
    total = 0
    for index, char in enumerate(digits):
        digit = int(char)
        if index % 2 == parity:
            digit = digit * 2 - 9 if digit > 4 else digit * 2
        total += digit
    return total % 10 == 0


def _valid_ssn(value: str) -> bool:
    digits = value.replace("-", "")
    area, group, serial = int(digits[:3]), int(digits[3:5]), int(digits[5:])
    return 100 <= area <= 665 and area != 666 and 1 <= group <= 99 and 1 <= serial <= 9999
