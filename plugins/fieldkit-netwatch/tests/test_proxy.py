from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from fieldkit_netwatch.models import Action, EventDecision, Mode
from fieldkit_netwatch.policy import Policy
from fieldkit_netwatch.proxy import ProxyServer
from fieldkit_netwatch.store import Store


async def _listen(
    handler: Callable[[asyncio.StreamReader, asyncio.StreamWriter], Awaitable[None]],
) -> tuple[asyncio.AbstractServer, int]:
    server = await asyncio.start_server(handler, "127.0.0.1", 0)
    sockets = server.sockets or []
    assert sockets
    return server, int(sockets[0].getsockname()[1])


async def _close(server: asyncio.AbstractServer) -> None:
    server.close()
    await server.wait_closed()


def _session(store: Store) -> str:
    return store.create_session(
        mode=Mode.AUDIT,
        agent="proxy-test",
        command=["test"],
        coverage=("test",),
    ).id


def test_http_forward_records_metadata_without_query(tmp_path) -> None:
    async def scenario() -> None:
        hits: list[bytes] = []

        async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            hits.append(await reader.readuntil(b"\r\n\r\n"))
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nOK")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        upstream_server, upstream_port = await _listen(upstream)
        store = Store(tmp_path / "http.db")
        session_id = _session(store)
        proxy = ProxyServer(
            store=store,
            session_id=session_id,
            policy=Policy.starter(),
            mode=Mode.ENFORCE,
        )
        addresses = await proxy.start()
        try:
            reader, writer = await asyncio.open_connection(addresses.http_host, addresses.http_port)
            writer.write(
                f"GET http://127.0.0.1:{upstream_port}/v1/items?token=never-store "
                "HTTP/1.1\r\nHost: policy-bypass.example\r\n\r\n".encode()
            )
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
        finally:
            await proxy.close()
            await _close(upstream_server)

        assert b"200 OK" in response
        assert b"?token=never-store" in hits[0]
        assert f"Host: 127.0.0.1:{upstream_port}".encode() in hits[0]
        assert b"policy-bypass.example" not in hits[0]
        event = store.report(session_id).events[0]
        assert event.decision is EventDecision.ALLOWED
        assert event.path == "/v1/items"
        assert "never-store" not in (event.path or "")
        assert event.bytes_received > 0

    asyncio.run(scenario())


def test_http_proxy_rejects_ambiguous_request_framing(tmp_path) -> None:
    async def scenario() -> None:
        store = Store(tmp_path / "framing.db")
        session_id = _session(store)
        proxy = ProxyServer(
            store=store,
            session_id=session_id,
            policy=Policy.audit_all(),
            mode=Mode.AUDIT,
        )
        addresses = await proxy.start()
        try:
            reader, writer = await asyncio.open_connection(addresses.http_host, addresses.http_port)
            writer.write(
                b"POST http://127.0.0.1:9/ HTTP/1.1\r\n"
                b"Host: 127.0.0.1:9\r\n"
                b"Content-Length: 4\r\n"
                b"Transfer-Encoding: chunked\r\n\r\n"
            )
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
        finally:
            await proxy.close()

        assert b"400 Bad Request" in response
        assert store.report(session_id).events == ()

    asyncio.run(scenario())


def test_enforced_http_denial_never_opens_upstream(tmp_path) -> None:
    async def scenario() -> None:
        hits = 0

        async def upstream(_reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            nonlocal hits
            hits += 1
            writer.close()
            await writer.wait_closed()

        upstream_server, upstream_port = await _listen(upstream)
        store = Store(tmp_path / "blocked.db")
        session_id = _session(store)
        proxy = ProxyServer(
            store=store,
            session_id=session_id,
            policy=Policy(default=Action.DENY, rules=()),
            mode=Mode.ENFORCE,
        )
        addresses = await proxy.start()
        try:
            reader, writer = await asyncio.open_connection(addresses.http_host, addresses.http_port)
            writer.write(
                f"GET http://127.0.0.1:{upstream_port}/ HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{upstream_port}\r\n\r\n".encode()
            )
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
        finally:
            await proxy.close()
            await _close(upstream_server)

        assert b"403 Forbidden" in response
        assert hits == 0
        assert store.report(session_id).events[0].decision is EventDecision.BLOCKED

    asyncio.run(scenario())


def test_audit_would_block_but_relays_the_request(tmp_path) -> None:
    async def scenario() -> None:
        hit = asyncio.Event()

        async def upstream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            await reader.readuntil(b"\r\n\r\n")
            hit.set()
            writer.write(b"HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        upstream_server, upstream_port = await _listen(upstream)
        store = Store(tmp_path / "audit.db")
        session_id = _session(store)
        proxy = ProxyServer(
            store=store,
            session_id=session_id,
            policy=Policy(default=Action.DENY, rules=()),
            mode=Mode.AUDIT,
        )
        addresses = await proxy.start()
        try:
            reader, writer = await asyncio.open_connection(addresses.http_host, addresses.http_port)
            writer.write(
                f"GET http://127.0.0.1:{upstream_port}/ HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{upstream_port}\r\n\r\n".encode()
            )
            await writer.drain()
            response = await reader.read()
            writer.close()
            await writer.wait_closed()
        finally:
            await proxy.close()
            await _close(upstream_server)

        assert b"204 No Content" in response
        assert hit.is_set()
        assert store.report(session_id).events[0].decision is EventDecision.WOULD_BLOCK

    asyncio.run(scenario())


def test_connect_tunnel_relays_bytes_and_records_only_destination(tmp_path) -> None:
    async def scenario() -> None:
        async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            payload = await reader.readexactly(5)
            writer.write(payload.upper())
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        upstream_server, upstream_port = await _listen(echo)
        store = Store(tmp_path / "connect.db")
        session_id = _session(store)
        proxy = ProxyServer(
            store=store,
            session_id=session_id,
            policy=Policy.starter(),
            mode=Mode.ENFORCE,
        )
        addresses = await proxy.start()
        try:
            reader, writer = await asyncio.open_connection(addresses.http_host, addresses.http_port)
            writer.write(
                f"CONNECT 127.0.0.1:{upstream_port} HTTP/1.1\r\n"
                f"Host: 127.0.0.1:{upstream_port}\r\n\r\n".encode()
            )
            await writer.drain()
            assert b"200 Connection Established" in await reader.readuntil(b"\r\n\r\n")
            writer.write(b"hello")
            await writer.drain()
            assert await reader.readexactly(5) == b"HELLO"
            await reader.read()
            writer.close()
            await writer.wait_closed()
        finally:
            await proxy.close()
            await _close(upstream_server)

        event = store.report(session_id).events[0]
        assert event.source == "http-connect"
        assert event.protocol == "https"
        assert event.path is None
        assert event.bytes_sent == 5
        assert event.bytes_received == 5

    asyncio.run(scenario())


def test_socks_connect_is_recorded_and_udp_is_rejected(tmp_path) -> None:
    async def scenario() -> None:
        async def echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            writer.write((await reader.readexactly(4))[::-1])
            await writer.drain()
            writer.close()
            await writer.wait_closed()

        upstream_server, upstream_port = await _listen(echo)
        store = Store(tmp_path / "socks.db")
        session_id = _session(store)
        proxy = ProxyServer(
            store=store,
            session_id=session_id,
            policy=Policy.starter(),
            mode=Mode.ENFORCE,
        )
        addresses = await proxy.start()
        try:
            reader, writer = await asyncio.open_connection(addresses.socks_host, addresses.socks_port)
            writer.write(b"\x05\x01\x00")
            await writer.drain()
            assert await reader.readexactly(2) == b"\x05\x00"
            writer.write(b"\x05\x01\x00\x01\x7f\x00\x00\x01" + upstream_port.to_bytes(2, "big"))
            await writer.drain()
            assert (await reader.readexactly(10))[1] == 0
            writer.write(b"abcd")
            await writer.drain()
            assert await reader.readexactly(4) == b"dcba"
            await reader.read()
            writer.close()
            await writer.wait_closed()

            reader, writer = await asyncio.open_connection(addresses.socks_host, addresses.socks_port)
            writer.write(b"\x05\x01\x00")
            await writer.drain()
            assert await reader.readexactly(2) == b"\x05\x00"
            writer.write(b"\x05\x03\x00\x01\x7f\x00\x00\x01" + upstream_port.to_bytes(2, "big"))
            await writer.drain()
            assert (await reader.readexactly(10))[1] == 7
            writer.close()
            await writer.wait_closed()
        finally:
            await proxy.close()
            await _close(upstream_server)

        report = store.report(session_id)
        assert [event.decision for event in report.events] == [
            EventDecision.ALLOWED,
            EventDecision.UNSUPPORTED,
        ]
        assert report.events[0].source == "socks5"
        assert report.events[0].bytes_sent == 4
        assert report.events[0].bytes_received == 4

    asyncio.run(scenario())


def test_proxy_refuses_non_loopback_listener(store: Store, session_id: str) -> None:
    try:
        ProxyServer(
            store=store,
            session_id=session_id,
            policy=Policy.audit_all(),
            mode=Mode.AUDIT,
            host="0.0.0.0",
        )
    except ValueError as exc:
        assert "loopback" in str(exc)
    else:
        raise AssertionError("public proxy listener should be rejected")
