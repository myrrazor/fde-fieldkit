from pathlib import Path

import pytest


@pytest.fixture
def example_dir() -> Path:
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "examples" / "awcp"
        if (candidate / "support-ticket-triage.yaml").is_file():
            return candidate
    raise FileNotFoundError("examples/awcp not found — run from the monorepo checkout")
