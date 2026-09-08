from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

from fieldkit_netwatch.agents import AgentKind
from fieldkit_netwatch.models import EventDecision, Mode
from fieldkit_netwatch.policy import Policy
from fieldkit_netwatch.store import Store
from fieldkit_netwatch.supervisor import run_supervised


CHILD_REQUEST = """
import os
import socket
from urllib.parse import urlsplit

proxy = urlsplit(os.environ["HTTP_PROXY"])
port = os.environ["NETWATCH_TEST_PORT"]
with socket.create_connection((proxy.hostname, proxy.port)) as sock:
    request = (
        f"GET http://127.0.0.1:{port}/agent?secret=drop-me HTTP/1.1\\r\\n"
        f"Host: 127.0.0.1:{port}\\r\\nConnection: close\\r\\n\\r\\n"
    )
    sock.sendall(request.encode())
    response = b""
    while chunk := sock.recv(4096):
        response += chunk
if b"200 OK" not in response:
    raise SystemExit(9)
"""


def test_supervisor_runs_child_through_proxy_and_closes_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def scenario() -> None:
        async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await reader.readuntil(b"\r\n\r\n")
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        server = await asyncio.start_server(upstream, "127.0.0.1", 0)
        sockets = server.sockets or []
        assert sockets
        monkeypatch.setenv("NETWATCH_TEST_PORT", str(sockets[0].getsockname()[1]))
        db = tmp_path / "supervisor.db"
        ready: list[tuple[str, str]] = []
        try:
            result = await run_supervised(
                [sys.executable, "-c", CHILD_REQUEST],
                mode=Mode.ENFORCE,
                policy=Policy.starter(),
                policy_path=None,
                db_path=db,
                agent=AgentKind.GENERIC,
                on_ready=lambda session, addresses, _prepared: ready.append(
                    (session, addresses.http_url)
                ),
            )
        finally:
            server.close()
            await server.wait_closed()

        assert result.exit_code == 0
        assert result.report.session.status == "complete"
        assert result.report.session.root_pid is not None
        assert result.report.events[0].decision is EventDecision.ALLOWED
        assert result.report.events[0].path == "/agent"
        assert ready == [(result.report.session.id, result.report.session.http_proxy)]

    asyncio.run(scenario())


def test_supervisor_records_a_missing_command_as_failed(tmp_path: Path) -> None:
    db = tmp_path / "missing.db"
    missing = f"definitely-not-a-command-{os.getpid()}"
    with pytest.raises(ValueError, match="command not found"):
        asyncio.run(
            run_supervised(
                [missing],
                mode=Mode.AUDIT,
                policy=Policy.audit_all(),
                policy_path=None,
                db_path=db,
                agent=AgentKind.GENERIC,
            )
        )
    sessions = Store(db).list_sessions()
    assert len(sessions) == 1
    assert sessions[0].status == "failed"
    assert sessions[0].note == "supervisor failed (ValueError)"


def test_supervisor_kills_child_when_post_spawn_setup_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "post-spawn.db"
    child_pid: list[int] = []

    def fail_mark_running(_store: Store, _session_id: str, *, root_pid: int, **_kwargs: object) -> None:
        child_pid.append(root_pid)
        raise RuntimeError("mark running failed")

    monkeypatch.setattr(Store, "mark_running", fail_mark_running)
    with pytest.raises(RuntimeError, match="mark running failed"):
        asyncio.run(
            run_supervised(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                mode=Mode.AUDIT,
                policy=Policy.audit_all(),
                policy_path=None,
                db_path=db,
                agent=AgentKind.GENERIC,
            )
        )

    assert child_pid
    with pytest.raises(ProcessLookupError):
        os.kill(child_pid[0], 0)
    sessions = Store(db).list_sessions()
    assert sessions[0].status == "failed"
    assert sessions[0].note == "supervisor failed (RuntimeError)"
