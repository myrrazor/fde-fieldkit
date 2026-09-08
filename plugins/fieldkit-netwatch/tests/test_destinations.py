from __future__ import annotations

import pytest

from fieldkit_netwatch.destinations import (
    identify_service,
    ip_scope,
    normalize_host,
    parse_destination,
    redact_command,
    sanitize_path,
    sanitize_url,
)


def test_host_normalization_and_service_identification() -> None:
    assert normalize_host("API.OpenAI.com.") == "api.openai.com"
    assert normalize_host("[::1]") == "::1"
    assert normalize_host("bücher.example") == "xn--bcher-kva.example"
    assert identify_service("files.api.openai.com") == "OpenAI API"
    assert identify_service("registry.npmjs.org") == "npm"
    assert identify_service("unknown.example") == "unknown.example"


@pytest.mark.parametrize(
    ("value", "scope"),
    [
        (None, "unresolved"),
        ("example.com", "hostname"),
        ("127.0.0.1", "loopback"),
        ("10.2.3.4", "private"),
        ("169.254.4.2", "link-local"),
        ("8.8.8.8", "public"),
    ],
)
def test_ip_scope(value: str | None, scope: str) -> None:
    assert ip_scope(value) == scope


def test_paths_urls_and_commands_drop_sensitive_content() -> None:
    assert sanitize_path("/v1/users/123?token=top-secret") == "/v1/users/123"
    assert sanitize_path("/token/super-secret-value") == "/[redacted]/[redacted]"
    assert sanitize_path("/jobs/550e8400-e29b-41d4-a716-446655440000") == "/jobs/[redacted]"
    assert (
        sanitize_url("https://alice:secret@example.com/v1/items?api_key=nope#frag")
        == "https://example.com/v1/items"
    )
    assert redact_command(
        ["agent", "--api-key", "real-secret", "--token=also-secret", "private prompt"]
    ) == ("agent", "[arguments redacted]")


def test_destination_parser_handles_urls_hosts_and_ipv6() -> None:
    assert parse_destination("https://API.Example.com/v1?q=secret").host == "api.example.com"
    assert parse_destination("example.com:8443").port == 8443
    assert parse_destination("[::1]:8080", "http").port == 8080
    assert parse_destination("localhost", "tcp").protocol == "tcp"

    with pytest.raises(ValueError, match="no default port"):
        parse_destination("example.com", "udp")
    with pytest.raises(ValueError, match="invalid destination host"):
        normalize_host("bad host")
