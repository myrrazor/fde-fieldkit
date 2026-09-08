from pathlib import Path

import pytest


@pytest.fixture
def fixture_dir() -> Path:
    # plugin tests don't see the root conftest; walk up to the monorepo fixture set
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "tests" / "fixtures"
        if (candidate / "customers.csv").is_file():
            return candidate
    raise FileNotFoundError("fieldkit repo fixtures not found — run from the monorepo checkout")
