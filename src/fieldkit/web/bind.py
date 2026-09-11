"""Loopback bind helper for `fieldkit serve`."""

from __future__ import annotations

import socket

LOOPBACK = "127.0.0.1"
PREFERRED_PORT = 8765


def bind_loopback(*, port: int | None = None, preferred: int = PREFERRED_PORT) -> tuple[socket.socket, int]:
    """Bind 127.0.0.1 and return the live socket plus the port it landed on.

    No `port`: try `preferred` (8765) first, then any free port.
    Explicit `port`: pin it, or raise OSError if it's taken.
    """

    if port is not None:
        return _listen(port)
    try:
        return _listen(preferred)
    except OSError:
        return _listen(0)


def _listen(port: int) -> tuple[socket.socket, int]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((LOOPBACK, port))
        sock.listen(2048)
    except OSError:
        sock.close()
        raise
    return sock, int(sock.getsockname()[1])
