from __future__ import annotations

import csv
import json
import math
import random
import re
import string
import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from io import BytesIO, StringIO
from itertools import accumulate
from typing import Any

import pandas as pd
from faker import Faker
from faker.providers.credit_card.en_US import Provider as CreditCardProvider
from faker.providers.internet.en_US import Provider as InternetProvider
from faker.providers.lorem.en_US import Provider as LoremProvider
from faker.providers.person.en_US import Provider as PersonProvider
from faker.providers.phone_number.en_US import Provider as PhoneProvider

from fieldkit.core.io import MAX_DATASET_BYTES, formula_safe_value
from fieldkit.core.pii import scan_text
from fieldkit_mimic.learn import ColumnSpec, MimicSpec

_PII_KINDS = {"email", "name", "phone", "ssn", "credit_card", "ip", "secret"}


@dataclass(frozen=True)
class _PreparedColumn:
    name: str
    value: Callable[[int, random.Random, Faker], Any]
    controlled_max_bytes: int


def generate(spec: MimicSpec, n: int, seed: int = 0, *, fmt: str = "csv") -> pd.DataFrame:
    """Generate synthetic rows in spec order using a reproducible seed."""

    prepared = _prepare_columns(spec, n)
    _validate_output_budget(prepared, n, fmt)
    return pd.DataFrame.from_records(
        _iter_prepared_rows(prepared, n, seed),
        columns=[column.name for column in spec.columns],
    )


def _iter_prepared_rows(
    columns: list[_PreparedColumn], n: int, seed: int
) -> Iterator[dict[str, Any]]:
    rng = random.Random(seed)
    faker = Faker("en_US")
    faker.seed_instance(seed)
    for row in range(n):
        yield {column.name: column.value(row, rng, faker) for column in columns}


def generate_serialized(
    spec: MimicSpec, n: int, *, seed: int = 0, fmt: str = "csv"
) -> tuple[bytes, list[dict[str, Any]]]:
    """Generate CSV or JSONL incrementally within the dataset-size contract."""

    if fmt not in {"csv", "jsonl"}:
        raise ValueError("web generation format must be csv or jsonl")

    output = _BoundedTextBuffer()
    preview: list[dict[str, Any]] = []
    prepared = _prepare_columns(spec, n)
    columns = [column.name for column in prepared]
    _validate_output_budget(prepared, n, fmt)
    rows = _iter_prepared_rows(prepared, n, seed)

    if fmt == "csv":
        writer = csv.writer(output, lineterminator="\n")
        writer.writerow([formula_safe_value(column) for column in columns])
        for row in rows:
            clean = _json_safe_row(row)
            if len(preview) < 20:
                preview.append(clean)
            writer.writerow(
                [
                    formula_safe_value(clean[column]) if clean[column] is not None else ""
                    for column in columns
                ]
            )
    else:
        for row in rows:
            clean = _json_safe_row(row)
            if len(preview) < 20:
                preview.append(clean)
            output.write(json.dumps(clean, ensure_ascii=False, separators=(",", ":")) + "\n")

    return output.getvalue(), preview


class _BoundedTextBuffer:
    def __init__(self) -> None:
        self._buffer = BytesIO()

    def write(self, text: str) -> int:
        encoded = text.encode("utf-8")
        if self._buffer.tell() + len(encoded) > MAX_DATASET_BYTES:
            raise ValueError("generated dataset exceeds the 50 MB total size limit")
        self._buffer.write(encoded)
        return len(text)

    def getvalue(self) -> bytes:
        return self._buffer.getvalue()


def _json_safe_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: None if pd.isna(value) else value for key, value in row.items()}


def _prepare_columns(spec: MimicSpec, n: int) -> list[_PreparedColumn]:
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        raise ValueError("n must be a non-negative integer")
    names = [column.name for column in spec.columns]
    if any(not isinstance(name, str) or not name for name in names):
        raise ValueError("mimic specs need non-empty text column names")
    if len(names) != len(set(names)):
        raise ValueError("mimic specs need unique column names")
    if any(scan_text(name, column_name=name) for name in names):
        raise ValueError("a column name contains sensitive data — rename it before generating")
    return [_prepare_column(column, n) for column in spec.columns]


def _prepare_column(column: ColumnSpec, n: int) -> _PreparedColumn:
    if not isinstance(column.kind, str):
        raise ValueError(f"column {column.name!r} kind must be text")
    if not isinstance(column.params, dict):
        raise ValueError(f"column {column.name!r} params must be a mapping")
    if not isinstance(column.unique, bool):
        raise ValueError(f"column {column.name!r} unique must be true or false")
    _require_params(column)
    null_rate = _finite_number(column.null_rate, f"column {column.name!r} null_rate")
    if not 0 <= null_rate <= 1:
        raise ValueError(f"column {column.name!r} null_rate must be between 0 and 1")

    if column.kind == "id_pattern":
        pattern = column.params.get("pattern", "####")
        if not isinstance(pattern, str):
            raise ValueError(f"column {column.name!r} pattern must be text")
        start = column.params.get("start", 1)
        if not isinstance(start, int) or isinstance(start, bool):
            raise ValueError(f"column {column.name!r} start must be an integer")
        max_counter = start + max(n - 1, 0)

        def make(row: int, rng: random.Random, _faker: Faker) -> str:
            return _id_value(pattern, start, column.unique, row, rng)

        controlled = max(
            _id_value_bound(pattern, start, column.unique),
            _id_value_bound(pattern, max_counter, column.unique),
        )
    elif column.kind == "categorical":
        values = column.params.get("values")
        if not isinstance(values, dict) or not values:
            raise ValueError(f"column {column.name!r} needs categorical values")
        if not all(isinstance(value, str) for value in values):
            raise ValueError(f"column {column.name!r} categorical values must be text")
        choices = list(values)
        weights = [
            _finite_number(values[value], f"column {column.name!r} categorical weight")
            for value in choices
        ]
        if any(weight < 0 for weight in weights) or not any(weights):
            raise ValueError(f"column {column.name!r} has invalid categorical weights")
        cumulative = list(accumulate(weights))

        def make(_row: int, rng: random.Random, _faker: Faker) -> str:
            return rng.choices(choices, cum_weights=cumulative, k=1)[0]

        controlled = max(len(value.encode("utf-8")) for value in choices)
    elif column.kind == "numeric":
        raw_grid = column.params.get("quantiles")
        if not isinstance(raw_grid, list) or not raw_grid:
            raise ValueError(f"column {column.name!r} needs a quantile grid")
        grid = [_finite_number(value, f"column {column.name!r} quantile") for value in raw_grid]
        decimals = column.params.get("decimals", 0)
        if not isinstance(decimals, int) or isinstance(decimals, bool):
            raise ValueError(f"column {column.name!r} decimals must be an integer")
        try:
            round(0.0, decimals)
        except OverflowError as exc:
            raise ValueError(f"column {column.name!r} decimals are out of range") from exc

        def make(_row: int, rng: random.Random, _faker: Faker) -> int | float:
            return _numeric_value(grid, decimals, rng)

        controlled = _numeric_value_bound(grid, decimals)
    elif column.kind == "datetime":
        fmt = column.params.get("format", "%Y-%m-%d")
        minimum_raw = column.params.get("min")
        maximum_raw = column.params.get("max")
        if not all(isinstance(value, str) for value in (fmt, minimum_raw, maximum_raw)):
            raise ValueError(f"column {column.name!r} has invalid datetime params")
        if len(fmt.encode("utf-8")) * max(n, 1) > MAX_DATASET_BYTES:
            raise ValueError("mimic spec cannot fit the 50 MB total dataset size")
        try:
            minimum = datetime.strptime(minimum_raw, fmt)
            maximum = datetime.strptime(maximum_raw, fmt)
        except ValueError as exc:
            raise ValueError(f"column {column.name!r} has invalid datetime params") from exc
        if maximum < minimum:
            raise ValueError(f"column {column.name!r} datetime max is before min")

        def make(_row: int, rng: random.Random, _faker: Faker) -> str:
            return _datetime_value(minimum, maximum, fmt, rng)

        controlled = _strftime_bound(fmt, minimum, maximum)
    elif column.kind == "boolean":
        rate = _finite_number(
            column.params.get("true_rate", 0.5), f"column {column.name!r} true_rate"
        )
        if not 0 <= rate <= 1:
            raise ValueError(f"column {column.name!r} true_rate must be between 0 and 1")

        def make(_row: int, rng: random.Random, _faker: Faker) -> bool:
            return rng.random() < rate

        controlled = 5
    elif column.kind == "text":
        count = column.params.get("avg_words", 1)
        if not isinstance(count, int) or isinstance(count, bool) or count < 1:
            raise ValueError(f"column {column.name!r} avg_words must be a positive integer")
        word_bytes = _faker_word_bound()
        controlled = count * word_bytes + count - 1

        def make(_row: int, _rng: random.Random, faker: Faker) -> str:
            return _fake_words(faker, count)

    elif column.kind == "secret":
        controlled = 29

        def make(_row: int, rng: random.Random, _faker: Faker) -> str:
            return "fake_" + "".join(
                rng.choice(string.ascii_letters + string.digits) for _ in range(24)
            )

    elif column.kind in _PII_KINDS:
        words = column.params.get("words", 2)
        if column.kind == "name" and words not in {1, 2}:
            raise ValueError(f"column {column.name!r} words must be 1 or 2")
        seen: set[str] = set()

        def make(_row: int, rng: random.Random, faker: Faker) -> str:
            if not column.unique:
                return _pii_value(column.kind, words, faker)
            for attempt in range(64):
                if attempt:
                    faker.seed_instance(rng.randrange(1 << 31))
                value = _pii_value(column.kind, words, faker)
                if value not in seen:
                    seen.add(value)
                    return value
            raise ValueError(
                f"couldn't generate unique {column.kind} values for column {column.name!r}"
            )

        controlled = _pii_value_bound(column.kind, words)
    else:
        raise ValueError(f"column {column.name!r} has unknown kind {column.kind!r}")

    def with_null(row: int, rng: random.Random, faker: Faker) -> Any:
        if rng.random() < null_rate:
            return pd.NA
        return make(row, rng, faker)

    return _PreparedColumn(column.name, with_null, controlled)


def _id_value(pattern: str, start: int, unique: bool, row: int, rng: random.Random) -> str:
    if unique:
        return _render_counter(pattern, start + row, rng)
    return "".join(
        rng.choice(string.digits)
        if char == "#"
        else rng.choice(string.ascii_uppercase)
        if char == "?"
        else char
        for char in pattern
    )


def _render_counter(pattern: str, counter: int, rng: random.Random) -> str:
    width = pattern.count("#")
    if width == 0:
        pattern = f"{pattern}-####"
        width = 4
    digits = str(counter).zfill(width)
    overflow = digits[: max(0, len(digits) - width)]
    digits = digits[-width:]
    output = []
    digit_index = 0
    overflow_written = False
    for char in pattern:
        if char == "#":
            if not overflow_written:
                output.append(overflow)
                overflow_written = True
            output.append(digits[digit_index])
            digit_index += 1
        elif char == "?":
            output.append(rng.choice(string.ascii_uppercase))
        else:
            output.append(char)
    return "".join(output)


def _numeric_value(grid: list[float], decimals: int, rng: random.Random) -> int | float:
    if len(grid) == 1:
        value = grid[0]
    else:
        position = rng.uniform(0, len(grid) - 1)
        left = min(math.floor(position), len(grid) - 2)
        fraction = position - left
        value = grid[left] * (1 - fraction) + grid[left + 1] * fraction
    rounded = round(value, decimals)
    return int(rounded) if decimals == 0 else rounded


def _datetime_value(minimum: datetime, maximum: datetime, fmt: str, rng: random.Random) -> str:
    value = minimum + timedelta(seconds=rng.random() * (maximum - minimum).total_seconds())
    return value.strftime(fmt)


def _validate_output_budget(columns: list[_PreparedColumn], n: int, fmt: str) -> None:
    if fmt not in {"csv", "tsv", "xlsx", "json", "jsonl"}:
        raise ValueError(f"unsupported generation format: {fmt}")
    names = [column.name for column in columns]
    if fmt in {"csv", "tsv", "xlsx"}:
        header = StringIO()
        csv.writer(header, lineterminator="\n").writerow(
            [formula_safe_value(name) for name in names]
        )
        fixed = len(header.getvalue().encode("utf-8")) + n * max(1, len(names))
    else:
        empty_row = (
            json.dumps({name: "" for name in names}, ensure_ascii=False, separators=(",", ":"))
            + "\n"
        )
        fixed = n * len(empty_row.encode("utf-8"))
    controlled = n * sum(column.controlled_max_bytes for column in columns)
    if fixed + controlled > MAX_DATASET_BYTES:
        raise ValueError("mimic spec cannot fit the 50 MB total dataset size")


def _require_params(column: ColumnSpec) -> None:
    allowed = {
        "id_pattern": {"pattern", "start"},
        "categorical": {"values"},
        "numeric": {"quantiles", "decimals"},
        "datetime": {"min", "max", "format"},
        "boolean": {"true_rate"},
        "text": {"avg_words"},
        "name": {"words"},
        "email": set(),
        "phone": set(),
        "ssn": set(),
        "credit_card": set(),
        "ip": set(),
        "secret": set(),
    }.get(column.kind)
    if allowed is None:
        return
    extra = set(column.params) - allowed
    if extra:
        raise ValueError(f"column {column.name!r} has unsupported parameters")


def _finite_number(value: object, label: str) -> float:
    if not isinstance(value, int | float) or isinstance(value, bool):
        raise ValueError(f"{label} must be a number")
    try:
        number = float(value)
    except OverflowError as exc:
        raise ValueError(f"{label} must be finite") from exc
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number


def _faker_word_bound() -> int:
    return max(len(str(word).encode("utf-8")) for word in LoremProvider.word_list)


def _id_value_bound(pattern: str, counter: int, unique: bool) -> int:
    if not unique:
        return len(pattern.encode("utf-8"))
    # This is compile-time only and exactly mirrors the output logic, including
    # negative signs, prefixes, suffixes, and the no-placeholder fallback.
    return len(_render_counter(pattern, counter, random.Random(0)).encode("utf-8"))


def _numeric_value_bound(grid: list[float], decimals: int) -> int:
    if decimals == 0:
        return max(len(str(int(round(value)))) for value in grid)
    return max(
        *(len(str(value)) for value in grid),
        len(str(sys.float_info.max)),
        len(str(-sys.float_info.max)),
        len(str(sys.float_info.min)),
    )


@lru_cache(maxsize=None)
def _pii_value_bound(kind: str, words: object) -> int:
    if kind == "email":
        return (
            _template_bound(InternetProvider.user_name_formats)
            + 1
            + max(len(domain.encode("utf-8")) for domain in InternetProvider.safe_domain_names)
        )
    if kind == "phone":
        return max(len(fmt.encode("utf-8")) for fmt in PhoneProvider.formats)
    if kind == "ssn":
        return len("000-00-0000")
    if kind == "credit_card":
        return max(card.length for card in CreditCardProvider.credit_card_types.values())
    if kind == "ip":
        return len("255.255.255.255")
    formats = ("{{first_name}}",) if words == 1 else PersonProvider.formats
    return _template_bound(formats)


def _template_bound(formats: object) -> int:
    templates = list(formats)
    maximum = 0
    for template in templates:
        text = str(template)
        placeholders = re.findall(r"\{\{([^}]+)}}", text)
        literals = re.sub(r"\{\{[^}]+}}", "", text)
        total = len(literals.encode("utf-8"))
        for placeholder in placeholders:
            values = getattr(PersonProvider, _provider_attribute(placeholder))
            total += max(len(str(value).encode("utf-8")) for value in values)
        maximum = max(maximum, total)
    return maximum


def _provider_attribute(placeholder: str) -> str:
    aliases = {
        "first_name": "first_names",
        "last_name": "last_names",
        "first_name_male": "first_names_male",
        "first_name_female": "first_names_female",
        "prefix_male": "prefixes_male",
        "prefix_female": "prefixes_female",
        "suffix_male": "suffixes_male",
        "suffix_female": "suffixes_female",
    }
    return aliases[placeholder]


def _fake_words(faker: Faker, count: int) -> str:
    output = StringIO()
    for index in range(count):
        if index:
            output.write(" ")
        output.write(faker.word())
    return output.getvalue()


def _strftime_bound(fmt: str, minimum: datetime, maximum: datetime) -> int:
    samples = [minimum, maximum]
    samples.extend(datetime(2000, month, 1) for month in range(1, 13))
    samples.extend(datetime(2000, 1, day) for day in range(3, 10))
    bound = 0
    for token in re.findall(r"%(?:[-_0^#EO]*.)|[^%]+|%$", fmt):
        if token.startswith("%"):
            bound += max(len(value.strftime(token).encode("utf-8")) for value in samples)
        else:
            bound += len(token.encode("utf-8"))
    return bound


def _pii_value(kind: str, words: object, faker: Faker) -> str:
    if kind == "email":
        return faker.email()
    if kind == "phone":
        return faker.phone_number()
    if kind == "ssn":
        return faker.ssn()
    if kind == "credit_card":
        return faker.credit_card_number()
    if kind == "ip":
        return faker.ipv4()
    return faker.first_name() if words == 1 else faker.name()
