from __future__ import annotations

import re
from pathlib import Path


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"


def _workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_third_party_actions_are_pinned_to_commits() -> None:
    """Mutable action tags must not enter the release pipeline."""

    workflows = "\n".join(_workflow(path.name) for path in WORKFLOWS.glob("*.yml"))
    uses = re.findall(r"^\s*- uses: ([^\s]+)", workflows, re.MULTILINE)

    assert uses
    assert all(re.fullmatch(r"[^@]+@[0-9a-f]{40}", action) for action in uses)


def test_ci_runs_the_complete_locked_release_gate() -> None:
    """Tests, static checks, site checks, and every workspace build stay required."""

    workflow = _workflow("ci.yml")

    for command in (
        "uv lock --check",
        "uv sync --locked --all-packages",
        "uv run --locked ruff check .",
        "uv run --locked pytest -q",
        "python site/check_site.py",
        "node --check",
        "uv build --all-packages",
    ):
        assert command in workflow


def test_dependency_audit_covers_runtime_workspace_dependencies() -> None:
    """The advisory gate audits every plugin without editable local packages."""

    workflow = _workflow("dep-audit.yml")

    for option in (
        "--locked",
        "--all-packages",
        "--all-extras",
        "--no-dev",
        "--no-emit-workspace",
        "--no-deps",
        "--disable-pip",
    ):
        assert option in workflow
    assert "pip-audit==2.10.1" in workflow


def test_ci_checks_privacy_distributions_and_verified_secret_scanner() -> None:
    """CI must check public history and distributed files, not just application tests."""
    workflow = _workflow("ci.yml")
    assert "fetch-depth: 0" in workflow
    assert "bash scripts/check-public-privacy.sh" in workflow
    assert "python scripts/check_release_artifacts.py dist" in workflow
    assert "sha256sum --check" in workflow
    assert 'git . --log-opts="--all --full-history" --redact' in workflow
