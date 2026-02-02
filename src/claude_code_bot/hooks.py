"""Hook manager for claude-agent-sdk hooks."""

from __future__ import annotations

import fnmatch
from typing import Any, Awaitable, Callable, Literal

import structlog
from claude_agent_sdk import HookMatcher

logger = structlog.get_logger()

HookEvent = Literal[
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "Stop",
    "SubagentStop",
    "PreCompact",
]

ALL_HOOK_EVENTS: list[HookEvent] = [
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "Stop",
    "SubagentStop",
    "PreCompact",
]

# Callback: async (input_data, tool_use_id, context) -> dict
HookCallback = Callable[..., Awaitable[dict[str, Any]]]


class HookManager:
    """Registry for SDK hooks with fluent registration API.

    Usage::

        manager = HookManager()
        manager.add_file_guard([".env", "*.pem"])
        manager.add_command_guard(["rm -rf /"])
        manager.add_auto_approve(["Read", "Glob", "Grep"])
        manager.add_audit_logger()

        options = ClaudeAgentOptions(hooks=manager.build())
    """

    def __init__(self) -> None:
        self._hooks: dict[str, list[tuple[str | None, HookCallback, int]]] = {}

    def add(
        self,
        event: HookEvent,
        callback: HookCallback,
        matcher: str | None = None,
        timeout: int = 60,
    ) -> HookManager:
        """Register a hook callback. Returns self for chaining."""
        self._hooks.setdefault(event, []).append((matcher, callback, timeout))
        return self

    def remove(self, event: HookEvent, callback: HookCallback) -> bool:
        """Remove a previously registered callback. Returns True if found."""
        entries = self._hooks.get(event, [])
        for i, (_, cb, _) in enumerate(entries):
            if cb is callback:
                entries.pop(i)
                if not entries:
                    del self._hooks[event]
                return True
        return False

    def build(self) -> dict[str, list[HookMatcher]]:
        """Build the hooks dict for ClaudeAgentOptions."""
        result: dict[str, list[HookMatcher]] = {}
        for event, entries in self._hooks.items():
            matchers: list[HookMatcher] = []
            for pattern, callback, timeout in entries:
                kwargs: dict[str, Any] = {"hooks": [callback]}
                if pattern is not None:
                    kwargs["matcher"] = pattern
                if timeout != 60:
                    kwargs["timeout"] = timeout
                matchers.append(HookMatcher(**kwargs))
            result[event] = matchers
        return result

    def list_hooks(self) -> list[dict[str, Any]]:
        """Return a summary of all registered hooks for display."""
        items: list[dict[str, Any]] = []
        for event, entries in self._hooks.items():
            for pattern, callback, timeout in entries:
                items.append(
                    {
                        "event": event,
                        "matcher": pattern or "*",
                        "name": getattr(callback, "__name__", str(callback)),
                        "timeout": timeout,
                    }
                )
        return items

    # --- Built-in hook factories ---

    def add_file_guard(self, patterns: list[str]) -> HookManager:
        """Block Write/Edit to files matching glob patterns (e.g. ['.env', '*.key'])."""

        async def _file_guard(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            file_path = input_data.get("tool_input", {}).get("file_path", "")
            file_name = file_path.rsplit("/", 1)[-1] if file_path else ""
            for pat in patterns:
                if fnmatch.fnmatch(file_name, pat) or fnmatch.fnmatch(file_path, pat):
                    logger.info("hook_file_guard_blocked", file_path=file_path, pattern=pat)
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": input_data["hook_event_name"],
                            "permissionDecision": "deny",
                            "permissionDecisionReason": f"File guard: {pat} blocks {file_path}",
                        }
                    }
            return {}

        _file_guard.__name__ = f"file_guard({', '.join(patterns)})"
        return self.add("PreToolUse", _file_guard, matcher="Write|Edit")

    def add_command_guard(self, blocked: list[str]) -> HookManager:
        """Block Bash commands containing dangerous strings."""

        async def _command_guard(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            command = input_data.get("tool_input", {}).get("command", "")
            for dangerous in blocked:
                if dangerous in command:
                    logger.info("hook_command_guard_blocked", command=command, pattern=dangerous)
                    return {
                        "hookSpecificOutput": {
                            "hookEventName": input_data["hook_event_name"],
                            "permissionDecision": "deny",
                            "permissionDecisionReason": f"Command guard: blocked '{dangerous}'",
                        }
                    }
            return {}

        _command_guard.__name__ = f"command_guard({', '.join(blocked)})"
        return self.add("PreToolUse", _command_guard, matcher="Bash")

    def add_audit_logger(self, log_fn: Callable[..., Any] | None = None) -> HookManager:
        """Log all tool calls via structlog or a custom function."""

        async def _audit_pre(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            info = {
                "tool": input_data.get("tool_name", ""),
                "tool_use_id": tool_use_id,
                "input_keys": list(input_data.get("tool_input", {}).keys()),
            }
            if log_fn:
                log_fn("pre_tool_use", **info)
            else:
                logger.info("hook_audit_pre_tool", **info)
            return {}

        async def _audit_post(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            info = {
                "tool": input_data.get("tool_name", ""),
                "tool_use_id": tool_use_id,
            }
            if log_fn:
                log_fn("post_tool_use", **info)
            else:
                logger.info("hook_audit_post_tool", **info)
            return {}

        _audit_pre.__name__ = "audit_logger(pre)"
        _audit_post.__name__ = "audit_logger(post)"
        self.add("PreToolUse", _audit_pre)
        return self.add("PostToolUse", _audit_post)

    def add_auto_approve(self, tools: list[str]) -> HookManager:
        """Auto-approve specific tools (PreToolUse -> allow)."""
        pattern = "|".join(tools)

        async def _auto_approve(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {
                "hookSpecificOutput": {
                    "hookEventName": input_data["hook_event_name"],
                    "permissionDecision": "allow",
                    "permissionDecisionReason": "Auto-approved by hook",
                }
            }

        _auto_approve.__name__ = f"auto_approve({', '.join(tools)})"
        return self.add("PreToolUse", _auto_approve, matcher=pattern)

    def add_stop_handler(self, callback: HookCallback) -> HookManager:
        """Register a callback for when the agent stops."""
        return self.add("Stop", callback)

    def add_prompt_handler(self, callback: HookCallback) -> HookManager:
        """Register a callback for user prompt submission."""
        return self.add("UserPromptSubmit", callback)
