from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from urllib.parse import SplitResult, urlsplit, urlunsplit

_SENSITIVE_OPTION = re.compile(
    r"(?i)(?:^|[-_])(api[-_]?key|auth|credential|password|secret|token)(?:$|[-_=])"
)
_UUID = re.compile(
    r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
)
_LONG_TOKEN = re.compile(r"^(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9._~-]{24,}$")

_SERVICES: tuple[tuple[str, str], ...] = (
    ("api.openai.com", "OpenAI API"),
    ("chatgpt.com", "ChatGPT"),
    ("openai.com", "OpenAI"),
    ("api.anthropic.com", "Anthropic API"),
    ("claude.ai", "Claude"),
    ("anthropic.com", "Anthropic"),
    ("github.com", "GitHub"),
    ("githubusercontent.com", "GitHub content"),
    ("githubassets.com", "GitHub assets"),
    ("npmjs.org", "npm"),
    ("npmjs.com", "npm"),
    ("pypi.org", "PyPI"),
    ("pythonhosted.org", "PyPI files"),
    ("huggingface.co", "Hugging Face"),
    ("googleapis.com", "Google APIs"),
    ("google.com", "Google"),
    ("microsoft.com", "Microsoft"),
    ("azure.com", "Microsoft Azure"),
    ("amazonaws.com", "Amazon Web Services"),
    ("cloudflare.com", "Cloudflare"),
    ("sentry.io", "Sentry"),
    ("statsig.com", "Statsig"),
)


@dataclass(frozen=True)
class Destination:
    """A normalized destination supplied on the command line."""

    host: str
    port: int
    protocol: str


def normalize_host(host: str) -> str:
    """Normalize a hostname or IP literal without performing DNS."""

    value = host.strip().rstrip(".").lower()
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if not value or any(char.isspace() or ord(char) < 32 for char in value):
        raise ValueError(f"invalid destination host {host!r}")
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        try:
            return value.encode("idna").decode("ascii")
        except UnicodeError as exc:
            raise ValueError(f"invalid destination host {host!r}") from exc


def identify_service(host: str) -> str:
    """Identify common services from local hostname rules."""

    normalized = normalize_host(host)
    if normalized in {"localhost", "ip6-localhost"}:
        return "Localhost"
    try:
        ipaddress.ip_address(normalized)
    except ValueError:
        pass
    else:
        return "IP address"
    for suffix, service in _SERVICES:
        if normalized == suffix or normalized.endswith(f".{suffix}"):
            return service
    labels = normalized.split(".")
    return ".".join(labels[-2:]) if len(labels) > 1 else normalized


def ip_scope(value: str | None) -> str:
    """Classify an IP literal for the UI and policy guard."""

    if value is None:
        return "unresolved"
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return "hostname"
    if address.is_loopback:
        return "loopback"
    if address.is_link_local:
        return "link-local"
    if address.is_private:
        return "private"
    if address.is_multicast:
        return "multicast"
    if address.is_reserved or address.is_unspecified:
        return "reserved"
    return "public"


def sanitize_path(path: str | None) -> str | None:
    """Remove query data and redact credential-shaped path segments."""

    if not path:
        return None
    plain = path.split("?", 1)[0].split("#", 1)[0] or "/"
    segments = plain.split("/")
    sanitized: list[str] = []
    redact_next = False
    for segment in segments:
        should_redact = bool(
            segment
            and (
                redact_next
                or _UUID.fullmatch(segment)
                or _LONG_TOKEN.fullmatch(segment)
                or _SENSITIVE_OPTION.search(segment)
            )
        )
        sanitized.append("[redacted]" if should_redact else segment)
        redact_next = bool(segment and _SENSITIVE_OPTION.search(segment))
    return "/".join(sanitized) or "/"


def sanitize_url(value: str | None) -> str | None:
    """Keep an origin and sanitized path while dropping userinfo, query, and fragment."""

    if not value:
        return None
    try:
        parsed = urlsplit(value)
        if not parsed.scheme or not parsed.hostname:
            return sanitize_path(value)
        host = normalize_host(parsed.hostname)
        netloc = f"[{host}]" if ":" in host else host
        if parsed.port is not None:
            netloc = f"{netloc}:{parsed.port}"
        cleaned = SplitResult(parsed.scheme.lower(), netloc, sanitize_path(parsed.path) or "/", "", "")
        return urlunsplit(cleaned)
    except (TypeError, ValueError):
        return "[invalid URL redacted]"


def redact_command(argv: list[str] | tuple[str, ...]) -> tuple[str, ...]:
    """Keep the executable while dropping every command argument from evidence."""

    if not argv:
        return ()
    return (argv[0], "[arguments redacted]") if len(argv) > 1 else (argv[0],)


def parse_destination(value: str, protocol: str = "https") -> Destination:
    """Parse `host[:port]` or a URL into a normalized destination."""

    raw = value.strip()
    if "://" in raw:
        parsed = urlsplit(raw)
        if parsed.hostname is None:
            raise ValueError(f"invalid destination {value!r}")
        selected_protocol = parsed.scheme.lower()
        port = parsed.port or _default_port(selected_protocol)
        return Destination(normalize_host(parsed.hostname), port, selected_protocol)

    selected_protocol = protocol.lower()
    if raw.startswith("["):
        end = raw.find("]")
        if end < 0:
            raise ValueError(f"invalid destination {value!r}")
        host = raw[1:end]
        remainder = raw[end + 1 :]
        port = int(remainder[1:]) if remainder.startswith(":") else _default_port(selected_protocol)
    elif raw.count(":") == 1:
        host, raw_port = raw.rsplit(":", 1)
        port = int(raw_port)
    else:
        host = raw
        port = _default_port(selected_protocol)
    if not 1 <= port <= 65535:
        raise ValueError("destination port must be from 1 through 65535")
    return Destination(normalize_host(host), port, selected_protocol)


def _default_port(protocol: str) -> int:
    defaults = {"http": 80, "https": 443, "tcp": 443}
    try:
        return defaults[protocol]
    except KeyError as exc:
        raise ValueError(f"no default port for protocol {protocol!r}") from exc
