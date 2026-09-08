from __future__ import annotations

import ipaddress
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fieldkit_netwatch.destinations import ip_scope, normalize_host
from fieldkit_netwatch.models import Action, EventDecision, Mode

SUPPORTED_PROTOCOLS = {"http", "https", "tcp"}
RESTRICTED_SCOPES = {"loopback", "private", "link-local", "multicast", "reserved"}


@dataclass(frozen=True)
class Rule:
    """One host/IP/port/protocol policy rule."""

    id: str
    action: Action
    hosts: tuple[str, ...] = ()
    networks: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = ()
    ports: tuple[int, ...] = ()
    protocols: tuple[str, ...] = ()
    allow_private: bool = False
    note: str | None = None

    def matches(self, host: str, ip: str | None, port: int, protocol: str) -> bool:
        """Return whether every configured selector matches the destination."""

        if self.hosts and not any(host_matches(pattern, host) for pattern in self.hosts):
            return False
        if self.networks:
            if ip is None:
                return False
            try:
                address = ipaddress.ip_address(ip)
            except ValueError:
                return False
            if not any(address in network for network in self.networks):
                return False
        if self.ports and port not in self.ports:
            return False
        if self.protocols and protocol not in self.protocols:
            return False
        return bool(self.hosts or self.networks or self.ports or self.protocols)

    def as_dict(self) -> dict[str, object]:
        """Return the stable JSON representation of this rule."""

        payload: dict[str, object] = {"id": self.id, "action": self.action.value}
        if self.hosts:
            payload["hosts"] = list(self.hosts)
        if self.networks:
            payload["ips"] = [str(network) for network in self.networks]
        if self.ports:
            payload["ports"] = list(self.ports)
        if self.protocols:
            payload["protocols"] = list(self.protocols)
        if self.allow_private:
            payload["allow_private"] = True
        if self.note:
            payload["note"] = self.note
        return payload


@dataclass(frozen=True)
class PolicyDecision:
    """The policy action and the mode-dependent observed outcome."""

    action: Action
    outcome: EventDecision
    rule_id: str | None
    reason: str


@dataclass(frozen=True)
class Policy:
    """Versioned destination policy with deny precedence."""

    default: Action
    rules: tuple[Rule, ...]
    version: int = 1

    @classmethod
    def load(cls, path: Path) -> Policy:
        """Read and validate a policy JSON file."""

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError(f"can't read policy {path}: {exc}") from exc
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, payload: object) -> Policy:
        """Validate a decoded policy object."""

        if not isinstance(payload, dict):
            raise ValueError("policy must be a JSON object")
        unknown = set(payload) - {"version", "default", "rules"}
        if unknown:
            raise ValueError(f"unknown policy keys: {', '.join(sorted(unknown))}")
        if payload.get("version") != 1:
            raise ValueError("policy version must be 1")
        try:
            default = Action(payload["default"])
        except (KeyError, ValueError) as exc:
            raise ValueError("policy default must be 'allow' or 'deny'") from exc
        rows = payload.get("rules", [])
        if not isinstance(rows, list):
            raise ValueError("policy rules must be a list")
        rules = tuple(_parse_rule(row, index) for index, row in enumerate(rows, start=1))
        ids = [rule.id for rule in rules]
        if len(ids) != len(set(ids)):
            raise ValueError("policy rule ids must be unique")
        return cls(default=default, rules=rules)

    @classmethod
    def audit_all(cls) -> Policy:
        """Return the built-in non-blocking policy used when audit has no file."""

        return cls(
            default=Action.ALLOW,
            rules=(
                Rule(
                    id="audit-all",
                    action=Action.ALLOW,
                    hosts=("*",),
                    allow_private=True,
                    note="built-in audit policy",
                ),
            ),
        )

    @classmethod
    def starter(cls) -> Policy:
        """Return a deny-by-default starter that only allows loopback."""

        return cls(
            default=Action.DENY,
            rules=(
                Rule(
                    id="local-hostname",
                    action=Action.ALLOW,
                    hosts=("localhost",),
                    allow_private=True,
                    note="allow localhost by name",
                ),
                Rule(
                    id="local-addresses",
                    action=Action.ALLOW,
                    networks=(
                        ipaddress.ip_network("127.0.0.0/8"),
                        ipaddress.ip_network("::1/128"),
                    ),
                    allow_private=True,
                    note="allow loopback IP literals",
                ),
            ),
        )

    def evaluate(
        self,
        host: str,
        ip: str | None,
        port: int,
        protocol: str,
        mode: Mode,
    ) -> PolicyDecision:
        """Evaluate one resolved destination without opening a socket."""

        normalized_host = normalize_host(host)
        normalized_protocol = protocol.lower()
        if normalized_protocol not in SUPPORTED_PROTOCOLS:
            raise ValueError(f"unsupported protocol {protocol!r}")
        if not 1 <= port <= 65535:
            raise ValueError("destination port must be from 1 through 65535")

        matches = [
            rule
            for rule in self.rules
            if rule.matches(normalized_host, ip, port, normalized_protocol)
        ]
        deny = next((rule for rule in matches if rule.action is Action.DENY), None)
        allow = next((rule for rule in matches if rule.action is Action.ALLOW), None)

        selected = deny or allow
        action = selected.action if selected else self.default
        reason = (
            f"matched {selected.id}"
            if selected
            else f"no rule matched; policy default is {self.default.value}"
        )

        scope = ip_scope(ip or normalized_host)
        private_allow = next(
            (
                rule
                for rule in matches
                if rule.action is Action.ALLOW and rule.allow_private
            ),
            None,
        )
        if action is Action.ALLOW and scope in RESTRICTED_SCOPES and private_allow is None:
            action = Action.DENY
            selected = None
            reason = f"{scope} destination needs an allow rule with allow_private=true"

        if action is Action.ALLOW:
            outcome = EventDecision.ALLOWED
        elif mode is Mode.AUDIT:
            outcome = EventDecision.WOULD_BLOCK
        else:
            outcome = EventDecision.BLOCKED
        return PolicyDecision(
            action=action,
            outcome=outcome,
            rule_id=selected.id if selected else None,
            reason=reason,
        )

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe representation in rule order."""

        return {
            "version": self.version,
            "default": self.default.value,
            "rules": [rule.as_dict() for rule in self.rules],
        }

    def write(self, path: Path) -> None:
        """Write this policy atomically with private file permissions."""

        path.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            raise ValueError(f"refusing to replace symlinked policy {path}")
        handle, raw_temp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temp_path = Path(raw_temp)
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(json.dumps(self.as_dict(), indent=2) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            temp_path.chmod(0o600)
            temp_path.replace(path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def with_rule(self, rule: Rule) -> Policy:
        """Return a policy with one new rule appended."""

        if any(existing.id == rule.id for existing in self.rules):
            raise ValueError(f"policy already has rule {rule.id!r}")
        return Policy(default=self.default, rules=(*self.rules, rule))


def host_matches(pattern: str, host: str) -> bool:
    """Match exact hosts and the documented `*.` / `**.` wildcard forms."""

    normalized = normalize_host(host)
    raw = pattern.strip().lower().rstrip(".")
    if raw == "*":
        return True
    if raw.startswith("**."):
        suffix = _wildcard_suffix(raw[3:], pattern)
        return normalized == suffix or normalized.endswith(f".{suffix}")
    if raw.startswith("*."):
        suffix = _wildcard_suffix(raw[2:], pattern)
        return normalized != suffix and normalized.endswith(f".{suffix}")
    if "*" in raw:
        raise ValueError(f"invalid host wildcard {pattern!r}")
    return normalized == normalize_host(raw)


def _wildcard_suffix(value: str, pattern: str) -> str:
    if not value or "*" in value:
        raise ValueError(f"invalid host wildcard {pattern!r}")
    return normalize_host(value)


def make_rule(
    rule_id: str,
    action: Action,
    *,
    hosts: tuple[str, ...] = (),
    ips: tuple[str, ...] = (),
    ports: tuple[int, ...] = (),
    protocols: tuple[str, ...] = (),
    allow_private: bool = False,
    note: str | None = None,
) -> Rule:
    """Validate CLI values and build a policy rule."""

    row: dict[str, Any] = {
        "id": rule_id,
        "action": action.value,
        "hosts": list(hosts),
        "ips": list(ips),
        "ports": list(ports),
        "protocols": list(protocols),
        "allow_private": allow_private,
        "note": note,
    }
    return _parse_rule(row, 1)


def _parse_rule(payload: object, index: int) -> Rule:
    if not isinstance(payload, dict):
        raise ValueError(f"policy rule {index} must be an object")
    allowed_keys = {
        "id",
        "action",
        "hosts",
        "ips",
        "ports",
        "protocols",
        "allow_private",
        "note",
    }
    unknown = set(payload) - allowed_keys
    if unknown:
        raise ValueError(f"rule {index} has unknown keys: {', '.join(sorted(unknown))}")
    rule_id = payload.get("id")
    if not isinstance(rule_id, str) or not rule_id.strip():
        raise ValueError(f"policy rule {index} needs a non-empty id")
    try:
        action = Action(payload.get("action"))
    except ValueError as exc:
        raise ValueError(f"policy rule {rule_id!r} action must be 'allow' or 'deny'") from exc

    hosts = _string_tuple(payload.get("hosts", []), f"rule {rule_id!r} hosts")
    for host in hosts:
        host_matches(host, "example.com")
    raw_ips = _string_tuple(payload.get("ips", []), f"rule {rule_id!r} ips")
    try:
        networks = tuple(ipaddress.ip_network(value, strict=False) for value in raw_ips)
    except ValueError as exc:
        raise ValueError(f"rule {rule_id!r} has an invalid IP or CIDR: {exc}") from exc

    raw_ports = payload.get("ports", [])
    if not isinstance(raw_ports, list) or any(type(port) is not int for port in raw_ports):
        raise ValueError(f"rule {rule_id!r} ports must be integer values")
    ports = tuple(raw_ports)
    if any(not 1 <= port <= 65535 for port in ports):
        raise ValueError(f"rule {rule_id!r} ports must be from 1 through 65535")

    protocols = tuple(
        value.lower()
        for value in _string_tuple(payload.get("protocols", []), f"rule {rule_id!r} protocols")
    )
    unsupported = set(protocols) - SUPPORTED_PROTOCOLS
    if unsupported:
        raise ValueError(f"rule {rule_id!r} has unsupported protocols: {', '.join(sorted(unsupported))}")
    allow_private = payload.get("allow_private", False)
    if type(allow_private) is not bool:
        raise ValueError(f"rule {rule_id!r} allow_private must be boolean")
    note = payload.get("note")
    if note is not None and not isinstance(note, str):
        raise ValueError(f"rule {rule_id!r} note must be text")
    if not any((hosts, networks, ports, protocols)):
        raise ValueError(f"policy rule {rule_id!r} needs at least one matcher")
    return Rule(
        id=rule_id.strip(),
        action=action,
        hosts=hosts,
        networks=networks,
        ports=ports,
        protocols=protocols,
        allow_private=allow_private,
        note=note,
    )


def _string_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"{label} must be text values")
    return tuple(item.strip() for item in value if item.strip())
