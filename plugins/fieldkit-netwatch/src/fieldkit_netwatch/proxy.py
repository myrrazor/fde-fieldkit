from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

from fieldkit_netwatch.destinations import identify_service, ip_scope, normalize_host, sanitize_path
from fieldkit_netwatch.models import EventDecision, Mode
from fieldkit_netwatch.policy import Policy, PolicyDecision
from fieldkit_netwatch.store import Store

HEADER_LIMIT = 64 * 1024
STREAM_CHUNK = 64 * 1024


@dataclass(frozen=True)
class ProxyAddresses:
    """Loopback listeners exposed to a supervised command."""

    http_host: str
    http_port: int
    socks_host: str
    socks_port: int

    @property
    def http_url(self) -> str:
        """Return the HTTP proxy URL."""

        return f"http://{self.http_host}:{self.http_port}"

    @property
    def socks_url(self) -> str:
        """Return the DNS-capable SOCKS proxy URL."""

        return f"socks5h://{self.socks_host}:{self.socks_port}"


@dataclass(frozen=True)
class _Candidate:
    ip: str
    family: socket.AddressFamily
    decision: PolicyDecision


class ProxyServer:
    """Metadata-only HTTP and SOCKS5 proxy bound to loopback."""

    def __init__(
        self,
        *,
        store: Store,
        session_id: str,
        policy: Policy,
        mode: Mode,
        host: str = "127.0.0.1",
    ):
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError("netwatch proxy listeners must bind to loopback")
        self.store = store
        self.session_id = session_id
        self.policy = policy
        self.mode = mode
        self.host = host
        self._http: asyncio.AbstractServer | None = None
        self._socks: asyncio.AbstractServer | None = None

    async def start(self) -> ProxyAddresses:
        """Start HTTP and SOCKS listeners on OS-selected ports."""

        self._http = await asyncio.start_server(
            self._handle_http,
            self.host,
            0,
            limit=HEADER_LIMIT,
        )
        try:
            self._socks = await asyncio.start_server(
                self._handle_socks,
                self.host,
                0,
                limit=HEADER_LIMIT,
            )
        except Exception:
            self._http.close()
            await self._http.wait_closed()
            self._http = None
            raise
        return ProxyAddresses(
            http_host=self.host,
            http_port=_server_port(self._http),
            socks_host=self.host,
            socks_port=_server_port(self._socks),
        )

    async def close(self) -> None:
        """Stop accepting new connections and close both listeners."""

        servers = [server for server in (self._http, self._socks) if server is not None]
        for server in servers:
            server.close()
        await asyncio.gather(*(server.wait_closed() for server in servers))
        self._http = None
        self._socks = None

    async def __aenter__(self) -> ProxyServer:
        await self.start()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def _handle_http(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            raw_head = await reader.readuntil(b"\r\n\r\n")
            method, target, version, headers = _parse_http_head(raw_head)
            if method == "CONNECT":
                host, port = _parse_authority(target, 443)
                await self._http_connect(reader, writer, host, port)
            else:
                host, port, origin_target = _http_destination(target, headers)
                await self._http_forward(
                    reader,
                    writer,
                    method,
                    origin_target,
                    version,
                    headers,
                    host,
                    port,
                )
        except (asyncio.IncompleteReadError, asyncio.LimitOverrunError, ValueError):
            await _write_http_error(writer, 400, "invalid proxy request")
        except Exception:
            await _write_http_error(writer, 502, "proxy connection failed")
        finally:
            await _close_writer(writer)

    async def _http_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        host: str,
        port: int,
    ) -> None:
        candidate = await self._candidate(host, port, "https")
        if candidate is None:
            await self._record_resolution_failure(
                source="http-connect",
                protocol="https",
                method="CONNECT",
                host=host,
                port=port,
            )
            await _write_http_error(writer, 502, "destination could not be resolved")
            return
        event_id = self._begin_event(
            source="http-connect",
            protocol="https",
            method="CONNECT",
            host=host,
            port=port,
            candidate=candidate,
            path=None,
        )
        if candidate.decision.outcome is EventDecision.BLOCKED:
            self.store.finish_network_event(event_id)
            await _write_http_error(writer, 403, "blocked by netwatch policy")
            return

        upstream_reader, upstream_writer = await self._open_upstream(candidate, port, event_id)
        if upstream_reader is None or upstream_writer is None:
            await _write_http_error(writer, 502, "destination connection failed")
            return
        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()
        try:
            sent, received = await _relay_duplex(reader, writer, upstream_reader, upstream_writer)
            self.store.finish_network_event(
                event_id,
                bytes_sent=sent,
                bytes_received=received,
            )
        except Exception as exc:
            self.store.finish_network_event(
                event_id,
                detail=f"tunnel transfer failed ({type(exc).__name__})",
                decision=_failure_decision(candidate.decision.outcome),
            )
            raise
        finally:
            await _close_writer(upstream_writer)

    async def _http_forward(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        method: str,
        origin_target: str,
        version: str,
        headers: list[tuple[str, str]],
        host: str,
        port: int,
    ) -> None:
        candidate = await self._candidate(host, port, "http")
        path = sanitize_path(origin_target)
        if candidate is None:
            await self._record_resolution_failure(
                source="http-forward",
                protocol="http",
                method=method,
                host=host,
                port=port,
                path=path,
            )
            await _write_http_error(writer, 502, "destination could not be resolved")
            return
        event_id = self._begin_event(
            source="http-forward",
            protocol="http",
            method=method,
            host=host,
            port=port,
            candidate=candidate,
            path=path,
        )
        if candidate.decision.outcome is EventDecision.BLOCKED:
            self.store.finish_network_event(event_id)
            await _write_http_error(writer, 403, "blocked by netwatch policy")
            return

        upstream_reader, upstream_writer = await self._open_upstream(candidate, port, event_id)
        if upstream_reader is None or upstream_writer is None:
            await _write_http_error(writer, 502, "destination connection failed")
            return
        sent = 0
        received = 0
        try:
            outgoing_head = _forward_head(
                method,
                origin_target,
                version,
                headers,
                host,
                port,
            )
            upstream_writer.write(outgoing_head)
            await upstream_writer.drain()
            sent += len(outgoing_head)
            sent += await _forward_request_body(reader, upstream_writer, headers)
            received = await _copy_stream(upstream_reader, writer)
            self.store.finish_network_event(
                event_id,
                bytes_sent=sent,
                bytes_received=received,
            )
        except Exception as exc:
            self.store.finish_network_event(
                event_id,
                bytes_sent=sent,
                bytes_received=received,
                detail=f"upstream transfer failed ({type(exc).__name__})",
                decision=_failure_decision(candidate.decision.outcome),
            )
            raise
        finally:
            await _close_writer(upstream_writer)

    async def _handle_socks(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        upstream_writer: asyncio.StreamWriter | None = None
        try:
            version, method_count = await reader.readexactly(2)
            if version != 5:
                return
            methods = await reader.readexactly(method_count)
            if 0 not in methods:
                writer.write(b"\x05\xff")
                await writer.drain()
                return
            writer.write(b"\x05\x00")
            await writer.drain()

            request_version, command, _reserved, address_type = await reader.readexactly(4)
            if request_version != 5:
                raise ValueError("invalid SOCKS request version")
            host = await _read_socks_host(reader, address_type)
            port = int.from_bytes(await reader.readexactly(2), "big")
            if command != 1:
                event_id = self.store.begin_network_event(
                    session_id=self.session_id,
                    source="socks5",
                    protocol="tcp",
                    host=host,
                    port=port,
                    scope=ip_scope(host),
                    service=identify_service(host),
                    decision=EventDecision.UNSUPPORTED,
                    detail="SOCKS5 supports CONNECT only; BIND and UDP are not captured",
                )
                self.store.finish_network_event(event_id)
                await _write_socks_reply(writer, 7)
                return

            candidate = await self._candidate(host, port, "tcp")
            if candidate is None:
                await self._record_resolution_failure(
                    source="socks5",
                    protocol="tcp",
                    method="CONNECT",
                    host=host,
                    port=port,
                )
                await _write_socks_reply(writer, 4)
                return
            event_id = self._begin_event(
                source="socks5",
                protocol="tcp",
                method="CONNECT",
                host=host,
                port=port,
                candidate=candidate,
                path=None,
            )
            if candidate.decision.outcome is EventDecision.BLOCKED:
                self.store.finish_network_event(event_id)
                await _write_socks_reply(writer, 2)
                return
            upstream_reader, upstream_writer = await self._open_upstream(candidate, port, event_id)
            if upstream_reader is None or upstream_writer is None:
                await _write_socks_reply(writer, 5)
                return
            await _write_socks_reply(writer, 0)
            try:
                sent, received = await _relay_duplex(
                    reader,
                    writer,
                    upstream_reader,
                    upstream_writer,
                )
                self.store.finish_network_event(
                    event_id,
                    bytes_sent=sent,
                    bytes_received=received,
                )
            except Exception as exc:
                self.store.finish_network_event(
                    event_id,
                    detail=f"SOCKS transfer failed ({type(exc).__name__})",
                    decision=_failure_decision(candidate.decision.outcome),
                )
                raise
        except (asyncio.IncompleteReadError, ValueError):
            with contextlib.suppress(Exception):
                await _write_socks_reply(writer, 1)
        finally:
            if upstream_writer is not None:
                await _close_writer(upstream_writer)
            await _close_writer(writer)

    async def _candidate(self, host: str, port: int, protocol: str) -> _Candidate | None:
        normalized = normalize_host(host)
        try:
            info = await asyncio.get_running_loop().getaddrinfo(
                normalized,
                port,
                type=socket.SOCK_STREAM,
                proto=socket.IPPROTO_TCP,
            )
        except OSError:
            return None
        candidates: list[_Candidate] = []
        seen: set[tuple[socket.AddressFamily, str]] = set()
        for family, _kind, _proto, _canonical, address in info:
            ip = str(ipaddress.ip_address(address[0]))
            key = (family, ip)
            if key in seen:
                continue
            seen.add(key)
            decision = self.policy.evaluate(normalized, ip, port, protocol, self.mode)
            candidates.append(_Candidate(ip, family, decision))
        if not candidates:
            return None
        # A denied answer cannot be bypassed by choosing another DNS result.
        return next(
            (candidate for candidate in candidates if candidate.decision.action.value == "deny"),
            candidates[0],
        )

    def _begin_event(
        self,
        *,
        source: str,
        protocol: str,
        method: str,
        host: str,
        port: int,
        candidate: _Candidate,
        path: str | None,
    ) -> int:
        return self.store.begin_network_event(
            session_id=self.session_id,
            source=source,
            protocol=protocol,
            method=method,
            host=normalize_host(host),
            port=port,
            path=path,
            resolved_ip=candidate.ip,
            scope=ip_scope(candidate.ip),
            service=identify_service(host),
            decision=candidate.decision.outcome,
            rule_id=candidate.decision.rule_id,
            detail=candidate.decision.reason,
        )

    async def _open_upstream(
        self,
        candidate: _Candidate,
        port: int,
        event_id: int,
    ) -> tuple[asyncio.StreamReader | None, asyncio.StreamWriter | None]:
        try:
            return await asyncio.open_connection(candidate.ip, port, family=candidate.family)
        except OSError as exc:
            self.store.finish_network_event(
                event_id,
                detail=f"upstream connection failed ({type(exc).__name__})",
                decision=_failure_decision(candidate.decision.outcome),
            )
            return None, None

    async def _record_resolution_failure(
        self,
        *,
        source: str,
        protocol: str,
        method: str,
        host: str,
        port: int,
        path: str | None = None,
    ) -> None:
        event_id = self.store.begin_network_event(
            session_id=self.session_id,
            source=source,
            protocol=protocol,
            method=method,
            host=normalize_host(host),
            port=port,
            path=path,
            scope="unresolved",
            service=identify_service(host),
            decision=EventDecision.FAILED,
            detail="destination could not be resolved",
        )
        self.store.finish_network_event(event_id)


def _server_port(server: asyncio.AbstractServer) -> int:
    sockets = server.sockets or []
    if not sockets:
        raise RuntimeError("proxy listener did not expose a socket")
    return int(sockets[0].getsockname()[1])


def _parse_http_head(raw: bytes) -> tuple[str, str, str, list[tuple[str, str]]]:
    try:
        lines = raw[:-4].decode("latin-1").split("\r\n")
        method, target, version = lines[0].split(" ", 2)
    except (UnicodeDecodeError, ValueError, IndexError) as exc:
        raise ValueError("invalid HTTP request line") from exc
    if not version.startswith("HTTP/1.") or not method.isascii() or not method.isalpha():
        raise ValueError("invalid HTTP request line")
    headers: list[tuple[str, str]] = []
    for line in lines[1:]:
        if not line or ":" not in line:
            raise ValueError("invalid HTTP header")
        name, value = line.split(":", 1)
        if not name or any(ord(char) < 33 or ord(char) > 126 for char in name):
            raise ValueError("invalid HTTP header")
        cleaned = value.strip()
        if any((ord(char) < 32 and char != "\t") or ord(char) == 127 for char in cleaned):
            raise ValueError("invalid HTTP header")
        headers.append((name, cleaned))
    _validate_http_headers(headers)
    return method.upper(), target, version, headers


def _parse_authority(value: str, default_port: int) -> tuple[str, int]:
    try:
        parsed = urlsplit(f"//{value}")
        if parsed.hostname is None:
            raise ValueError
        port = parsed.port or default_port
    except ValueError as exc:
        raise ValueError(f"invalid proxy destination {value!r}") from exc
    if not 1 <= port <= 65535:
        raise ValueError("destination port must be from 1 through 65535")
    return normalize_host(parsed.hostname), port


def _http_destination(target: str, headers: list[tuple[str, str]]) -> tuple[str, int, str]:
    parsed = urlsplit(target)
    if parsed.scheme:
        if parsed.scheme.lower() != "http" or parsed.hostname is None:
            raise ValueError("plain proxy requests must use http")
        port = parsed.port or 80
        origin = parsed.path or "/"
        if parsed.query:
            origin = f"{origin}?{parsed.query}"
        return normalize_host(parsed.hostname), port, origin
    host_header = next((value for name, value in headers if name.lower() == "host"), None)
    if host_header is None:
        raise ValueError("HTTP proxy request has no Host header")
    host, port = _parse_authority(host_header, 80)
    if not target.startswith("/"):
        raise ValueError("invalid HTTP origin target")
    return host, port, target


def _forward_head(
    method: str,
    target: str,
    version: str,
    headers: list[tuple[str, str]],
    host: str,
    port: int,
) -> bytes:
    authority = f"[{host}]" if ":" in host else host
    if port != 80:
        authority = f"{authority}:{port}"
    lines = [f"{method} {target} {version}", f"Host: {authority}"]
    blocked = {"connection", "host", "proxy-authorization", "proxy-connection"}
    lines.extend(f"{name}: {value}" for name, value in headers if name.lower() not in blocked)
    lines.append("Connection: close")
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1")


def _validate_http_headers(headers: list[tuple[str, str]]) -> None:
    grouped: dict[str, list[str]] = {}
    for name, value in headers:
        grouped.setdefault(name.lower(), []).append(value)
    if len(grouped.get("host", [])) > 1:
        raise ValueError("HTTP proxy request has more than one Host header")
    lengths = grouped.get("content-length", [])
    if len(lengths) > 1:
        raise ValueError("HTTP proxy request has more than one Content-Length")
    if lengths:
        try:
            length = int(lengths[0])
        except ValueError as exc:
            raise ValueError("invalid Content-Length") from exc
        if length < 0:
            raise ValueError("invalid Content-Length")
    transfers = grouped.get("transfer-encoding", [])
    if transfers:
        encodings = ",".join(transfers).replace(" ", "").lower()
        if encodings != "chunked":
            raise ValueError("unsupported Transfer-Encoding")
        if lengths:
            raise ValueError("request cannot combine Transfer-Encoding and Content-Length")


async def _forward_request_body(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    headers: list[tuple[str, str]],
) -> int:
    header_map = {name.lower(): value for name, value in headers}
    if "chunked" in header_map.get("transfer-encoding", "").lower():
        return await _copy_chunked(reader, writer)
    raw_length = header_map.get("content-length")
    if raw_length is None:
        return 0
    try:
        remaining = int(raw_length)
    except ValueError as exc:
        raise ValueError("invalid Content-Length") from exc
    if remaining < 0:
        raise ValueError("invalid Content-Length")
    total = 0
    while remaining:
        chunk = await reader.readexactly(min(remaining, STREAM_CHUNK))
        writer.write(chunk)
        await writer.drain()
        total += len(chunk)
        remaining -= len(chunk)
    return total


async def _copy_chunked(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> int:
    total = 0
    while True:
        line = await reader.readuntil(b"\r\n")
        try:
            size = int(line.split(b";", 1)[0].strip(), 16)
        except ValueError as exc:
            raise ValueError("invalid chunked request body") from exc
        writer.write(line)
        await writer.drain()
        total += len(line)
        if size == 0:
            while True:
                trailer = await reader.readuntil(b"\r\n")
                writer.write(trailer)
                await writer.drain()
                total += len(trailer)
                if trailer == b"\r\n":
                    return total
        chunk = await reader.readexactly(size + 2)
        if not chunk.endswith(b"\r\n"):
            raise ValueError("invalid chunk boundary")
        writer.write(chunk)
        await writer.drain()
        total += len(chunk)


async def _copy_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> int:
    total = 0
    while chunk := await reader.read(STREAM_CHUNK):
        writer.write(chunk)
        await writer.drain()
        total += len(chunk)
    return total


async def _relay_duplex(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    upstream_reader: asyncio.StreamReader,
    upstream_writer: asyncio.StreamWriter,
) -> tuple[int, int]:
    counts = [0, 0]

    async def pump(
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        index: int,
    ) -> None:
        try:
            while chunk := await reader.read(STREAM_CHUNK):
                writer.write(chunk)
                await writer.drain()
                counts[index] += len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            return

    sent_task = asyncio.create_task(pump(client_reader, upstream_writer, 0))
    received_task = asyncio.create_task(pump(upstream_reader, client_writer, 1))
    try:
        done, _pending = await asyncio.wait(
            {sent_task, received_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if received_task in done and not sent_task.done():
            # An upstream close is the end of a tunnel. Waiting for the client to close too
            # deadlocks clients that are still reading the final response.
            sent_task.cancel()
            await asyncio.gather(sent_task, return_exceptions=True)
        elif sent_task in done and not received_task.done():
            with contextlib.suppress(Exception):
                upstream_writer.write_eof()
            await received_task
        if not sent_task.cancelled():
            sent_task.result()
        if not received_task.cancelled():
            received_task.result()
        return counts[0], counts[1]
    finally:
        for task in (sent_task, received_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(sent_task, received_task, return_exceptions=True)


async def _read_socks_host(reader: asyncio.StreamReader, address_type: int) -> str:
    if address_type == 1:
        return str(ipaddress.ip_address(await reader.readexactly(4)))
    if address_type == 4:
        return str(ipaddress.ip_address(await reader.readexactly(16)))
    if address_type == 3:
        length = (await reader.readexactly(1))[0]
        if length == 0:
            raise ValueError("empty SOCKS hostname")
        try:
            return normalize_host((await reader.readexactly(length)).decode("idna"))
        except UnicodeError as exc:
            raise ValueError("invalid SOCKS hostname") from exc
    raise ValueError("invalid SOCKS address type")


async def _write_socks_reply(writer: asyncio.StreamWriter, code: int) -> None:
    writer.write(bytes((5, code, 0, 1, 0, 0, 0, 0, 0, 0)))
    await writer.drain()


async def _write_http_error(writer: asyncio.StreamWriter, status: int, message: str) -> None:
    if writer.is_closing():
        return
    reason = {400: "Bad Request", 403: "Forbidden", 502: "Bad Gateway"}.get(status, "Error")
    body = f"{message}\n".encode()
    writer.write(
        f"HTTP/1.1 {status} {reason}\r\nContent-Type: text/plain\r\n"
        f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n".encode()
        + body
    )
    with contextlib.suppress(ConnectionError):
        await writer.drain()


async def _close_writer(writer: asyncio.StreamWriter) -> None:
    if not writer.is_closing():
        writer.close()
    with contextlib.suppress(ConnectionError, asyncio.CancelledError):
        await writer.wait_closed()


def _failure_decision(current: EventDecision) -> EventDecision:
    return current if current is EventDecision.WOULD_BLOCK else EventDecision.FAILED
