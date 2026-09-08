from __future__ import annotations

import csv
import json
import math
import random
import re
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timedelta
from pathlib import Path

from faker import Faker
from faker.providers.person.en_US import Provider as PersonProvider
from openpyxl import Workbook

SEED = 1337
FIXTURE_DIR = Path(__file__).resolve().parent
ROOT = FIXTURE_DIR.parents[1]
NAME_DIR = ROOT / "src" / "fieldkit" / "core" / "data"


def main() -> None:
    rng = random.Random(SEED)
    Faker.seed(SEED)
    fake = Faker("en_US")
    fake.seed_instance(SEED)

    first_names = _provider_names(PersonProvider.first_names)
    last_names = _provider_names(PersonProvider.last_names)
    NAME_DIR.mkdir(parents=True, exist_ok=True)
    (NAME_DIR / "first_names.txt").write_text("\n".join(first_names) + "\n", encoding="utf-8")
    (NAME_DIR / "last_names.txt").write_text("\n".join(last_names) + "\n", encoding="utf-8")

    usable_first = [name for name in first_names if name.isascii() and name.isalpha()]
    usable_last = [name for name in last_names if name.isascii() and name.isalpha()]
    customers = [
        _customer(index, rng, fake, usable_first, usable_last) for index in range(1, 151)
    ]
    _write_csv(FIXTURE_DIR / "customers.csv", customers)
    _write_customers_v2(customers, rng, fake, usable_first, usable_last)
    _write_events(customers, rng)
    _write_orders(customers, rng, fake)
    _write_inventory(rng, fake)
    _write_messy(rng)
    _write_log(customers)


def _provider_names(source: object) -> list[str]:
    if isinstance(source, Mapping):
        values: Iterable[object] = source.keys()
    elif isinstance(source, Iterable):
        values = source
    else:
        raise TypeError("Faker's name provider is not iterable")
    seen: set[str] = set()
    names: list[str] = []
    for raw in values:
        name = str(raw).strip().lower()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names[:1000]


def _customer(
    index: int,
    rng: random.Random,
    fake: Faker,
    first_names: list[str],
    last_names: list[str],
) -> dict[str, str]:
    first = rng.choice(first_names).title()
    last = rng.choice(last_names).title()
    email_name = re.sub(r"[^a-z]", "", f"{first}.{last}".lower())
    signup = date(2021, 1, 1) + timedelta(days=rng.randrange(1460))
    mrr = min(2000.0, max(20.0, rng.lognormvariate(math.log(180), 1.0)))
    notes = "" if rng.random() < 0.2 else fake.sentence(nb_words=10)
    return {
        "customer_id": f"CUST-{index:04d}",
        "first_name": first,
        "last_name": last,
        "email": f"{email_name}{index}@example.com",
        "phone": _phone(rng),
        "ssn": _ssn(rng),
        "credit_card": _credit_card(rng),
        "ip_address": _ip(rng),
        "signup_date": signup.isoformat(),
        "plan": rng.choice(("free", "pro", "enterprise")),
        "mrr": f"{mrr:.2f}",
        "seats": str(rng.randint(1, 500)),
        "churned": rng.choice(("true", "false")),
        "notes": notes,
    }


def _phone(rng: random.Random) -> str:
    area = rng.randint(200, 999)
    exchange = rng.randint(200, 999)
    return f"({area:03d}) {exchange:03d}-{rng.randint(0, 9999):04d}"


def _ssn(rng: random.Random) -> str:
    area = rng.choice([value for value in range(1, 900) if value != 666])
    return f"{area:03d}-{rng.randint(1, 99):02d}-{rng.randint(1, 9999):04d}"


def _credit_card(rng: random.Random) -> str:
    body = "4" + "".join(str(rng.randrange(10)) for _ in range(14))
    for check_digit in range(10):
        candidate = body + str(check_digit)
        if _passes_luhn(candidate):
            return candidate
    raise RuntimeError("couldn't make a Luhn-valid card number")


def _passes_luhn(digits: str) -> bool:
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


def _ip(rng: random.Random) -> str:
    return ".".join(
        str(value)
        for value in (
            rng.randint(11, 223),
            rng.randint(0, 255),
            rng.randint(0, 255),
            rng.randint(1, 254),
        )
    )


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _write_customers_v2(
    customers: list[dict[str, str]],
    rng: random.Random,
    fake: Faker,
    first_names: list[str],
    last_names: list[str],
) -> None:
    regions = ("NA", "EMEA", "APAC")
    rows: list[dict[str, str]] = []
    source_rows = customers[:140] + [
        _customer(index, rng, fake, first_names, last_names) for index in range(151, 163)
    ]
    for source in source_rows:
        row = {key: value for key, value in source.items() if key != "ssn"}
        number = int(source["customer_id"].removeprefix("CUST-"))
        if number <= 25:
            row["mrr"] = f"{round(float(source['mrr']) * 1.2, 2):.2f}"
        if number <= 8:
            row["plan"] = "starter"
        row["seats"] = f"{source['seats']}.0"
        row["region"] = regions[(number - 1) % len(regions)]
        rows.append(row)
    _write_csv(FIXTURE_DIR / "customers_v2.csv", rows)


def _write_events(customers: list[dict[str, str]], rng: random.Random) -> None:
    event_types = ("login", "export", "api_call", "page_view", "error")
    start = datetime(2024, 1, 1, 9, 0, 0)
    rows = []
    for index in range(200):
        rows.append(
            {
                "event_id": f"evt_{index + 1:08x}",
                "user_email": rng.choice(customers)["email"],
                "event_type": rng.choice(event_types),
                "ts": (start + timedelta(seconds=rng.randrange(31_536_000))).isoformat(),
                "duration_ms": rng.randint(4, 30_000),
                "ip": _ip(rng),
            }
        )
    with (FIXTURE_DIR / "events.jsonl").open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def _write_orders(
    customers: list[dict[str, str]], rng: random.Random, fake: Faker
) -> None:
    start = datetime(2023, 1, 1, 12, 0, 0)
    rows = []
    for index in range(1, 81):
        rows.append(
            {
                "order_id": f"ORD-{index:06d}",
                "customer_email": rng.choice(customers)["email"],
                "amount": round(rng.uniform(8, 2500), 2),
                "currency": rng.choice(("USD", "EUR")),
                "status": rng.choice(("paid", "refunded", "pending")),
                "created_at": (start + timedelta(hours=rng.randrange(17_520))).isoformat(),
                "shipping": {"city": fake.city(), "country": fake.country_code()},
            }
        )
    (FIXTURE_DIR / "orders.json").write_text(
        json.dumps(rows, indent=2) + "\n", encoding="utf-8"
    )


def _write_inventory(rng: random.Random, fake: Faker) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "inventory"
    sheet.append(
        ["sku", "name", "warehouse", "qty", "unit_cost", "restock_date", "discontinued"]
    )
    for index in range(1, 61):
        sheet.append(
            [
                f"SKU-{index:05d}",
                fake.word().title(),
                rng.choice(("AUS", "FRA", "NRT")),
                rng.randint(0, 5000),
                round(rng.uniform(0.5, 800), 2),
                date(2024, 1, 1) + timedelta(days=rng.randrange(730)),
                rng.choice((True, False)),
            ]
        )
    workbook.save(FIXTURE_DIR / "inventory.xlsx")


def _write_messy(rng: random.Random) -> None:
    rows = []
    for index in range(1, 51):
        started = date(2024, 1, 1) + timedelta(days=index)
        rows.append(
            {
                "id": str(index),
                "label": f"  item {index}  ",
                "started": started.strftime("%Y-%m-%d" if index % 2 else "%m/%d/%Y"),
                "score": "N/A" if index % 7 == 0 else f"{rng.uniform(0, 100):.1f}",
                "legacy_code": "",
                "comment": "null" if index % 6 == 0 else f"legacy row {index}",
            }
        )
    with (FIXTURE_DIR / "messy.tsv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]), delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)


def _write_log(customers: list[dict[str, str]]) -> None:
    start = datetime(2025, 1, 15, 8, 0, 0)
    levels = ("INFO", "DEBUG", "WARN", "ERROR")
    modules = ("auth", "billing", "worker", "api")
    lines = [
        f"{(start + timedelta(seconds=index * 17)).isoformat()} "
        f"{levels[index % len(levels)]} {modules[index % len(modules)]} request_id=req-{index:05d}"
        for index in range(120)
    ]
    for position, customer in zip((5, 12, 19, 26, 33), customers[:5], strict=True):
        lines[position] += f" user={customer['email']}"
    for position, customer in zip((40, 47, 54, 61, 68), customers[5:10], strict=True):
        lines[position] += f" peer={customer['ip_address']}"
    lines[75] += f" callback={customers[10]['phone']}"
    lines[82] += f" callback={customers[11]['phone']}"
    lines[90] += " aws_key=AKIAIOSFODNN7EXAMPLE"
    lines[97] += " token=sk-00000000000000000000000000000000"
    lines[104] += " token=ghp_00000000000000000000000000000000"
    lines[111] += " -----BEGIN RSA PRIVATE KEY-----"
    (FIXTURE_DIR / "app.log").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
