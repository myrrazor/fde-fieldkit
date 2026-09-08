from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fieldkit.cli import app
from fieldkit_tell.lexicon import load_lexicon, phrase_spans
from fieldkit_tell.rewrite import (
    Edit,
    collect_suggestions,
    resolve_edits,
    unslop,
    word_diff,
)
from fieldkit_tell.sentences import segment
from fieldkit_tell.signals import Severity, analyze


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        (
            "In today's fast-paced world, we utilize tools and can leverage notes.",
            "Today, we use tools and can use notes.",
        ),
        (
            "It's worth noting that the build failed.",
            "The build failed.",
        ),
        (
            "Here's the thing: the build failed.",
            "The build failed.",
        ),
        (
            "The first pass worked.\n\nOverall, the build failed.",
            "The first pass worked.\n\nThe build failed.",
        ),
        (
            "This plays a vital role in onboarding.",
            "This matters to onboarding.",
        ),
        (
            "The plan — tested twice — still failed. Another thought — it can wait.",
            "The plan, tested twice, still failed. Another thought. It can wait.",
        ),
        (
            "## 🚀 Launch\n\n- **Speed:** Move carefully.",
            "## Launch\n\n- Speed: Move carefully.",
        ),
    ],
)
def test_each_deterministic_transform_has_exact_output(
    source: str, expected: str
) -> None:
    assert unslop(source).final == expected


def test_single_ordinary_em_dash_is_left_alone() -> None:
    source = "The patch is small — the decision around it is not."

    result = unslop(source)

    assert result.final == source
    assert not result.iterations


@pytest.mark.parametrize("score", ["3—2", "3 — 2"])
def test_digit_dash_score_is_never_normalized(score: str) -> None:
    source = (
        f"We won the match {score} in overtime. "
        "Another thought — it can wait. One more — it also can wait."
    )

    result = unslop(source)

    assert result.final == (
        f"We won the match {score} in overtime. "
        "Another thought. It can wait. One more. It also can wait."
    )


def test_inline_code_spans_are_untouched() -> None:
    source = (
        "We utilize this plan, but keep `harness` and "
        "``teams can leverage this`` literal."
    )

    result = unslop(source)

    assert result.final == (
        "We use this plan, but keep `harness` and "
        "``teams can leverage this`` literal."
    )


@pytest.mark.parametrize("fence", ["```", "~~~"])
def test_fenced_code_blocks_are_untouched(fence: str) -> None:
    source = (
        "Outside, we utilize this plan.\n\n"
        f"{fence}markdown\n\n"
        "Here's the thing: teams can leverage this robust harness.\n"
        "This plays a crucial role in tests — checks — and docs.\n"
        "## 🚀 Example\n"
        "- **Speed:** Keep it literal.\n\n"
        "Overall, teams can leverage this.\n"
        f"{fence}\n"
    )

    result = unslop(source)

    assert result.final == source.replace(
        "Outside, we utilize this plan.",
        "Outside, we use this plan.",
    )


def test_unclosed_fenced_code_block_is_protected_to_end_of_text() -> None:
    source = (
        "Outside, we utilize this plan.\n\n"
        "```text\n"
        "teams can leverage this robust harness\n"
    )

    result = unslop(source)

    assert result.final == source.replace(
        "Outside, we utilize this plan.",
        "Outside, we use this plan.",
    )


@pytest.mark.parametrize(
    ("source", "excerpt"),
    [
        (
            "When it comes to security, details matter.",
            "When it comes to security,",
        ),
        (
            "In the world of finance, trust matters.",
            "In the world of finance,",
        ),
        (
            "In the age of satellites, maps update quickly.",
            "In the age of satellites,",
        ),
    ],
)
def test_object_taking_openers_are_suggestions_not_deletions(
    source: str, excerpt: str
) -> None:
    result = unslop(source)

    assert result.final == source
    assert not result.iterations
    assert any(
        item.pattern == "object_opener" and item.excerpt == excerpt
        for item in result.suggestions
    )


def test_made_a_decision_swap_requires_following_to() -> None:
    unsafe = "She made a decision that surprised everyone."
    safe = "She made a decision to leave."

    assert unslop(unsafe).final == unsafe
    assert unslop(safe).final == "She decided to leave."


def test_overlap_resolution_prefers_transform_priority_then_leftmost() -> None:
    candidates = [
        Edit(0, 10, "puffery", "puffery_table", "lower priority"),
        Edit(0, 5, "plain", "banned_swap", "higher priority"),
        Edit(3, 8, "later", "banned_swap", "overlaps leftmost"),
        Edit(12, 16, "kept", "formatting_cleanup", "separate"),
    ]

    selected = resolve_edits(candidates)

    assert selected == [candidates[1], candidates[3]]


def test_unslop_is_idempotent_and_deterministic() -> None:
    source = (
        "Here's the thing: in today's fast-paced world, teams can leverage a robust "
        "plan — tested twice — and utilize it."
    )

    first = unslop(source)
    again = unslop(source)
    stable = unslop(first.final)

    assert asdict(first) == asdict(again)
    assert stable.final == first.final
    assert stable.iterations == []


@pytest.mark.parametrize(
    ("text", "pattern"),
    [
        ("It's not just a tool — it's a movement.", "binary_contrast"),
        ("The result: chaos.", "colon_reveal"),
        (
            "The patch fixed the crash, highlighting the need for better logs.",
            "trailing_ing",
        ),
        ("Studies show that the process works.", "weasel_attribution"),
        ("Enough.", "dramatic_fragmentation"),
        ("No owner. No deadline. No proof.", "negative_listing"),
        ("What does that mean? We need the owner by Friday.", "rhetorical_question"),
        ("The migration is stable. The future is clear.", "fake_profound_kicker"),
        (
            "We repaired the loader and documented the odd rows.\n\n"
            "In summary, we repaired the loader and documented the odd rows.",
            "whole_recap",
        ),
        ("Teams write clear notes each day. " * 6, "robotic_rhythm"),
    ],
)
def test_judgment_patterns_are_suggestions_only(text: str, pattern: str) -> None:
    suggestions = collect_suggestions(segment(text))

    assert pattern in {item.pattern for item in suggestions}
    assert all(item.excerpt == text[item.start : item.end] for item in suggestions)
    assert all(item.advice and item.llm_instruction for item in suggestions)


def test_word_diff_is_lossless_for_both_sides() -> None:
    original = "We utilize the old plan.\n"
    final = "We use the tested plan.\n"

    operations = word_diff(original, final)

    rebuilt_original = "".join(
        operation.text for operation in operations if operation.op in {"equal", "delete"}
    )
    rebuilt_final = "".join(
        operation.text for operation in operations if operation.op in {"equal", "insert"}
    )
    assert rebuilt_original == original
    assert rebuilt_final == final
    assert {operation.op for operation in operations} == {"equal", "delete", "insert"}


def test_slop_fixture_improves_without_hiding_judgment_calls(fixture_dir: Path) -> None:
    source = (fixture_dir / "slop_sample.md").read_text(encoding="utf-8")
    before = analyze(source)

    result = unslop(source)
    after = analyze(result.final)
    by_name = {signal.signal: signal for signal in after.signals}
    swaps = tuple(load_lexicon().swap_table)

    assert phrase_spans(result.final, list(swaps)) == []
    assert by_name["em_dash"].stats["count"] < _signal(before, "em_dash").stats["count"]
    assert by_name["phrase_tells"].severity != Severity.STRONG
    assert by_name["puffery"].severity != Severity.STRONG
    assert result.suggestions
    assert all(
        item.excerpt == result.final[item.start : item.end] for item in result.suggestions
    )
    assert len(result.iterations) <= 3


def test_iteration_cap_is_honored(fixture_dir: Path) -> None:
    source = (fixture_dir / "slop_sample.md").read_text(encoding="utf-8")

    result = unslop(source, max_iterations=1)

    assert len(result.iterations) <= 1


def test_cli_writes_cleaned_text_json_and_diff(
    fixture_dir: Path, tmp_path: Path
) -> None:
    source = fixture_dir / "slop_sample.md"
    output = tmp_path / "cleaned.md"
    json_path = tmp_path / "rewrite.json"

    result = CliRunner().invoke(
        app,
        [
            "tell",
            "unslop",
            str(source),
            "-o",
            str(output),
            "--diff",
            "--json",
            str(json_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Word diff" in result.output
    assert output.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["original"] == source.read_text(encoding="utf-8")
    assert payload["final"] == output.read_text(encoding="utf-8")
    assert payload["diff"]


def test_cli_requires_output_refuses_overwrite_and_accepts_stdin(
    fixture_dir: Path, tmp_path: Path
) -> None:
    source = fixture_dir / "slop_sample.md"
    runner = CliRunner()

    missing = runner.invoke(app, ["tell", "unslop", str(source)])
    same = runner.invoke(app, ["tell", "unslop", str(source), "-o", str(source)])
    stdin_out = tmp_path / "stdin.txt"
    stdin = runner.invoke(
        app,
        ["tell", "unslop", "-", "-o", str(stdin_out)],
        input="We utilize this plan.",
    )

    assert missing.exit_code == 1
    assert "output is required" in missing.output
    assert same.exit_code == 1
    assert "must be different" in same.output
    assert stdin.exit_code == 0, stdin.output
    assert stdin_out.read_text(encoding="utf-8") == "We use this plan."


def _signal(report, name: str):
    return next(signal for signal in report.signals if signal.signal == name)
