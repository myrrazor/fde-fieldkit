from __future__ import annotations

import io
import json
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from fieldkit_netwatch import agents, hook
from fieldkit_netwatch.agents import AgentKind, detect_agent, discover_agents, prepare_agent
from fieldkit_netwatch.attach import descendant_pids, parse_lsof
from fieldkit_netwatch.models import Mode
from fieldkit_netwatch.proxy import ProxyAddresses
from fieldkit_netwatch.store import Store


ADDRESSES = ProxyAddresses("127.0.0.1", 41001, "127.0.0.1", 41002)


def test_agent_detection_uses_executable_not_unrelated_arguments() -> None:
    assert detect_agent(["/opt/homebrew/bin/codex", "exec"]) is AgentKind.CODEX
    assert detect_agent(["claude", "--print"]) is AgentKind.CLAUDE
    assert detect_agent(["python", "codex-report.py"]) is AgentKind.GENERIC


def test_process_discovery_recognizes_vendor_launchers_without_substring_false_positives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output = "\n".join(
        [
            "101 1 /opt/homebrew/bin/codex app-server",
            "102 1 node /usr/local/lib/node_modules/@anthropic-ai/claude-code/cli.js",
            "103 1 python codex-report.py",
            "104 1 fieldkit netwatch run -- claude",
            "105 101 /vendor/bin/codex exec child",
            "106 1 /Applications/Claude.app/Contents/Frameworks/Claude Helper --type=renderer",
            "107 1 /Applications/ChatGPT.app/Contents/Resources/codex app-server",
            "108 1 /opt/fixtures/Library/Application Support/Claude/claude helper",
        ]
    )
    monkeypatch.setattr(
        agents.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(args[0], 0, stdout=output, stderr=""),
    )
    found = discover_agents()
    assert [(row.pid, row.agent) for row in found] == [
        (101, AgentKind.CODEX),
        (102, AgentKind.CLAUDE),
        (107, AgentKind.CODEX),
    ]
    assert all(row.command.endswith("[arguments redacted]") for row in found)


def test_proxy_environment_overrides_bypass_variables(tmp_path: Path) -> None:
    prepared = agents.proxy_environment(
        ADDRESSES,
        session_id="session-1",
        db_path=tmp_path / "events.db",
        base_env={"NO_PROXY": "localhost", "KEEP": "yes"},
    )
    assert prepared["HTTP_PROXY"] == "http://127.0.0.1:41001"
    assert prepared["HTTPS_PROXY"] == prepared["http_proxy"]
    assert prepared["ALL_PROXY"] == "socks5h://127.0.0.1:41002"
    assert prepared["NO_PROXY"] == prepared["no_proxy"] == ""
    assert prepared["KEEP"] == "yes"


def test_codex_preparation_adds_invocation_local_network_proxy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agents, "codex_network_proxy_supported", lambda _executable: True)
    prepared = prepare_agent(
        ["codex", "exec", "status"],
        requested=AgentKind.AUTO,
        addresses=ADDRESSES,
        session_id="session-2",
        db_path=tmp_path / "events.db",
        temp_dir=tmp_path,
        base_env={},
    )
    assert prepared.agent is AgentKind.CODEX
    assert prepared.argv[:2] == ("codex", "-c")
    assert "features.network_proxy" in prepared.argv[2]
    assert prepared.argv[3:] == ("exec", "status")
    assert "Codex sandbox network proxy chained upstream" in prepared.coverage


def test_codex_capability_fallback_is_labelled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agents, "codex_network_proxy_supported", lambda _executable: False)
    prepared = prepare_agent(
        ["codex"],
        requested=AgentKind.CODEX,
        addresses=ADDRESSES,
        session_id="session-3",
        db_path=tmp_path / "events.db",
        temp_dir=tmp_path,
        base_env={},
    )
    assert prepared.argv == ("codex",)
    assert "only proxy-aware traffic is covered" in prepared.warnings[0]


def test_claude_settings_are_copied_merged_and_never_edited(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = tmp_path / "claude-settings.json"
    original_payload = {
        "permissions": {"allow": ["Read"]},
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]},
    }
    original.write_text(json.dumps(original_payload))
    (tmp_path / "temp").mkdir()
    monkeypatch.setattr(agents, "_command_version", lambda _executable: "2.1.223")

    prepared = prepare_agent(
        ["claude", "--settings", str(original), "--print", "hello"],
        requested=AgentKind.AUTO,
        addresses=ADDRESSES,
        session_id="session-4",
        db_path=tmp_path / "events.db",
        temp_dir=tmp_path / "temp",
        base_env={},
    )
    settings_path = Path(prepared.argv[2])
    merged = json.loads(settings_path.read_text())
    assert prepared.argv[:2] == ("claude", "--settings")
    assert prepared.argv[3:] == ("--print", "hello")
    assert original.read_text() == json.dumps(original_payload)
    assert merged["permissions"] == {"allow": ["Read"]}
    assert len(merged["hooks"]["PreToolUse"]) == 2
    assert merged["sandbox"] == {
        "enabled": True,
        "failIfUnavailable": True,
        "allowUnsandboxedCommands": False,
        "network": {
            "allowedDomains": ["*"],
            "strictAllowlist": True,
            "allowLocalBinding": True,
            "httpProxyPort": 41001,
            "socksProxyPort": 41002,
        },
    }
    assert "copied and merged" in prepared.warnings[0]


def test_claude_old_version_keeps_proxy_environment_but_labels_weaker_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(agents, "_command_version", lambda _executable: "2.1.100")
    prepared = prepare_agent(
        ["claude"],
        requested=AgentKind.CLAUDE,
        addresses=ADDRESSES,
        session_id="session-5",
        db_path=tmp_path / "events.db",
        temp_dir=tmp_path,
        base_env={},
    )
    assert prepared.argv == ("claude",)
    assert prepared.env["HTTP_PROXY"] == ADDRESSES.http_url
    assert "2.1.219" in prepared.warnings[0]


def test_hook_sanitizes_every_supported_content_shape() -> None:
    web = hook.sanitize_hook_payload(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "WebFetch",
            "tool_use_id": "tool-1",
            "tool_input": {
                "url": "https://alice:secret@example.com/users/550e8400-e29b-41d4-a716-446655440000?q=secret",
                "headers": {"Authorization": "Bearer secret"},
                "body": "private prompt",
            },
        }
    )
    assert web == (
        "PreToolUse",
        "WebFetch",
        "https://example.com/users/[redacted]",
        "tool-1",
    )
    assert hook.sanitize_hook_payload(
        {"tool_name": "WebSearch", "tool_input": {"query": "secret search"}}
    )[2] == "search query redacted"
    assert hook.sanitize_hook_payload(
        {"tool_name": "Bash", "tool_input": {"command": "curl -H secret"}}
    )[2] == "shell command redacted"
    assert hook.sanitize_hook_payload(
        {"tool_name": "mcp__browser__click", "tool_input": {"selector": "#private"}}
    )[2] == "tool input redacted"


def test_hook_main_persists_only_sanitized_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db = tmp_path / "hook.db"
    store = Store(db)
    session_id = store.create_session(
        mode=Mode.AUDIT,
        agent="claude",
        command=["claude"],
        coverage=("hook",),
    ).id
    raw = {
        "hook_event_name": "PreToolUse",
        "tool_name": "WebSearch",
        "tool_use_id": "tool-secret-id",
        "tool_input": {"query": "company acquisition secret", "body": "do not store"},
    }
    monkeypatch.setenv("FIELDKIT_NETWATCH_SESSION", session_id)
    monkeypatch.setenv("FIELDKIT_NETWATCH_DB", str(db))
    monkeypatch.setattr(hook.sys, "stdin", io.StringIO(json.dumps(raw)))
    assert hook.main() == 0
    event = store.list_tool_events(session_id)[0]
    assert event.target == "search query redacted"
    contents = db.read_bytes()
    assert b"company acquisition secret" not in contents
    assert b"do not store" not in contents


def test_process_tree_and_lsof_parsing_cover_descendants_and_ipv6() -> None:
    process_table = "1 0\n10 1\n11 10\n12 11\n20 1\n"
    assert descendant_pids(10, process_table) == {10, 11, 12}
    with pytest.raises(ValueError, match="no running process"):
        descendant_pids(99, process_table)

    output = "\n".join(
        [
            "p10",
            "cclaude",
            "n127.0.0.1:50000->1.1.1.1:443",
            "TST=ESTABLISHED",
            "p11",
            "ccodex",
            "n[::1]:50001->[2606:4700:4700::1111]:443",
            "n127.0.0.1:50002",
        ]
    )
    rows = parse_lsof(output)
    assert [(row.pid, row.process_name, row.remote_host, row.remote_port) for row in rows] == [
        (10, "claude", "1.1.1.1", 443),
        (11, "codex", "2606:4700:4700::1111", 443),
    ]
    assert rows[0].fingerprint == "10|127.0.0.1:50000|1.1.1.1:443"
