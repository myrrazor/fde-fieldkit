from __future__ import annotations

import os
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path

_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def ensure_private_regular_file(path: Path) -> None:
    """Create or validate a regular file and force owner-only permissions."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | _NOFOLLOW, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f"private path is not a regular file: {path}")
        os.fchmod(fd, 0o600)
    finally:
        os.close(fd)


def read_or_create_private_file(path: Path, factory: Callable[[], bytes]) -> bytes:
    """Read an owner-only regular file, creating its initial bytes once if absent."""

    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(path, os.O_RDONLY | _NOFOLLOW)
    except FileNotFoundError:
        payload = factory()
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW, 0o600)
        except FileExistsError:
            return read_or_create_private_file(path, factory)
        try:
            _write_all(fd, payload)
            os.fchmod(fd, 0o600)
            os.fsync(fd)
            return payload
        finally:
            os.close(fd)

    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise ValueError(f"private path is not a regular file: {path}")
        os.fchmod(fd, 0o600)
        chunks: list[bytes] = []
        while chunk := os.read(fd, 64 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def atomic_write_private(path: Path, payload: bytes) -> None:
    """Atomically replace a file with owner-only bytes in the same directory."""

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, raw_tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    tmp_path = Path(raw_tmp)
    try:
        _write_all(fd, payload)
        os.fchmod(fd, 0o600)
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(tmp_path, path)
        os.chmod(path, 0o600, follow_symlinks=False)
    finally:
        if fd >= 0:
            os.close(fd)
        tmp_path.unlink(missing_ok=True)


def _write_all(fd: int, payload: bytes) -> None:
    view = memoryview(payload)
    written = 0
    while written < len(view):
        written += os.write(fd, view[written:])
