from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from fieldkit_netwatch.proxy import ProxyAddresses

_VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")
_CLAUDE_STRICT_MIN = (2, 1, 219)


class AgentKind(StrEnum):
    """Agent integrations Netwatch can prepare."""

    AUTO = "auto"
    CODEX = "codex"
    CLAUDE = "claude"
    GENERIC = "generic"


@dataclass(frozen=True)
class AgentProcess:
    """One running Codex or Claude process discovered through `ps`."""

    pid: int
    ppid: int
    agent: AgentKind
    executable: str
    command: str


@dataclass(frozen=True)
class PreparedAgent:
    """Invocation-local command, environment, and coverage notes."""

    argv: tuple[str, ...]
    env: dict[str, str]
    agent: AgentKind
    coverage: tuple[str, ...]
    warnings: tuple[str, ...]


def detect_agent(argv: list[str] | tuple[str, ...]) -> AgentKind:
    """Infer a supported agent from the command executable."""

    if not argv:
        raise ValueError("missing command after --")
    executable = Path(argv[0]).name.lower()
    if executable in {"codex", "codex-cli"}:
        return AgentKind.CODEX
    if executable in {"claude", "claude-code"}:
        return AgentKind.CLAUDE
    return AgentKind.GENERIC


def discover_agents() -> list[AgentProcess]:
    """List running Codex and Claude processes without inspecting their files."""

    try:
        completed = subprocess.run(
            ["ps", "-axo", "pid=,ppid=,command="],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise RuntimeError(f"can't inspect running processes: {exc}") from exc
    processes: list[AgentProcess] = []
    for line in completed.stdout.splitlines():
        parts = line.strip().split(None, 2)
        if len(parts) != 3:
            continue
        try:
            pid, ppid = int(parts[0]), int(parts[1])
        except ValueError:
            continue
        command = parts[2]
        executable = command.split(None, 1)[0]
        kind = _process_agent(command)
        if kind is AgentKind.GENERIC:
            continue
        safe_command = executable if command.strip() == executable else f"{executable} [arguments redacted]"
        processes.append(AgentProcess(pid, ppid, kind, executable, safe_command))
    by_pid = {process.pid: process for process in processes}
    roots = [
        process
        for process in processes
        if not (
            (parent := by_pid.get(process.ppid))
            and parent.agent is process.agent
        )
    ]
    return sorted(roots, key=lambda process: process.pid)


def prepare_agent(
    argv: list[str] | tuple[str, ...],
    *,
    requested: AgentKind,
    addresses: ProxyAddresses,
    session_id: str,
    db_path: Path,
    temp_dir: Path,
    base_env: dict[str, str] | None = None,
) -> PreparedAgent:
    """Build an invocation-local agent command and proxy environment."""

    if not argv:
        raise ValueError("missing command after --")
    inferred = detect_agent(argv)
    agent = inferred if requested is AgentKind.AUTO else requested
    if requested is not AgentKind.AUTO and requested is not AgentKind.GENERIC and inferred not in {
        requested,
        AgentKind.GENERIC,
    }:
        raise ValueError(f"command looks like {inferred.value}, not {requested.value}")

    env = proxy_environment(
        addresses,
        session_id=session_id,
        db_path=db_path,
        base_env=base_env,
    )
    command = list(argv)
    coverage = ["environment HTTP(S)/SOCKS proxy", "HTTP host + plaintext path", "HTTPS host:port"]
    warnings: list[str] = []

    if agent is AgentKind.CODEX:
        command, codex_coverage, codex_warning = _prepare_codex(command)
        coverage.extend(codex_coverage)
        if codex_warning:
            warnings.append(codex_warning)
    elif agent is AgentKind.CLAUDE:
        command, claude_coverage, claude_warning = _prepare_claude(
            command,
            addresses=addresses,
            temp_dir=temp_dir,
        )
        coverage.extend(claude_coverage)
        if claude_warning:
            warnings.append(claude_warning)
    else:
        warnings.append("generic commands can bypass Netwatch if they ignore proxy variables")

    return PreparedAgent(
        argv=tuple(command),
        env=env,
        agent=agent,
        coverage=tuple(coverage),
        warnings=tuple(warnings),
    )


def proxy_environment(
    addresses: ProxyAddresses,
    *,
    session_id: str,
    db_path: Path,
    base_env: dict[str, str] | None = None,
) -> dict[str, str]:
    """Return a child environment that routes cooperative clients through Netwatch."""

    env = dict(os.environ if base_env is None else base_env)
    values = {
        "HTTP_PROXY": addresses.http_url,
        "HTTPS_PROXY": addresses.http_url,
        "ALL_PROXY": addresses.socks_url,
        "NO_PROXY": "",
        "http_proxy": addresses.http_url,
        "https_proxy": addresses.http_url,
        "all_proxy": addresses.socks_url,
        "no_proxy": "",
        "FIELDKIT_NETWATCH_SESSION": session_id,
        "FIELDKIT_NETWATCH_DB": str(db_path),
    }
    env.update(values)
    return env


def codex_network_proxy_supported(executable: str) -> bool:
    """Check the installed Codex feature list without starting an agent session."""

    try:
        completed = subprocess.run(
            [executable, "features", "list"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return False
    for line in completed.stdout.splitlines():
        fields = line.split()
        if fields and fields[0] == "network_proxy" and len(fields) >= 3:
            return fields[1] in {"experimental", "stable", "under"}
    return False


def capability_report() -> dict[str, object]:
    """Report local capture and agent integration availability without network access."""

    codex = shutil.which("codex")
    claude = shutil.which("claude")
    lsof = shutil.which("lsof")
    return {
        "platform": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "capture": {
            "http_proxy": True,
            "socks5_tcp": True,
            "tls_decryption": False,
            "udp_quic": False,
            "whole_machine_enforcement": False,
            "attach_snapshot": bool(lsof),
        },
        "agents": {
            "codex": {
                "path": codex,
                "network_proxy": bool(codex and codex_network_proxy_supported(codex)),
            },
            "claude": {
                "path": claude,
                "version": _command_version(claude) if claude else None,
                "strict_sandbox_proxy": bool(
                    claude and _version_tuple(_command_version(claude)) >= _CLAUDE_STRICT_MIN
                ),
            },
        },
        "coverage_note": (
            "run mode covers traffic routed through the local proxies; attach mode samples "
            "TCP sockets and cannot block. DNS, UDP/QUIC, and proxy-bypassing sockets are uncovered."
        ),
    }


def _prepare_codex(command: list[str]) -> tuple[list[str], list[str], str | None]:
    executable = command[0]
    if any("network_proxy" in arg for arg in command[1:]):
        return command, ["Codex user-supplied network proxy config"], (
            "Codex already has a network_proxy override; Netwatch left it unchanged"
        )
    if not codex_network_proxy_supported(executable):
        return command, [], (
            "this Codex build does not expose network_proxy; only proxy-aware traffic is covered"
        )
    config = (
        'features.network_proxy={enabled=true,allow_upstream_proxy=true,'
        'allow_local_binding=true,domains={"*"="allow"}}'
    )
    return [command[0], "-c", config, *command[1:]], ["Codex sandbox network proxy chained upstream"], None


def _prepare_claude(
    command: list[str],
    *,
    addresses: ProxyAddresses,
    temp_dir: Path,
) -> tuple[list[str], list[str], str | None]:
    version = _command_version(command[0])
    if _version_tuple(version) < _CLAUDE_STRICT_MIN:
        return command, [], (
            "Claude Code 2.1.219 or newer is required for strict custom-proxy sandboxing; "
            "only proxy-aware traffic is covered"
        )

    original, cleaned_command, warning = _extract_claude_settings(command)
    hook_command = f"{shlex.quote(sys.executable)} -m fieldkit_netwatch.hook"
    sandbox = original.setdefault("sandbox", {})
    if not isinstance(sandbox, dict):
        raise ValueError("Claude --settings sandbox must be an object")
    sandbox.update(
        {
            "enabled": True,
            "failIfUnavailable": True,
            "allowUnsandboxedCommands": False,
        }
    )
    network = sandbox.setdefault("network", {})
    if not isinstance(network, dict):
        raise ValueError("Claude --settings sandbox.network must be an object")
    network.update(
        {
            "allowedDomains": ["*"],
            "strictAllowlist": True,
            "allowLocalBinding": True,
            "httpProxyPort": addresses.http_port,
            "socksProxyPort": addresses.socks_port,
        }
    )
    hooks = original.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise ValueError("Claude --settings hooks must be an object")
    pre_tool = hooks.setdefault("PreToolUse", [])
    if not isinstance(pre_tool, list):
        raise ValueError("Claude --settings hooks.PreToolUse must be a list")
    pre_tool.append({"hooks": [{"type": "command", "command": hook_command}]})

    settings_path = temp_dir / "claude-netwatch-settings.json"
    settings_path.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
    settings_path.chmod(0o600)
    prepared = [cleaned_command[0], "--settings", str(settings_path), *cleaned_command[1:]]
    coverage = ["Claude fail-closed Bash sandbox proxy", "Claude PreToolUse metadata hooks"]
    return prepared, coverage, warning


def _extract_claude_settings(command: list[str]) -> tuple[dict[str, Any], list[str], str | None]:
    cleaned: list[str] = [command[0]]
    value: str | None = None
    index = 1
    while index < len(command):
        arg = command[index]
        if arg == "--settings":
            if index + 1 >= len(command):
                raise ValueError("Claude --settings is missing its value")
            if value is not None:
                raise ValueError("Claude command has more than one --settings value")
            value = command[index + 1]
            index += 2
            continue
        if arg.startswith("--settings="):
            if value is not None:
                raise ValueError("Claude command has more than one --settings value")
            value = arg.split("=", 1)[1]
            index += 1
            continue
        cleaned.append(arg)
        index += 1
    if value is None:
        return {}, cleaned, None
    try:
        if value.lstrip().startswith("{"):
            payload = json.loads(value)
        else:
            payload = json.loads(Path(value).expanduser().read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"can't merge Claude --settings: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError("Claude --settings must contain a JSON object")
    return payload, cleaned, "Claude --settings was copied and merged for this run; the original was not edited"


def _command_version(executable: str) -> str:
    try:
        completed = subprocess.run(
            [executable, "--version"],
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError:
        return "unknown"
    return (completed.stdout or completed.stderr).strip() or "unknown"


def _version_tuple(value: str) -> tuple[int, int, int]:
    match = _VERSION.search(value)
    return tuple(int(part) for part in match.groups()) if match else (0, 0, 0)


def _process_agent(command: str) -> AgentKind:
    lowered_command = command.lower()
    if "fieldkit netwatch" in lowered_command:
        return AgentKind.GENERIC
    if any(
        marker in lowered_command
        for marker in (
            "/applications/claude.app/",
            "/library/application support/claude/",
            "/applications/chatgpt.app/contents/frameworks/",
        )
    ):
        return AgentKind.GENERIC
    try:
        argv = shlex.split(command)
    except ValueError:
        argv = command.split()
    if not argv:
        return AgentKind.GENERIC
    executable = argv[0].lower()
    if (
        ".app/contents/frameworks/" in executable
        or ".app/contents/helpers/" in executable
        or "/.codex/computer-use/" in executable
        or (
            ".app/contents/" in executable
            and not executable.endswith("/contents/resources/codex")
        )
    ):
        return AgentKind.GENERIC
    direct = detect_agent((argv[0],))
    if direct is not AgentKind.GENERIC:
        return direct
    for arg in argv[1:]:
        lowered = arg.lower()
        basename = Path(arg).name.lower()
        if basename in {"claude", "claude-code"} or "@anthropic-ai/claude-code" in lowered:
            return AgentKind.CLAUDE
        if basename in {"codex", "codex-cli"} or "@openai/codex" in lowered:
            return AgentKind.CODEX
    return AgentKind.GENERIC
