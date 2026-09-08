from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from fieldkit_netwatch.models import Action, EventDecision, Mode
from fieldkit_netwatch.policy import Policy, host_matches


def policy(payload: dict[str, object]) -> Policy:
    return Policy.from_dict({"version": 1, "default": "deny", "rules": [], **payload})


def test_host_wildcards_have_explicit_apex_boundaries() -> None:
    assert host_matches("api.example.com", "API.EXAMPLE.COM.")
    assert host_matches("*.example.com", "api.example.com")
    assert not host_matches("*.example.com", "example.com")
    assert host_matches("**.example.com", "example.com")
    assert host_matches("**.example.com", "deep.api.example.com")
    assert host_matches("*", "anything.test")
    with pytest.raises(ValueError, match="invalid host wildcard"):
        host_matches("api.*.example.com", "api.dev.example.com")


def test_deny_wins_even_when_an_allow_rule_appears_first() -> None:
    rules = [
        {"id": "allow-api", "action": "allow", "hosts": ["*.example.com"]},
        {"id": "deny-prod", "action": "deny", "hosts": ["prod.example.com"]},
    ]
    decision = policy({"default": "allow", "rules": rules}).evaluate(
        "prod.example.com", "8.8.8.8", 443, "https", Mode.ENFORCE
    )
    assert decision.action is Action.DENY
    assert decision.outcome is EventDecision.BLOCKED
    assert decision.rule_id == "deny-prod"


def test_rule_matchers_are_and_across_categories_and_or_within_them() -> None:
    rules = [
        {
            "id": "api-range",
            "action": "allow",
            "hosts": ["api.example.com", "api2.example.com"],
            "ips": ["8.8.8.0/24"],
            "ports": [443, 8443],
            "protocols": ["https"],
        }
    ]
    selected = policy({"rules": rules})
    assert selected.evaluate(
        "api2.example.com", "8.8.8.4", 8443, "https", Mode.ENFORCE
    ).action is Action.ALLOW
    assert selected.evaluate(
        "api2.example.com", "8.8.4.4", 8443, "https", Mode.ENFORCE
    ).action is Action.DENY
    assert selected.evaluate(
        "api2.example.com", "8.8.8.4", 80, "http", Mode.ENFORCE
    ).action is Action.DENY


def test_private_destinations_need_an_explicit_private_allow() -> None:
    unsafe = policy(
        {"default": "allow", "rules": [{"id": "all", "action": "allow", "hosts": ["*"]}]}
    )
    safe = policy(
        {
            "rules": [
                {
                    "id": "dev",
                    "action": "allow",
                    "hosts": ["localhost"],
                    "allow_private": True,
                }
            ]
        }
    )
    assert unsafe.evaluate("localhost", "127.0.0.1", 3000, "http", Mode.ENFORCE).action is Action.DENY
    assert safe.evaluate("localhost", "127.0.0.1", 3000, "http", Mode.ENFORCE).action is Action.ALLOW


def test_audit_records_would_block_but_keeps_the_policy_action() -> None:
    decision = policy({}).evaluate("api.example.com", "8.8.8.8", 443, "https", Mode.AUDIT)
    assert decision.action is Action.DENY
    assert decision.outcome is EventDecision.WOULD_BLOCK


def test_starter_round_trip_allows_loopback_only(tmp_path: Path) -> None:
    path = tmp_path / "policy.json"
    Policy.starter().write(path)
    loaded = Policy.load(path)
    assert loaded.evaluate("localhost", "127.0.0.1", 4321, "tcp", Mode.ENFORCE).action is Action.ALLOW
    assert loaded.evaluate("example.com", "8.8.8.8", 443, "https", Mode.ENFORCE).action is Action.DENY
    assert json.loads(path.read_text())["version"] == 1
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_policy_write_refuses_symlink_destination(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("do not replace")
    link = tmp_path / "policy.json"
    link.symlink_to(target)

    with pytest.raises(ValueError, match="symlinked policy"):
        Policy.starter().write(link)

    assert target.read_text() == "do not replace"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"version": 2, "default": "deny", "rules": []},
        {"version": 1, "default": "drop", "rules": []},
        {"version": 1, "default": "deny", "rules": "nope"},
        {"version": 1, "default": "deny", "rules": [{"id": "x", "action": "allow"}]},
        {
            "version": 1,
            "default": "deny",
            "rules": [{"id": "x", "action": "allow", "hosts": ["*.bad.*"]}],
        },
        {"version": 1, "default": "deny", "rules": [], "surprise": True},
    ],
)
def test_invalid_policies_fail_closed(payload: object) -> None:
    with pytest.raises(ValueError):
        Policy.from_dict(payload)


def test_invalid_json_is_reported(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("{ definitely not json")
    with pytest.raises(ValueError, match="can't read policy"):
        Policy.load(path)
