from __future__ import annotations

import hashlib
import importlib
import random
import re
from pathlib import Path

import pandas as pd
import pytest
import yaml
from typer.testing import CliRunner

from fieldkit.cli import app
from fieldkit.core.io import LoadedTable, load_table
from fieldkit_mimic import dump_spec, generate, learn_spec, load_spec
from fieldkit_mimic.generate import generate_serialized
from fieldkit_mimic.learn import ColumnSpec, MimicSpec


def test_learn_and_generate_customers_with_independent_pii_providers(fixture_dir: Path) -> None:
    sample = load_table(fixture_dir / "customers.csv")
    spec = learn_spec(sample, name="customers")

    output = generate(spec, 500, seed=42)

    assert len(output) == 500
    assert list(output.columns) == list(sample.df.columns)
    assert set(output["plan"]) <= {"free", "pro", "enterprise"}
    source_null_rate = sample.df["notes"].isna().mean()
    assert abs(output["notes"].isna().mean() - source_null_rate) <= 0.05
    assert output["mrr"].min() >= sample.df["mrr"].astype(float).min()
    assert output["mrr"].max() <= sample.df["mrr"].astype(float).max()
    assert output["customer_id"].is_unique
    assert output["customer_id"].map(lambda value: bool(re.fullmatch(r"CUST-\d{4,}", value))).all()

    # Faker output is independent of the source, but common names may coincide.
    assert output["email"].str.contains("@", na=False).all()
    assert output["phone"].dropna().str.len().gt(0).all()


def test_seed_is_byte_reproducible(fixture_dir: Path) -> None:
    spec = learn_spec(load_table(fixture_dir / "customers.csv"))

    first = generate(spec, 100, seed=7).to_csv(index=False).encode()
    second = generate(spec, 100, seed=7).to_csv(index=False).encode()
    different = generate(spec, 100, seed=8).to_csv(index=False).encode()

    assert first == second
    assert first != different


def test_dump_load_round_trip_and_hand_edit(fixture_dir: Path, tmp_path: Path) -> None:
    sample = load_table(fixture_dir / "customers.csv")
    learned = learn_spec(sample, name="customers")
    first_dump = dump_spec(learned)
    assert first_dump == dump_spec(learned)
    assert "shelbyjoyce1@example.com" not in first_dump
    source_values = sample.df[["email", "first_name", "last_name", "phone"]].stack()
    source_digests = {
        hashlib.sha256(str(value).encode("utf-8")).hexdigest() for value in source_values
    }
    assert all(digest not in first_dump for digest in source_digests)
    assert "exclude_hashes" not in first_dump

    payload = yaml.safe_load(first_dump)
    plan = next(column for column in payload["columns"] if column["name"] == "plan")
    plan["params"]["values"] = {"alpha": 1.0}
    path = tmp_path / "customers.yaml"
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    edited = load_spec(path)
    output = generate(edited, 40, seed=12)

    assert set(output["plan"]) == {"alpha"}
    assert dump_spec(edited) == dump_spec(load_spec(path))


def test_cli_learn_and_one_shot_jsonl(fixture_dir: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    sample = fixture_dir / "customers.csv"
    spec_path = tmp_path / "customers.yaml"

    learned = runner.invoke(app, ["mimic", "learn", str(sample), "-o", str(spec_path)])
    assert learned.exit_code == 0, learned.output
    assert spec_path.is_file()
    assert "wrote" in learned.output

    output_path = tmp_path / "synthetic.jsonl"
    generated = runner.invoke(
        app,
        ["mimic", "generate", str(sample), "-n", "50", "--seed", "3", "-o", str(output_path)],
    )
    assert generated.exit_code == 0, generated.output
    assert f"wrote {output_path} (50 rows)" in generated.output

    rows = pd.read_json(output_path, lines=True)
    assert len(rows) == 50
    assert list(rows.columns) == list(load_table(sample).df.columns)


def test_single_word_name_columns_stay_single_word(fixture_dir: Path) -> None:
    spec = learn_spec(load_table(fixture_dir / "customers.csv"))
    generated = generate(spec, 40, seed=7)

    for value in generated["first_name"].dropna():
        assert len(str(value).split()) == 1


def test_sensitive_columns_never_reuse_or_embed_sample_values(fixture_dir: Path) -> None:
    # ssn/credit_card/ip must be faker-generated: the quantile/id paths would
    # otherwise embed real sample values in the spec itself
    sample = load_table(fixture_dir / "customers.csv")
    spec = learn_spec(sample)
    spec_yaml = dump_spec(spec)
    generated = generate(spec, 300, seed=3)

    for column in ("ssn", "credit_card", "ip_address"):
        source_values = set(sample.df[column].dropna())
        assert source_values.isdisjoint(set(generated[column].dropna()))
        for value in source_values:
            assert value not in spec_yaml


@pytest.mark.parametrize(
    ("kind", "sensitive"),
    [
        ("email", "sparse.person@example.test"),
        ("phone", "+1 (415) 555-0199"),
        ("ssn", "123-45-6789"),
        ("credit_card", "4111111111111111"),
        ("ip", "203.0.113.42"),
        ("name", "James"),
        ("secret", "sk-" + "SyntheticCanary42"),
    ],
)
def test_sparse_sensitive_categorical_values_never_enter_specs(kind: str, sensitive: str) -> None:
    frame = pd.DataFrame(
        {"mixed_field": ["ordinary", sensitive, "routine", "ordinary"]},
        dtype="string",
    )

    spec = learn_spec(LoadedTable(frame, fmt="csv", source="mixed.csv", warnings=[]))
    spec_yaml = dump_spec(spec)

    assert spec.columns[0].kind == kind
    assert sensitive not in spec_yaml
    assert hashlib.sha256(sensitive.encode()).hexdigest() not in spec_yaml


def test_full_and_sparse_secret_fields_generate_source_free_values() -> None:
    full_secret = "ghp_" + "FullSyntheticCanary42"
    sparse_secret = "AKIA" + "SPARSETEST0001"
    frame = pd.DataFrame(
        {
            "credentials": [full_secret, full_secret],
            "mixed": ["ordinary", sparse_secret],
        },
        dtype="string",
    )

    spec = learn_spec(LoadedTable(frame, fmt="csv", source="secrets.csv", warnings=[]))
    spec_yaml = dump_spec(spec)
    output = generate(spec, 5, seed=9)

    assert [column.kind for column in spec.columns] == ["secret", "secret"]
    for value in (full_secret, sparse_secret):
        assert value not in spec_yaml
        assert hashlib.sha256(value.encode()).hexdigest() not in spec_yaml
        assert value not in output.to_string()
    assert output.map(lambda value: str(value).startswith("fake_")).all(axis=None)


def test_sensitive_dataset_name_is_replaced_without_a_portable_mapping() -> None:
    sensitive_name = "owner@example.test"
    frame = pd.DataFrame({"status": ["ready", "done"]}, dtype="string")

    spec = learn_spec(
        LoadedTable(frame, fmt="csv", source="source.csv", warnings=[]),
        name=sensitive_name,
    )
    spec_yaml = dump_spec(spec)

    assert spec.name == "dataset"
    assert sensitive_name not in spec_yaml
    assert hashlib.sha256(sensitive_name.encode()).hexdigest() not in spec_yaml


@pytest.mark.parametrize(
    "sensitive_header",
    ["owner@example.test", "sk-HeaderSyntheticCanary42"],
)
def test_sensitive_column_names_fail_closed_without_echoing_a_mapping(
    sensitive_header: str,
) -> None:
    frame = pd.DataFrame({sensitive_header: ["ordinary"]}, dtype="string")

    with pytest.raises(
        ValueError,
        match="a column name contains sensitive data — rename it before generating",
    ) as exc_info:
        learn_spec(LoadedTable(frame, fmt="csv", source="source.csv", warnings=[]))

    assert sensitive_header not in str(exc_info.value)


@pytest.mark.parametrize(
    "column",
    [
        ColumnSpec("value", "text", {"avg_words": 100}),
        ColumnSpec("value", "id_pattern", {"pattern": "x" * 100}),
        ColumnSpec("value", "categorical", {"values": {"x" * 100: 1.0}}),
        ColumnSpec(
            "value",
            "datetime",
            {"min": "2024", "max": "2025", "format": "%Y" * 100},
        ),
    ],
)
def test_expanding_parameters_are_rejected_before_value_generation(
    column: ColumnSpec, monkeypatch: pytest.MonkeyPatch
) -> None:
    generate_module = importlib.import_module("fieldkit_mimic.generate")
    monkeypatch.setattr(generate_module, "MAX_DATASET_BYTES", 64)
    monkeypatch.setattr(
        generate_module,
        "_fake_words",
        lambda *_args: pytest.fail("value generation started before the budget check"),
    )
    spec = MimicSpec(name="dataset", rows_sampled=1, columns=[column])

    with pytest.raises(ValueError, match="50 MB total dataset size"):
        generate_serialized(spec, 2)


def test_row_and_schema_overhead_are_rejected_before_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_module = importlib.import_module("fieldkit_mimic.generate")
    monkeypatch.setattr(generate_module, "MAX_DATASET_BYTES", 32)
    spec = MimicSpec(
        name="dataset",
        rows_sampled=1,
        columns=[ColumnSpec(f"column_{index}", "boolean") for index in range(4)],
    )

    with pytest.raises(ValueError, match="50 MB total dataset size"):
        generate_serialized(spec, 10)


def test_numeric_lists_and_categorical_cardinality_are_compiled_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_module = importlib.import_module("fieldkit_mimic.generate")
    seen: list[str] = []
    choice_calls: list[tuple[object, object]] = []
    original = generate_module._finite_number
    original_choices = random.Random.choices

    def count_validation(value: object, label: str) -> float:
        seen.append(label)
        return original(value, label)

    def track_choices(
        rng: random.Random,
        population: object,
        weights: object = None,
        *,
        cum_weights: object = None,
        k: int = 1,
    ) -> list[object]:
        choice_calls.append((weights, cum_weights))
        return original_choices(
            rng,
            population,
            weights=weights,
            cum_weights=cum_weights,
            k=k,
        )

    monkeypatch.setattr(generate_module, "_finite_number", count_validation)
    monkeypatch.setattr(random.Random, "choices", track_choices)
    spec = MimicSpec(
        name="dataset",
        rows_sampled=1,
        columns=[
            ColumnSpec("number", "numeric", {"quantiles": list(range(40)), "decimals": 0}),
            ColumnSpec(
                "category",
                "categorical",
                {"values": {f"category-{index}": 1.0 for index in range(40)}},
            ),
        ],
    )

    output = generate(spec, 200)

    assert len(output) == 200
    assert len(seen) == 82  # 40 quantiles + 40 weights + two null-rate checks
    assert all(weights is None and cumulative is not None for weights, cumulative in choice_calls)
    assert len({id(cumulative) for _, cumulative in choice_calls}) == 1


def test_repeated_sensitive_columns_compile_provider_bounds_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_module = importlib.import_module("fieldkit_mimic.generate")
    calls: list[object] = []
    original = generate_module._template_bound

    def track_bound(formats: object) -> int:
        calls.append(formats)
        return original(formats)

    generate_module._pii_value_bound.cache_clear()
    monkeypatch.setattr(generate_module, "_template_bound", track_bound)
    spec = MimicSpec(
        name="dataset",
        rows_sampled=1,
        columns=[ColumnSpec(f"person_{index}", "name", {"words": 2}) for index in range(50)],
    )
    try:
        output = generate(spec, 2)
    finally:
        generate_module._pii_value_bound.cache_clear()

    assert output.shape == (2, 50)
    assert len(calls) == 1


@pytest.mark.parametrize(
    "column",
    [
        ColumnSpec("number", "numeric", {"quantiles": [0.0, float("inf")]}),
        ColumnSpec("flag", "boolean", {"true_rate": float("nan")}),
        ColumnSpec("when", "datetime", {"min": "2025", "max": "2024", "format": "%Y"}),
        ColumnSpec("label", "categorical", {"values": {"a": -1.0, "b": 1.0}}),
    ],
)
def test_invalid_numeric_range_weight_and_date_parameters_fail_closed(
    column: ColumnSpec,
) -> None:
    spec = MimicSpec(name="dataset", rows_sampled=1, columns=[column])

    with pytest.raises(ValueError):
        generate(spec, 1)


def test_huge_yaml_integer_is_a_benign_validation_error(tmp_path: Path) -> None:
    path = tmp_path / "huge-number.yaml"
    path.write_text(
        """name: dataset
rows_sampled: 1
columns:
  - name: value
    kind: numeric
    params:
      quantiles:
        - 1
        - 1"""
        + "0" * 1000
        + "\n      decimals: 0\n",
        encoding="utf-8",
    )

    spec = load_spec(path)
    with pytest.raises(ValueError, match="quantile must be finite"):
        generate(spec, 1)


def test_id_budget_checks_negative_start_and_final_endpoints(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generate_module = importlib.import_module("fieldkit_mimic.generate")
    spec = MimicSpec(
        name="dataset",
        rows_sampled=1,
        columns=[ColumnSpec("id", "id_pattern", {"pattern": "pre-#-suffix", "start": -999}, True)],
    )
    prepared = generate_module._prepare_columns(spec, 999)

    expected = max(
        len(generate_module._render_counter("pre-#-suffix", endpoint, random.Random(0)).encode())
        for endpoint in (-999, -1)
    )

    assert prepared[0].controlled_max_bytes == expected

    monkeypatch.setattr(generate_module, "MAX_DATASET_BYTES", expected)
    with pytest.raises(ValueError, match="50 MB total dataset size"):
        generate_serialized(spec, 2)
