from pathlib import Path

import pytest

from fieldkit_netwatch.models import Mode
from fieldkit_netwatch.store import Store


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(tmp_path / "netwatch.db")


@pytest.fixture
def session_id(store: Store) -> str:
    return store.create_session(
        mode=Mode.AUDIT,
        agent="test",
        command=["test-agent"],
        coverage=("test proxy",),
    ).id

