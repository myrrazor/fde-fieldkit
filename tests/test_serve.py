from __future__ import annotations

import socket
import threading
import time

import httpx
import pytest
import uvicorn
from click import unstyle
from typer.testing import CliRunner

from fieldkit.cli import app as cli_app
from fieldkit.web import create_app
from fieldkit.web.bind import PREFERRED_PORT, bind_loopback


runner = CliRunner()


def test_bind_prefers_8765_when_that_port_is_free() -> None:
    blocker = _hold("127.0.0.1", 0)
    try:
        preferred = blocker.getsockname()[1]
    finally:
        blocker.close()

    sock, port = bind_loopback(preferred=preferred)
    try:
        assert port == preferred
        assert sock.getsockname()[0] == "127.0.0.1"
    finally:
        sock.close()


def test_bind_picks_another_port_when_preferred_is_taken() -> None:
    blocker = _hold("127.0.0.1", 0)
    try:
        busy = blocker.getsockname()[1]
        sock, port = bind_loopback(preferred=busy)
        try:
            assert port != busy
            assert sock.getsockname()[0] == "127.0.0.1"
        finally:
            sock.close()
    finally:
        blocker.close()


def test_explicit_port_fails_when_taken() -> None:
    blocker = _hold("127.0.0.1", 0)
    try:
        busy = blocker.getsockname()[1]
        with pytest.raises(OSError):
            bind_loopback(port=busy)
    finally:
        blocker.close()


def test_serve_help_exposes_only_loopback_safe_options() -> None:
    result = runner.invoke(cli_app, ["serve", "--help"])
    output = unstyle(result.output)

    assert result.exit_code == 0
    assert "--host" not in output
    assert "--port" in output
    assert "8765" in output


def test_serve_rejects_host_flag() -> None:
    result = runner.invoke(cli_app, ["serve", "--host", "0.0.0.0"])

    assert result.exit_code != 0
    assert "--host" in result.output or "No such option" in result.output


def test_serve_always_binds_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeServer:
        def __init__(self, config: object) -> None:
            captured["host"] = getattr(config, "host", None)

        def run(self, sockets: list[socket.socket] | None = None) -> None:
            assert sockets
            captured["bound"] = sockets[0].getsockname()

    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    probe = _hold("127.0.0.1", 0)
    free = probe.getsockname()[1]
    probe.close()

    result = runner.invoke(cli_app, ["serve", "--port", str(free)])

    assert result.exit_code == 0, result.output
    assert captured["host"] == "127.0.0.1"
    assert captured["bound"] == ("127.0.0.1", free)
    assert f"http://127.0.0.1:{free}" in result.output


def test_serve_falls_back_and_prints_the_url(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    class FakeServer:
        def __init__(self, config: object) -> None:
            captured["host"] = getattr(config, "host", None)

        def run(self, sockets: list[socket.socket] | None = None) -> None:
            assert sockets
            captured["bound"] = sockets[0].getsockname()

    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    blocker = _hold("127.0.0.1", PREFERRED_PORT)
    try:
        result = runner.invoke(cli_app, ["serve"])

        assert result.exit_code == 0, result.output
        bound = captured["bound"]
        assert isinstance(bound, tuple)
        bound_host, bound_port = bound
        assert bound_host == "127.0.0.1"
        assert bound_port != PREFERRED_PORT
        assert f"http://127.0.0.1:{bound_port}" in result.output
        assert f"port {PREFERRED_PORT} was in use, using {bound_port}" in result.output
    finally:
        blocker.close()


def test_serve_explicit_busy_port_exits_without_picking_another(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ShouldNotStart:
        def __init__(self, config: object) -> None:
            raise AssertionError("serve should not start when the port is taken")

    monkeypatch.setattr(uvicorn, "Server", ShouldNotStart)
    blocker = _hold("127.0.0.1", 0)
    busy = blocker.getsockname()[1]
    try:
        result = runner.invoke(cli_app, ["serve", "--port", str(busy)])
        assert result.exit_code == 1
        assert f"port {busy} is already in use" in result.output
        assert "omit --port" in result.output
    finally:
        blocker.close()


def test_bound_socket_answers_health() -> None:
    sock, port = bind_loopback(port=0)
    config = uvicorn.Config(create_app(), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        for _ in range(100):
            if server.started:
                break
            time.sleep(0.05)
        else:
            raise AssertionError("server did not start")
        response = httpx.get(f"http://127.0.0.1:{port}/api/health", timeout=2.0)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()


def _hold(host: str, port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, port))
    sock.listen(1)
    return sock
