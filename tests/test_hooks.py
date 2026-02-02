"""Tests for HookManager hook registration and built-in hooks."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from claude_code_bot.hooks import HookManager


# Mock HookMatcher since claude_agent_sdk may not be installed in test env
class MockHookMatcher:
    """Mock HookMatcher for testing."""

    def __init__(self, hooks: list, matcher: str | None = None, timeout: int = 60) -> None:
        self.hooks = hooks
        self.matcher = matcher
        self.timeout = timeout


@pytest.fixture
def manager() -> HookManager:
    """Create a fresh HookManager instance."""
    return HookManager()


@pytest.fixture
def mock_hook_matcher():
    """Mock the HookMatcher import."""
    with patch("claude_code_bot.hooks.HookMatcher", MockHookMatcher):
        yield MockHookMatcher


class TestAddRemove:
    """Test add() and remove() methods."""

    async def test_add_hook(self, manager: HookManager) -> None:
        """Test adding a hook callback."""

        async def my_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        result = manager.add("PreToolUse", my_hook)
        assert result is manager  # Fluent API
        assert "PreToolUse" in manager._hooks
        assert len(manager._hooks["PreToolUse"]) == 1
        assert manager._hooks["PreToolUse"][0][1] is my_hook

    async def test_add_hook_with_matcher(self, manager: HookManager) -> None:
        """Test adding a hook with a matcher pattern."""

        async def my_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PreToolUse", my_hook, matcher="Bash|Write")
        entry = manager._hooks["PreToolUse"][0]
        assert entry[0] == "Bash|Write"
        assert entry[1] is my_hook
        assert entry[2] == 60  # default timeout

    async def test_add_hook_with_custom_timeout(self, manager: HookManager) -> None:
        """Test adding a hook with custom timeout."""

        async def my_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PostToolUse", my_hook, timeout=120)
        entry = manager._hooks["PostToolUse"][0]
        assert entry[2] == 120

    async def test_add_multiple_hooks_same_event(self, manager: HookManager) -> None:
        """Test adding multiple hooks to the same event."""

        async def hook1(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        async def hook2(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PreToolUse", hook1)
        manager.add("PreToolUse", hook2)
        assert len(manager._hooks["PreToolUse"]) == 2

    async def test_remove_hook_success(self, manager: HookManager) -> None:
        """Test removing a registered hook."""

        async def my_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PreToolUse", my_hook)
        result = manager.remove("PreToolUse", my_hook)
        assert result is True
        assert "PreToolUse" not in manager._hooks

    async def test_remove_hook_not_found(self, manager: HookManager) -> None:
        """Test removing a hook that doesn't exist."""

        async def my_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        result = manager.remove("PreToolUse", my_hook)
        assert result is False

    async def test_remove_one_hook_keeps_others(self, manager: HookManager) -> None:
        """Test that removing one hook keeps others in the list."""

        async def hook1(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        async def hook2(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PreToolUse", hook1)
        manager.add("PreToolUse", hook2)
        manager.remove("PreToolUse", hook1)
        assert len(manager._hooks["PreToolUse"]) == 1
        assert manager._hooks["PreToolUse"][0][1] is hook2


class TestBuild:
    """Test build() generates correct HookMatcher structure."""

    async def test_build_empty(self, manager: HookManager, mock_hook_matcher) -> None:
        """Test building with no hooks registered."""
        result = manager.build()
        assert result == {}

    async def test_build_single_hook(self, manager: HookManager, mock_hook_matcher) -> None:
        """Test building with a single hook."""

        async def my_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PreToolUse", my_hook)
        result = manager.build()
        assert "PreToolUse" in result
        assert len(result["PreToolUse"]) == 1
        matcher = result["PreToolUse"][0]
        assert isinstance(matcher, MockHookMatcher)
        assert matcher.hooks == [my_hook]
        assert matcher.matcher is None
        assert matcher.timeout == 60

    async def test_build_with_matcher(self, manager: HookManager, mock_hook_matcher) -> None:
        """Test building with a matcher pattern."""

        async def my_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PreToolUse", my_hook, matcher="Bash")
        result = manager.build()
        matcher = result["PreToolUse"][0]
        assert matcher.matcher == "Bash"

    async def test_build_with_custom_timeout(
        self, manager: HookManager, mock_hook_matcher
    ) -> None:
        """Test building with custom timeout."""

        async def my_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PostToolUse", my_hook, timeout=120)
        result = manager.build()
        matcher = result["PostToolUse"][0]
        assert matcher.timeout == 120

    async def test_build_multiple_events(
        self, manager: HookManager, mock_hook_matcher
    ) -> None:
        """Test building with multiple events."""

        async def hook1(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        async def hook2(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PreToolUse", hook1)
        manager.add("PostToolUse", hook2)
        result = manager.build()
        assert "PreToolUse" in result
        assert "PostToolUse" in result
        assert len(result["PreToolUse"]) == 1
        assert len(result["PostToolUse"]) == 1

    async def test_build_multiple_hooks_same_event(
        self, manager: HookManager, mock_hook_matcher
    ) -> None:
        """Test building with multiple hooks on same event."""

        async def hook1(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        async def hook2(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PreToolUse", hook1)
        manager.add("PreToolUse", hook2)
        result = manager.build()
        assert len(result["PreToolUse"]) == 2


class TestListHooks:
    """Test list_hooks() returns summaries."""

    async def test_list_empty(self, manager: HookManager) -> None:
        """Test listing hooks when none are registered."""
        result = manager.list_hooks()
        assert result == []

    async def test_list_single_hook(self, manager: HookManager) -> None:
        """Test listing a single hook."""

        async def my_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PreToolUse", my_hook)
        result = manager.list_hooks()
        assert len(result) == 1
        assert result[0]["event"] == "PreToolUse"
        assert result[0]["matcher"] == "*"
        assert result[0]["name"] == "my_hook"
        assert result[0]["timeout"] == 60

    async def test_list_hook_with_matcher(self, manager: HookManager) -> None:
        """Test listing hook shows matcher pattern."""

        async def my_hook(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PreToolUse", my_hook, matcher="Bash")
        result = manager.list_hooks()
        assert result[0]["matcher"] == "Bash"

    async def test_list_multiple_hooks(self, manager: HookManager) -> None:
        """Test listing multiple hooks."""

        async def hook1(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        async def hook2(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        manager.add("PreToolUse", hook1)
        manager.add("PostToolUse", hook2, matcher="Write", timeout=90)
        result = manager.list_hooks()
        assert len(result) == 2
        assert result[0]["name"] == "hook1"
        assert result[1]["name"] == "hook2"
        assert result[1]["timeout"] == 90

    async def test_list_hook_without_name_attribute(self, manager: HookManager) -> None:
        """Test listing hook that doesn't have __name__ attribute."""

        # Create a callable without __name__
        class CallableHook:
            def __call__(
                self, input_data: dict, tool_use_id: str | None, context: Any
            ) -> dict:
                return {}

        hook = CallableHook()
        manager._hooks["PreToolUse"] = [(None, hook, 60)]
        result = manager.list_hooks()
        assert len(result) == 1
        assert "CallableHook" in result[0]["name"]


class TestFileGuard:
    """Test add_file_guard() blocks matching files, allows non-matching."""

    async def test_file_guard_blocks_exact_match(self, manager: HookManager) -> None:
        """Test file guard blocks exact filename match."""
        manager.add_file_guard([".env"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/home/user/.env"},
        }
        result = await guard_callback(input_data, None, None)
        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert ".env" in result["hookSpecificOutput"]["permissionDecisionReason"]

    async def test_file_guard_blocks_glob_pattern(self, manager: HookManager) -> None:
        """Test file guard blocks glob pattern match."""
        manager.add_file_guard(["*.key", "*.pem"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/home/user/private.key"},
        }
        result = await guard_callback(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_file_guard_blocks_full_path_pattern(self, manager: HookManager) -> None:
        """Test file guard blocks full path pattern."""
        manager.add_file_guard(["*/secrets/*"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/home/user/secrets/api.key"},
        }
        result = await guard_callback(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_file_guard_allows_non_matching(self, manager: HookManager) -> None:
        """Test file guard allows non-matching files."""
        manager.add_file_guard([".env", "*.key"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/home/user/config.yaml"},
        }
        result = await guard_callback(input_data, None, None)
        assert result == {}

    async def test_file_guard_empty_file_path(self, manager: HookManager) -> None:
        """Test file guard handles empty file path."""
        manager.add_file_guard([".env"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {"hook_event_name": "PreToolUse", "tool_input": {}}
        result = await guard_callback(input_data, None, None)
        assert result == {}

    async def test_file_guard_matcher_is_write_edit(self, manager: HookManager) -> None:
        """Test file guard is registered with Write|Edit matcher."""
        manager.add_file_guard([".env"])
        hooks = manager._hooks["PreToolUse"]
        assert hooks[0][0] == "Write|Edit"

    async def test_file_guard_has_descriptive_name(self, manager: HookManager) -> None:
        """Test file guard has descriptive __name__."""
        manager.add_file_guard([".env", "*.key"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]
        assert guard_callback.__name__ == "file_guard(.env, *.key)"

    async def test_file_guard_fluent_api(self, manager: HookManager) -> None:
        """Test file guard returns self for chaining."""
        result = manager.add_file_guard([".env"])
        assert result is manager


class TestCommandGuard:
    """Test add_command_guard() blocks dangerous commands, allows safe ones."""

    async def test_command_guard_blocks_dangerous_command(self, manager: HookManager) -> None:
        """Test command guard blocks dangerous command."""
        manager.add_command_guard(["rm -rf /", "sudo rm"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"command": "rm -rf / && echo done"},
        }
        result = await guard_callback(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "rm -rf /" in result["hookSpecificOutput"]["permissionDecisionReason"]

    async def test_command_guard_blocks_partial_match(self, manager: HookManager) -> None:
        """Test command guard blocks substring matches."""
        manager.add_command_guard(["sudo"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"command": "sudo apt-get install curl"},
        }
        result = await guard_callback(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_command_guard_allows_safe_command(self, manager: HookManager) -> None:
        """Test command guard allows safe commands."""
        manager.add_command_guard(["rm -rf /", "sudo"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"command": "ls -la"},
        }
        result = await guard_callback(input_data, None, None)
        assert result == {}

    async def test_command_guard_empty_command(self, manager: HookManager) -> None:
        """Test command guard handles empty command."""
        manager.add_command_guard(["rm -rf /"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {"hook_event_name": "PreToolUse", "tool_input": {}}
        result = await guard_callback(input_data, None, None)
        assert result == {}

    async def test_command_guard_matcher_is_bash(self, manager: HookManager) -> None:
        """Test command guard is registered with Bash matcher."""
        manager.add_command_guard(["rm -rf /"])
        hooks = manager._hooks["PreToolUse"]
        assert hooks[0][0] == "Bash"

    async def test_command_guard_has_descriptive_name(self, manager: HookManager) -> None:
        """Test command guard has descriptive __name__."""
        manager.add_command_guard(["rm -rf /", "sudo rm"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]
        assert guard_callback.__name__ == "command_guard(rm -rf /, sudo rm)"

    async def test_command_guard_fluent_api(self, manager: HookManager) -> None:
        """Test command guard returns self for chaining."""
        result = manager.add_command_guard(["rm -rf /"])
        assert result is manager


class TestAuditLogger:
    """Test add_audit_logger() registers pre+post hooks, calls log_fn."""

    async def test_audit_logger_registers_pre_and_post(self, manager: HookManager) -> None:
        """Test audit logger registers both pre and post hooks."""
        manager.add_audit_logger()
        assert "PreToolUse" in manager._hooks
        assert "PostToolUse" in manager._hooks
        assert len(manager._hooks["PreToolUse"]) == 1
        assert len(manager._hooks["PostToolUse"]) == 1

    async def test_audit_logger_pre_hook_uses_structlog(self, manager: HookManager) -> None:
        """Test audit logger pre hook logs with structlog by default."""
        manager.add_audit_logger()
        pre_hook = manager._hooks["PreToolUse"][0][1]

        with patch("claude_code_bot.hooks.logger.info") as mock_log:
            input_data = {
                "tool_name": "Read",
                "tool_input": {"file_path": "/tmp/test.txt"},
            }
            await pre_hook(input_data, "tool-123", None)
            mock_log.assert_called_once()
            assert mock_log.call_args[0][0] == "hook_audit_pre_tool"
            assert mock_log.call_args[1]["tool"] == "Read"
            assert mock_log.call_args[1]["tool_use_id"] == "tool-123"
            assert "file_path" in mock_log.call_args[1]["input_keys"]

    async def test_audit_logger_post_hook_uses_structlog(self, manager: HookManager) -> None:
        """Test audit logger post hook logs with structlog by default."""
        manager.add_audit_logger()
        post_hook = manager._hooks["PostToolUse"][0][1]

        with patch("claude_code_bot.hooks.logger.info") as mock_log:
            input_data = {"tool_name": "Write"}
            await post_hook(input_data, "tool-456", None)
            mock_log.assert_called_once()
            assert mock_log.call_args[0][0] == "hook_audit_post_tool"
            assert mock_log.call_args[1]["tool"] == "Write"
            assert mock_log.call_args[1]["tool_use_id"] == "tool-456"

    async def test_audit_logger_with_custom_log_fn(self, manager: HookManager) -> None:
        """Test audit logger uses custom log function."""
        log_calls: list[tuple[str, dict]] = []

        def custom_log(event: str, **kwargs: Any) -> None:
            log_calls.append((event, kwargs))

        manager.add_audit_logger(log_fn=custom_log)
        pre_hook = manager._hooks["PreToolUse"][0][1]
        post_hook = manager._hooks["PostToolUse"][0][1]

        input_data = {
            "tool_name": "Bash",
            "tool_input": {"command": "ls"},
        }
        await pre_hook(input_data, "tool-789", None)
        await post_hook(input_data, "tool-789", None)

        assert len(log_calls) == 2
        assert log_calls[0][0] == "pre_tool_use"
        assert log_calls[0][1]["tool"] == "Bash"
        assert log_calls[1][0] == "post_tool_use"
        assert log_calls[1][1]["tool"] == "Bash"

    async def test_audit_logger_returns_empty_dict(self, manager: HookManager) -> None:
        """Test audit logger hooks return empty dict (no permission decision)."""
        manager.add_audit_logger()
        pre_hook = manager._hooks["PreToolUse"][0][1]
        post_hook = manager._hooks["PostToolUse"][0][1]

        input_data = {"tool_name": "Read", "tool_input": {}}
        result_pre = await pre_hook(input_data, None, None)
        result_post = await post_hook(input_data, None, None)

        assert result_pre == {}
        assert result_post == {}

    async def test_audit_logger_has_descriptive_names(self, manager: HookManager) -> None:
        """Test audit logger hooks have descriptive names."""
        manager.add_audit_logger()
        pre_hook = manager._hooks["PreToolUse"][0][1]
        post_hook = manager._hooks["PostToolUse"][0][1]

        assert pre_hook.__name__ == "audit_logger(pre)"
        assert post_hook.__name__ == "audit_logger(post)"

    async def test_audit_logger_fluent_api(self, manager: HookManager) -> None:
        """Test audit logger returns self for chaining."""
        result = manager.add_audit_logger()
        assert result is manager


class TestAutoApprove:
    """Test add_auto_approve() returns allow decision."""

    async def test_auto_approve_returns_allow(self, manager: HookManager) -> None:
        """Test auto approve returns allow permission decision."""
        manager.add_auto_approve(["Read", "Glob"])
        hooks = manager._hooks["PreToolUse"]
        approve_callback = hooks[0][1]

        input_data = {"hook_event_name": "PreToolUse", "tool_input": {}}
        result = await approve_callback(input_data, None, None)

        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert result["hookSpecificOutput"]["permissionDecision"] == "allow"
        assert result["hookSpecificOutput"]["permissionDecisionReason"] == "Auto-approved by hook"

    async def test_auto_approve_matcher(self, manager: HookManager) -> None:
        """Test auto approve creates correct matcher pattern."""
        manager.add_auto_approve(["Read", "Glob", "Grep"])
        hooks = manager._hooks["PreToolUse"]
        assert hooks[0][0] == "Read|Glob|Grep"

    async def test_auto_approve_has_descriptive_name(self, manager: HookManager) -> None:
        """Test auto approve has descriptive __name__."""
        manager.add_auto_approve(["Read", "Write"])
        hooks = manager._hooks["PreToolUse"]
        approve_callback = hooks[0][1]
        assert approve_callback.__name__ == "auto_approve(Read, Write)"

    async def test_auto_approve_fluent_api(self, manager: HookManager) -> None:
        """Test auto approve returns self for chaining."""
        result = manager.add_auto_approve(["Read"])
        assert result is manager


class TestStopHandler:
    """Test add_stop_handler()."""

    async def test_stop_handler_registration(self, manager: HookManager) -> None:
        """Test stop handler registers on Stop event."""

        async def my_stop_handler(
            input_data: dict, tool_use_id: str | None, context: Any
        ) -> dict:
            return {}

        manager.add_stop_handler(my_stop_handler)
        assert "Stop" in manager._hooks
        assert len(manager._hooks["Stop"]) == 1
        assert manager._hooks["Stop"][0][1] is my_stop_handler

    async def test_stop_handler_fluent_api(self, manager: HookManager) -> None:
        """Test stop handler returns self for chaining."""

        async def my_stop_handler(
            input_data: dict, tool_use_id: str | None, context: Any
        ) -> dict:
            return {}

        result = manager.add_stop_handler(my_stop_handler)
        assert result is manager


class TestPromptHandler:
    """Test add_prompt_handler()."""

    async def test_prompt_handler_registration(self, manager: HookManager) -> None:
        """Test prompt handler registers on UserPromptSubmit event."""

        async def my_prompt_handler(
            input_data: dict, tool_use_id: str | None, context: Any
        ) -> dict:
            return {}

        manager.add_prompt_handler(my_prompt_handler)
        assert "UserPromptSubmit" in manager._hooks
        assert len(manager._hooks["UserPromptSubmit"]) == 1
        assert manager._hooks["UserPromptSubmit"][0][1] is my_prompt_handler

    async def test_prompt_handler_fluent_api(self, manager: HookManager) -> None:
        """Test prompt handler returns self for chaining."""

        async def my_prompt_handler(
            input_data: dict, tool_use_id: str | None, context: Any
        ) -> dict:
            return {}

        result = manager.add_prompt_handler(my_prompt_handler)
        assert result is manager


class TestChaining:
    """Test chaining (fluent API)."""

    async def test_chaining_multiple_guards(self, manager: HookManager) -> None:
        """Test chaining multiple guard methods."""
        result = (
            manager.add_file_guard([".env"])
            .add_command_guard(["rm -rf /"])
            .add_auto_approve(["Read"])
        )
        assert result is manager
        assert "PreToolUse" in manager._hooks
        assert len(manager._hooks["PreToolUse"]) == 3

    async def test_chaining_with_audit_logger(self, manager: HookManager) -> None:
        """Test chaining with audit logger."""
        result = (
            manager.add_file_guard([".env"])
            .add_audit_logger()
            .add_command_guard(["sudo"])
        )
        assert result is manager
        assert "PreToolUse" in manager._hooks
        assert "PostToolUse" in manager._hooks

    async def test_chaining_with_handlers(self, manager: HookManager) -> None:
        """Test chaining with stop and prompt handlers."""

        async def stop_cb(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        async def prompt_cb(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        result = (
            manager.add_file_guard([".env"])
            .add_stop_handler(stop_cb)
            .add_prompt_handler(prompt_cb)
        )
        assert result is manager
        assert "PreToolUse" in manager._hooks
        assert "Stop" in manager._hooks
        assert "UserPromptSubmit" in manager._hooks

    async def test_full_chain_build(self, manager: HookManager, mock_hook_matcher) -> None:
        """Test full chain ending with build()."""

        async def stop_cb(input_data: dict, tool_use_id: str | None, context: Any) -> dict:
            return {}

        (
            manager.add_file_guard([".env", "*.key"])
            .add_command_guard(["rm -rf /"])
            .add_auto_approve(["Read", "Glob"])
            .add_audit_logger()
            .add_stop_handler(stop_cb)
        )
        result = manager.build()

        assert "PreToolUse" in result
        assert "PostToolUse" in result
        assert "Stop" in result
        assert len(result["PreToolUse"]) == 4  # file guard, command guard, auto approve, audit pre
        assert len(result["PostToolUse"]) == 1  # audit post
        assert len(result["Stop"]) == 1  # stop handler


class TestEdgeCases:
    """Test edge cases and error handling."""

    async def test_empty_patterns_file_guard(self, manager: HookManager) -> None:
        """Test file guard with empty pattern list."""
        manager.add_file_guard([])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/home/user/.env"},
        }
        result = await guard_callback(input_data, None, None)
        assert result == {}  # No patterns means nothing is blocked

    async def test_empty_patterns_command_guard(self, manager: HookManager) -> None:
        """Test command guard with empty pattern list."""
        manager.add_command_guard([])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"command": "rm -rf /"},
        }
        result = await guard_callback(input_data, None, None)
        assert result == {}

    async def test_empty_tools_auto_approve(self, manager: HookManager) -> None:
        """Test auto approve with empty tools list."""
        manager.add_auto_approve([])
        hooks = manager._hooks["PreToolUse"]
        assert hooks[0][0] == ""  # Empty matcher pattern

    async def test_missing_tool_input(self, manager: HookManager) -> None:
        """Test hooks handle missing tool_input gracefully."""
        manager.add_file_guard([".env"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {"hook_event_name": "PreToolUse"}
        result = await guard_callback(input_data, None, None)
        assert result == {}

    async def test_none_tool_use_id(self, manager: HookManager) -> None:
        """Test hooks handle None tool_use_id."""
        manager.add_audit_logger()
        pre_hook = manager._hooks["PreToolUse"][0][1]

        input_data = {"tool_name": "Read", "tool_input": {}}
        result = await pre_hook(input_data, None, None)
        assert result == {}

    async def test_file_guard_case_sensitive(self, manager: HookManager) -> None:
        """Test file guard is case-sensitive by default."""
        manager.add_file_guard([".env"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/home/user/.ENV"},
        }
        result = await guard_callback(input_data, None, None)
        assert result == {}  # .ENV doesn't match .env (case sensitive)

    async def test_command_guard_case_sensitive(self, manager: HookManager) -> None:
        """Test command guard is case-sensitive."""
        manager.add_command_guard(["sudo"])
        hooks = manager._hooks["PreToolUse"]
        guard_callback = hooks[0][1]

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"command": "SUDO apt-get install"},
        }
        result = await guard_callback(input_data, None, None)
        assert result == {}  # SUDO doesn't match sudo


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    async def test_production_like_setup(
        self, manager: HookManager, mock_hook_matcher
    ) -> None:
        """Test a production-like hook setup."""
        log_calls: list[str] = []

        def custom_log(event: str, **kwargs: Any) -> None:
            log_calls.append(event)

        async def cleanup_handler(
            input_data: dict, tool_use_id: str | None, context: Any
        ) -> dict:
            # Simulate cleanup on stop
            return {}

        (
            manager.add_file_guard([".env", "*.pem", "*.key", "credentials.json"])
            .add_command_guard(["rm -rf /", "sudo rm", "format", "dd if="])
            .add_auto_approve(["Read", "Glob", "Grep"])
            .add_audit_logger(log_fn=custom_log)
            .add_stop_handler(cleanup_handler)
        )

        result = manager.build()
        hooks_summary = manager.list_hooks()

        assert "PreToolUse" in result
        assert "PostToolUse" in result
        assert "Stop" in result
        assert len(hooks_summary) == 6  # 4 PreToolUse + 1 PostToolUse + 1 Stop

    async def test_multiple_guards_order_matters(self, manager: HookManager) -> None:
        """Test that guard order is preserved."""
        manager.add_file_guard([".env"])
        manager.add_command_guard(["sudo"])
        manager.add_auto_approve(["Read"])

        hooks = manager._hooks["PreToolUse"]
        assert "file_guard" in hooks[0][1].__name__
        assert "command_guard" in hooks[1][1].__name__
        assert "auto_approve" in hooks[2][1].__name__
