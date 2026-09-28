from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from fieldkit.core.io import load_table
from fieldkit.core.pii import PIIKind, scan_column, scan_dataframe, scan_text


@pytest.mark.parametrize(
    ("column", "kind"),
    [
        ("email", PIIKind.EMAIL),
        ("phone", PIIKind.PHONE),
        ("ssn", PIIKind.SSN),
        ("credit_card", PIIKind.CREDIT_CARD),
        ("ip_address", PIIKind.IP),
        ("first_name", PIIKind.NAME),
        ("last_name", PIIKind.NAME),
    ],
)
def test_customer_pii_columns_are_flagged(
    fixture_dir: Path, column: str, kind: PIIKind
) -> None:
    df = load_table(fixture_dir / "customers.csv").df
    report = scan_dataframe(df)[column]

    assert report.kinds[kind] >= 0.5
    assert report.hit_rate >= 0.5
    assert 1 <= len(report.samples_masked) <= 3


def test_masked_samples_do_not_include_raw_values(fixture_dir: Path) -> None:
    df = load_table(fixture_dir / "customers.csv").df
    reports = scan_dataframe(df)

    for column in ("email", "phone", "ssn", "credit_card", "ip_address", "first_name"):
        raw_values = df[column].dropna().tolist()
        for masked in reports[column].samples_masked:
            assert all(raw not in masked for raw in raw_values)


def test_luhn_invalid_numbers_are_not_credit_cards() -> None:
    report = scan_column(
        pd.Series(["4111111111111112"] * 20, dtype="string"), column_name="credit_card"
    )

    assert PIIKind.CREDIT_CARD not in report.kinds
    assert not any(
        match.kind is PIIKind.CREDIT_CARD for match in scan_text("0.4111111111111111")
    )


def test_order_ids_are_not_secrets(fixture_dir: Path) -> None:
    order_ids = load_table(fixture_dir / "orders.json").df["order_id"]

    assert PIIKind.SECRET not in scan_column(order_ids, column_name="order_id").kinds


def test_ips_are_not_phones() -> None:
    report = scan_column(pd.Series(["163.60.235.64"] * 20, dtype="string"), column_name="ip")

    assert PIIKind.PHONE not in report.kinds
    assert PIIKind.IP in report.kinds


def test_iso_datetimes_are_not_phones(fixture_dir: Path) -> None:
    values = pd.Series(
        [
            "2024-01-15 10:30:00",
            "2025-01-27 00:00:00",
            "2024-01-15 10:30",
            "2024-01-15T10:30:00",
            "15-01-2024 10:30:00",
            "01-15-2024 10:30:00",
            "15-01-2024 10:30",
            "01-15-2024T10:30:00",
        ],
        dtype="string",
    )
    assert PIIKind.PHONE not in scan_column(values, column_name="restock_date").kinds
    assert not any(match.kind is PIIKind.PHONE for match in scan_text("2024-01-15 10:30:00"))
    assert not any(match.kind is PIIKind.PHONE for match in scan_text("15-01-2024 10:30:00"))
    assert not any(match.kind is PIIKind.PHONE for match in scan_text("01-15-2024 10:30:00"))

    inventory = load_table(fixture_dir / "inventory.xlsx")
    assert PIIKind.PHONE not in scan_dataframe(inventory.df)["restock_date"].kinds


def test_real_phones_still_match() -> None:
    phones = [
        "(415) 555-0199",
        "+1 (415) 555-0199",
        "415-555-0199",
        "+441234567890",
        "212.5551234",
        "1234.5678901234",
    ]
    for phone in phones:
        assert any(match.kind is PIIKind.PHONE for match in scan_text(phone)), phone
    report = scan_column(pd.Series(phones * 5, dtype="string"), column_name="phone")
    assert PIIKind.PHONE in report.kinds


def test_bare_ssn_needs_column_hint() -> None:
    values = pd.Series(["123456789"] * 10, dtype="string")

    assert PIIKind.SSN not in scan_column(values, column_name="account_id").kinds
    assert PIIKind.SSN in scan_column(values, column_name="social_number").kinds


def test_scan_text_finds_every_planted_secret_prefix(fixture_dir: Path) -> None:
    text = (fixture_dir / "app.log").read_text(encoding="utf-8")
    secrets = [match.value for match in scan_text(text) if match.kind == PIIKind.SECRET]

    assert any(value.startswith("AKIA") for value in secrets)
    assert any(value.startswith("sk-") for value in secrets)
    assert any(value.startswith("ghp_") for value in secrets)
    assert any(value.startswith("-----BEGIN") for value in secrets)


def test_scan_text_finds_regular_pii() -> None:
    text = "Contact ada@example.com from 203.0.113.42 or (415) 555-0199."
    kinds = {match.kind for match in scan_text(text)}

    assert {PIIKind.EMAIL, PIIKind.IP, PIIKind.PHONE} <= kinds


def test_name_without_header_hint_stays_out_of_column_report() -> None:
    values = pd.Series(["James"] * 10, dtype="string")

    assert PIIKind.NAME in {match.kind for match in scan_text("James")}
    assert PIIKind.NAME not in scan_column(values, column_name="value").kinds


def test_entropy_secret_accepts_punctuation() -> None:
    token = "aB3$dE5!fG7#hJ9%kL2&mN4*"

    assert PIIKind.SECRET in {match.kind for match in scan_text(token)}


def test_entropy_secret_skips_markup_and_javascript_urls() -> None:
    text = "<a href='javascript:alert(1)'>click</a>"

    assert PIIKind.SECRET not in {match.kind for match in scan_text(text)}


def test_quoted_json_tag_and_backtick_secrets_are_masked() -> None:
    from fieldkit_scrub import Scrubber

    lines = [
        'api_key="9f86d081884c7d659a2feaa0c55ad015a3bf4f1b"',
        '{"token":"a8f5f167f44f4964e6c998dee827110c7Qx"}',
        "password='Xk9mQ2vL8nR4pT6wZ1yB3cD5'",
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0",
        # Same shape as a pay key. The live-key prefix is rejected by push protection.
        "STRIPE_KEY=fkpay_51H8xYzAbCdEfGhIjKlMnOpQr",
        "fkpay_51H8xYzAbCdEfGhIjKlMnOpQrStUv",
        'export AWS_SECRET_ACCESS_KEY="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"',
        "<secret>wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY</secret>",
        "`ghs_16C7e42F292c6912E7710c838347Ae178B4a`",
        "token=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
    ]
    secrets = [
        "9f86d081884c7d659a2feaa0c55ad015a3bf4f1b",
        "a8f5f167f44f4964e6c998dee827110c7Qx",
        "Xk9mQ2vL8nR4pT6wZ1yB3cD5",
        "eyJhbGciOiJIUzI1NiJ9",
        "fkpay_51H8xYzAbCdEfGhIjKlMnOpQr",
        "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
        "ghs_16C7e42F292c6912E7710c838347Ae178B4a",
    ]
    scrubber = Scrubber(b"round2-salt")
    scrubbed, _summary = scrubber.scrub_text("\n".join(lines) + "\n")

    for line in lines:
        assert any(match.kind == PIIKind.SECRET for match in scan_text(line))
    for secret in secrets:
        assert secret not in scrubbed
    assert all(kind != PIIKind.SECRET for kind in {match.kind for match in scan_text("[note]")})
    assert all(kind != PIIKind.SECRET for kind in {match.kind for match in scan_text("<b>")})
