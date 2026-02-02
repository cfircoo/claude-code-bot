"""Core HookManager class — registry and builder for SDK hooks."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Literal

from claude_agent_sdk import HookMatcher

HookEvent = Literal[
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

    # --- Convenience wiring from individual hook modules ---

    def add_file_guard(self, patterns: list[str]) -> HookManager:
        """Block Write/Edit to files matching glob patterns."""
        from claude_code_bot.hooks.file_guard import make_file_guard

        callback = make_file_guard(patterns)
        return self.add("PreToolUse", callback, matcher="Write|Edit")

    def add_command_guard(self, blocked: list[str]) -> HookManager:
        """Block Bash commands containing dangerous strings."""
        from claude_code_bot.hooks.command_guard import make_command_guard

        callback = make_command_guard(blocked)
        return self.add("PreToolUse", callback, matcher="Bash")

    def add_audit_logger(self, log_fn: Callable[..., Any] | None = None) -> HookManager:
        """Log all tool calls (PreToolUse + PostToolUse)."""
        from claude_code_bot.hooks.audit_logger import make_audit_hooks

        pre, post = make_audit_hooks(log_fn)
        self.add("PreToolUse", pre)
        return self.add("PostToolUse", post)

    def add_auto_approve(self, tools: list[str]) -> HookManager:
        """Auto-approve specific tools (PreToolUse -> allow)."""
        from claude_code_bot.hooks.auto_approve import make_auto_approve

        callback = make_auto_approve(tools)
        pattern = "|".join(tools)
        return self.add("PreToolUse", callback, matcher=pattern)

    def add_damage_control(self, patterns_path: str | None = None) -> HookManager:
        """Load damage-control patterns from YAML and register all guards."""
        from claude_code_bot.hooks.damage_control import register_damage_control

        register_damage_control(self, patterns_path)
        return self

    def add_stop_handler(self, callback: HookCallback) -> HookManager:
        """Register a callback for when the agent stops."""
        return self.add("Stop", callback)

    def add_prompt_handler(self, callback: HookCallback) -> HookManager:
        """Register a callback for user prompt submission."""
        return self.add("UserPromptSubmit", callback)
