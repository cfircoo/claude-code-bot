"""Command guard hook — blocks Bash commands matching dangerous patterns."""

from __future__ import annotations

import re
from typing import Any

import structlog

logger = structlog.get_logger()


def make_command_guard(blocked: list[str], *, use_regex: bool = False) -> Any:
    """Create a PreToolUse callback that blocks dangerous Bash commands.

    Args:
        blocked: List of patterns to block (plain substrings or regex).
        use_regex: If True, treat patterns as regex. Default is substring match.
    """

    async def command_guard(input_data: dict, _tool_use_id: str | None, _ctx: Any) -> dict:
        command = input_data.get("tool_input", {}).get("command", "")
        if not command:
            return {}
        for pattern in blocked:
            matched = False
            if use_regex:
                try:
                    matched = bool(re.search(pattern, command, re.IGNORECASE))
                except re.error:
                    continue
            else:
                matched = pattern in command
            if matched:
                logger.info("hook_command_guard_blocked", command=command, pattern=pattern)
                return {
                    "hookSpecificOutput": {
                        "hookEventName": input_data["hook_event_name"],
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Command guard: blocked '{pattern}'",
                    }
                }
        return {}

    label = ", ".join(blocked[:3])
    if len(blocked) > 3:
        label += f", ... +{len(blocked) - 3}"
    command_guard.__name__ = f"command_guard({label})"
    return command_guard


def make_command_ask(patterns: list[dict[str, str]]) -> Any:
    """Create a PreToolUse callback that asks for confirmation on matching commands.

    Args:
        patterns: List of dicts with 'pattern' (regex) and 'reason' keys.
    """

    async def command_ask(input_data: dict, _tool_use_id: str | None, _ctx: Any) -> dict:
        command = input_data.get("tool_input", {}).get("command", "")
        if not command:
            return {}
        for item in patterns:
            pattern = item.get("pattern", "")
            reason = item.get("reason", "Requires confirmation")
            try:
                if re.search(pattern, command, re.IGNORECASE):
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": input_data["hook_event_name"],
                            "permissionDecision": "ask",
                            "permissionDecisionReason": reason,
                        }
                    }
            except re.error:
                continue
        return {}

    command_ask.__name__ = "command_ask"
    return command_ask
