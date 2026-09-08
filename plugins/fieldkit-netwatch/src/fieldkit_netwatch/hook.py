from __future__ import annotations

import json
import os
import sys
from typing import Any

from fieldkit_netwatch.destinations import sanitize_url
from fieldkit_netwatch.store import Store


def sanitize_hook_payload(payload: object) -> tuple[str, str, str | None, str | None]:
    """Reduce a Claude hook payload to non-content metadata."""

    if not isinstance(payload, dict):
        raise ValueError("hook input must be a JSON object")
    event = _text(payload.get("hook_event_name")) or "PreToolUse"
    tool = _text(payload.get("tool_name")) or "unknown"
    correlation_id = _text(payload.get("tool_use_id"))
    tool_input = payload.get("tool_input")
    values = tool_input if isinstance(tool_input, dict) else {}
    target: str | None
    if tool == "WebFetch":
        target = sanitize_url(_text(values.get("url")))
    elif tool == "WebSearch":
        target = "search query redacted"
    elif tool == "Bash":
        target = "shell command redacted"
    elif "browser" in tool.lower() or tool.startswith("mcp__"):
        target = sanitize_url(_text(values.get("url"))) or "tool input redacted"
    else:
        target = "tool input redacted" if values else None
    return event, tool, target, correlation_id


def main() -> int:
    """Read one hook payload from stdin and record sanitized metadata."""

    session_id = os.environ.get("FIELDKIT_NETWATCH_SESSION")
    db_path = os.environ.get("FIELDKIT_NETWATCH_DB")
    if not session_id or not db_path:
        print("netwatch hook skipped: session environment is missing", file=sys.stderr)
        return 0
    try:
        payload: Any = json.load(sys.stdin)
        event, tool, target, correlation_id = sanitize_hook_payload(payload)
        Store().add_tool_event(
            session_id=session_id,
            event=event,
            tool=tool,
            target=target,
            correlation_id=correlation_id,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"netwatch hook skipped: {type(exc).__name__}", file=sys.stderr)
    return 0


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


if __name__ == "__main__":
    raise SystemExit(main())
