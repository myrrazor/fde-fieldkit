from __future__ import annotations

import os
from pathlib import Path

from fieldkit.core.private_files import read_or_create_private_file

DEFAULT_SALT_PATH = Path.home() / ".fieldkit" / "salt"


def load_or_create_salt(path: Path = DEFAULT_SALT_PATH) -> bytes:
    """Return the existing salt at path, or create a private 32-byte salt."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if path == DEFAULT_SALT_PATH:
        path.parent.chmod(0o700)
    return read_or_create_private_file(path, lambda: os.urandom(32))
