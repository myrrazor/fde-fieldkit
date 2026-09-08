from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fieldkit.cli import app
from fieldkit_tell.sentences import segment
from fieldkit_tell.signals import SIGNALS, Severity, analyze


def _by_name(text: str):
    report = analyze(text)
    return {result.signal: result for result in report.signals}


@pytest.mark.parametrize(
    ("signal", "text", "severity", "evidence_count"),
    [
        (
            "burstiness",
            "One two three four five six. " * 6,
            Severity.STRONG,
            1,
        ),
        (
            "phrase_tells",
            "We delve into a robust, intricate tapestry.",
            Severity.STRONG,
            4,
        ),
        (
            "em_dash",
            "The plan — tested twice — still failed.",
            Severity.STRONG,
            1,
        ),
        (
            "binary_contrast",
            "It's not just a tool — it's a movement.",
            Severity.STRONG,
            1,
        ),
        (
            "colon_reveal",
            "The result: chaos. The reason: haste. The cost: trust.",
            Severity.STRONG,
            3,
        ),
        (
            "puffery",
            "It plays a crucial role in planning and stands as a testament to care.",
            Severity.STRONG,
            2,
        ),
        (
            "weasel",
            "Studies show this works. Experts agree it lasts.",
            Severity.STRONG,
            2,
        ),
        (
            "uniform_structure",
            "We need speed, care, and proof. We value facts, context, and restraint.",
            Severity.STRONG,
            2,
        ),
        (
            "recap_ending",
            "We repaired the loader and documented the odd rows.\n\n"
            "In conclusion, the loader now handles the odd rows.",
            Severity.STRONG,
            1,
        ),
        (
            "formatting_slop",
            "## 🚀 Launch\n\n- **Speed:** quick\n- **Trust:** visible",
            Severity.STRONG,
            3,
        ),
    ],
)
def test_signal_goldens(
    signal: str,
    text: str,
    severity: Severity,
    evidence_count: int,
) -> None:
    result = _by_name(text)[signal]

    assert result.severity == severity
    assert len(result.evidence) == evidence_count
    assert 0 <= result.score <= 1
    assert all(item.excerpt == text[item.start : item.end] for item in result.evidence)


def test_segment_guards_abbreviations_and_splits_markdown() -> None:
    text = (
        "Dr. Rivera tested e.g. short cases. They worked.\n\n## Notes\n- First item\n- Second item"
    )

    doc = segment(text)
    sentences = [text[span.start : span.end] for span in doc.sentences]

    assert sentences == [
        "Dr. Rivera tested e.g. short cases.",
        "They worked.",
        "## Notes",
        "- First item",
        "- Second item",
    ]
    assert len(doc.paragraphs) == 2
    assert all(text[span.start : span.end].strip() for span in (*doc.sentences, *doc.words))


def test_every_signal_appears_even_when_text_is_clean() -> None:
    report = analyze("")

    assert [result.signal for result in report.signals] == [
        function.__name__ for function in SIGNALS
    ]
    assert all(result.severity == Severity.INFO for result in report.signals)
    assert not hasattr(report, "overall")
    assert not hasattr(report, "aggregate")


def test_slop_and_human_controls(fixture_dir: Path) -> None:
    slop = analyze((fixture_dir / "slop_sample.md").read_text(encoding="utf-8"))
    human = analyze((fixture_dir / "human_sample.md").read_text(encoding="utf-8"))

    assert sum(result.severity == Severity.STRONG for result in slop.signals) >= 4
    assert sum(result.severity == Severity.STRONG for result in human.signals) == 0


def test_cli_renders_all_signals_and_writes_json(fixture_dir: Path, tmp_path: Path) -> None:
    output = tmp_path / "tell.json"

    result = CliRunner().invoke(
        app,
        [
            "tell",
            "check",
            str(fixture_dir / "slop_sample.md"),
            "--json",
            str(output),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Stylometric tells" in result.output
    empty = segment("")
    assert all(signal(empty).title in result.output for signal in SIGNALS)
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert len(payload["signals"]) == 10
    assert "overall" not in payload
    assert "aggregate" not in payload


def test_cli_accepts_stdin_and_reports_missing_files(tmp_path: Path) -> None:
    runner = CliRunner()

    stdin = runner.invoke(app, ["tell", "check", "-"], input="A short note.")
    missing = runner.invoke(app, ["tell", "check", str(tmp_path / "missing.md")])

    assert stdin.exit_code == 0, stdin.output
    assert missing.exit_code == 1
    assert "error: file not found" in missing.output
    assert "Traceback" not in missing.output
