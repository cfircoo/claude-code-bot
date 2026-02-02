"""Tests for damage control hook system."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
import yaml

from claude_code_bot.hooks import HookManager
from claude_code_bot.hooks.damage_control import (
    DEFAULT_PATTERNS_PATHS,
    _make_bash_path_guard,
    _make_read_guard,
    _make_write_edit_guard,
    load_patterns,
    register_damage_control,
)


# Mock HookMatcher since claude_agent_sdk may not be installed in test env
class MockHookMatcher:
    """Mock HookMatcher for testing."""

    def __init__(self, hooks: list, matcher: str | None = None, timeout: int = 60) -> None:
        self.hooks = hooks
        self.matcher = matcher
        self.timeout = timeout


@pytest.fixture
def mock_hook_matcher():
    """Mock the HookMatcher import."""
    with patch("claude_code_bot.hooks.manager.HookMatcher", MockHookMatcher):
        yield MockHookMatcher


@pytest.fixture
def manager() -> HookManager:
    """Create a fresh HookManager instance."""
    return HookManager()


class TestLoadPatterns:
    """Test load_patterns() YAML loading logic."""

    def test_load_valid_yaml_custom_path(self, tmp_path: Path) -> None:
        """Test loading patterns from a valid custom YAML file."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {
            "zeroAccessPaths": ["/etc/shadow", "~/.ssh/*"],
            "readOnlyPaths": ["*.lock"],
            "noDeletePaths": ["/var/log/*"],
            "bashToolPatterns": [
                {"pattern": r"\brm\s+-rf\s+/", "ask": False},
                {"pattern": r"\bsudo\b", "ask": True, "reason": "Requires elevated privileges"},
            ],
        }
        patterns_file.write_text(yaml.safe_dump(config))

        result = load_patterns(str(patterns_file))

        assert result == config
        assert result["zeroAccessPaths"] == ["/etc/shadow", "~/.ssh/*"]
        assert result["readOnlyPaths"] == ["*.lock"]
        assert result["noDeletePaths"] == ["/var/log/*"]
        assert len(result["bashToolPatterns"]) == 2

    def test_load_patterns_missing_file_custom_path(self, tmp_path: Path) -> None:
        """Test loading patterns from non-existent custom path returns empty dict."""
        nonexistent = tmp_path / "does_not_exist.yaml"

        result = load_patterns(str(nonexistent))

        assert result == {}

    def test_load_patterns_empty_yaml(self, tmp_path: Path) -> None:
        """Test loading patterns from empty YAML file returns empty dict."""
        patterns_file = tmp_path / "empty.yaml"
        patterns_file.write_text("")

        result = load_patterns(str(patterns_file))

        assert result == {}

    def test_load_patterns_malformed_yaml(self, tmp_path: Path) -> None:
        """Test loading patterns from malformed YAML raises exception."""
        patterns_file = tmp_path / "malformed.yaml"
        patterns_file.write_text("{ invalid: yaml: [")

        with pytest.raises(yaml.YAMLError):
            load_patterns(str(patterns_file))

    def test_load_patterns_default_locations_none_exist(self, tmp_path: Path, monkeypatch) -> None:
        """Test loading patterns from default locations when none exist."""
        # Mock the default paths to non-existent locations
        fake_paths = [tmp_path / "fake1.yaml", tmp_path / "fake2.yaml"]
        monkeypatch.setattr("claude_code_bot.hooks.damage_control.DEFAULT_PATTERNS_PATHS", fake_paths)

        result = load_patterns()

        assert result == {}

    def test_load_patterns_default_locations_first_exists(self, tmp_path: Path, monkeypatch) -> None:
        """Test loading patterns finds first existing default location."""
        first = tmp_path / "first.yaml"
        second = tmp_path / "second.yaml"
        config = {"zeroAccessPaths": ["/secret"]}
        first.write_text(yaml.safe_dump(config))

        monkeypatch.setattr("claude_code_bot.hooks.damage_control.DEFAULT_PATTERNS_PATHS", [first, second])

        result = load_patterns()

        assert result == config

    def test_load_patterns_default_locations_second_exists(self, tmp_path: Path, monkeypatch) -> None:
        """Test loading patterns skips missing first, loads second default location."""
        first = tmp_path / "first.yaml"
        second = tmp_path / "second.yaml"
        config = {"readOnlyPaths": ["*.log"]}
        second.write_text(yaml.safe_dump(config))

        monkeypatch.setattr("claude_code_bot.hooks.damage_control.DEFAULT_PATTERNS_PATHS", [first, second])

        result = load_patterns()

        assert result == config

    def test_load_patterns_none_value_yaml(self, tmp_path: Path) -> None:
        """Test loading YAML that evaluates to None returns empty dict."""
        patterns_file = tmp_path / "none.yaml"
        patterns_file.write_text("null")

        result = load_patterns(str(patterns_file))

        assert result == {}


class TestMakeReadGuard:
    """Test _make_read_guard() blocks zero-access paths."""

    async def test_read_guard_blocks_exact_path(self) -> None:
        """Test read guard blocks exact zero-access path."""
        guard = _make_read_guard(["/etc/shadow"])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/etc/shadow"},
        }
        result = await guard(input_data, None, None)

        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Zero-access path" in result["hookSpecificOutput"]["permissionDecisionReason"]
        assert "/etc/shadow" in result["hookSpecificOutput"]["permissionDecisionReason"]

    async def test_read_guard_blocks_glob_pattern(self) -> None:
        """Test read guard blocks files matching glob pattern."""
        guard = _make_read_guard(["*.env"])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/home/user/project/.env"},
        }
        result = await guard(input_data, None, None)

        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_read_guard_blocks_wildcard_pattern(self) -> None:
        """Test read guard blocks files matching wildcard pattern."""
        import os

        # Use actual expanded home directory
        home = os.path.expanduser("~")
        guard = _make_read_guard([f"{home}/.ssh/*"])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": f"{home}/.ssh/id_rsa"},
        }
        result = await guard(input_data, None, None)

        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_read_guard_allows_non_matching_path(self) -> None:
        """Test read guard allows paths that don't match zero-access patterns."""
        guard = _make_read_guard(["/etc/shadow", "*.env"])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/home/user/config.yaml"},
        }
        result = await guard(input_data, None, None)

        assert result == {}

    async def test_read_guard_empty_file_path(self) -> None:
        """Test read guard handles empty file path."""
        guard = _make_read_guard(["/etc/shadow"])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {},
        }
        result = await guard(input_data, None, None)

        assert result == {}

    async def test_read_guard_missing_tool_input(self) -> None:
        """Test read guard handles missing tool_input."""
        guard = _make_read_guard(["/etc/shadow"])

        input_data = {"hook_event_name": "PreToolUse"}
        result = await guard(input_data, None, None)

        assert result == {}

    async def test_read_guard_multiple_patterns(self) -> None:
        """Test read guard checks all patterns."""
        guard = _make_read_guard(["/etc/shadow", "/etc/passwd", "~/.ssh/*"])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/etc/passwd"},
        }
        result = await guard(input_data, None, None)

        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "/etc/passwd" in result["hookSpecificOutput"]["permissionDecisionReason"]

    async def test_read_guard_has_name(self) -> None:
        """Test read guard has descriptive name."""
        guard = _make_read_guard(["/etc/shadow"])

        assert guard.__name__ == "damage_control(read)"


class TestMakeWriteEditGuard:
    """Test _make_write_edit_guard() blocks zero-access and read-only paths."""

    async def test_write_edit_guard_blocks_zero_access(self) -> None:
        """Test write/edit guard blocks zero-access paths."""
        guard = _make_write_edit_guard(["/etc/shadow"], [])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/etc/shadow"},
        }
        result = await guard(input_data, None, None)

        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Zero-access path" in result["hookSpecificOutput"]["permissionDecisionReason"]

    async def test_write_edit_guard_blocks_read_only(self) -> None:
        """Test write/edit guard blocks read-only paths."""
        guard = _make_write_edit_guard([], ["*.lock"])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/home/user/package.lock"},
        }
        result = await guard(input_data, None, None)

        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Read-only path" in result["hookSpecificOutput"]["permissionDecisionReason"]

    async def test_write_edit_guard_zero_access_takes_precedence(self) -> None:
        """Test write/edit guard checks zero-access before read-only."""
        guard = _make_write_edit_guard(["/etc/shadow"], ["/etc/*"])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/etc/shadow"},
        }
        result = await guard(input_data, None, None)

        # Should report zero-access, not read-only
        assert "Zero-access path" in result["hookSpecificOutput"]["permissionDecisionReason"]

    async def test_write_edit_guard_allows_non_protected(self) -> None:
        """Test write/edit guard allows non-protected paths."""
        guard = _make_write_edit_guard(["/etc/shadow"], ["*.lock"])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/home/user/config.yaml"},
        }
        result = await guard(input_data, None, None)

        assert result == {}

    async def test_write_edit_guard_empty_file_path(self) -> None:
        """Test write/edit guard handles empty file path."""
        guard = _make_write_edit_guard(["/etc/shadow"], ["*.lock"])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {},
        }
        result = await guard(input_data, None, None)

        assert result == {}

    async def test_write_edit_guard_glob_patterns(self) -> None:
        """Test write/edit guard works with glob patterns."""
        import os

        home = os.path.expanduser("~")
        guard = _make_write_edit_guard([f"{home}/.ssh/*"], ["*.json"])

        # Zero-access glob
        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": f"{home}/.ssh/id_rsa"},
        }
        result = await guard(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

        # Read-only glob
        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"file_path": "/home/user/package-lock.json"},
        }
        result = await guard(input_data, None, None)
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_write_edit_guard_has_name(self) -> None:
        """Test write/edit guard has descriptive name."""
        guard = _make_write_edit_guard(["/etc/shadow"], ["*.lock"])

        assert guard.__name__ == "damage_control(write/edit)"


class TestMakeBashPathGuard:
    """Test _make_bash_path_guard() blocks bash commands on protected paths."""

    async def test_bash_guard_blocks_zero_access_mention(self) -> None:
        """Test bash guard blocks any mention of zero-access paths."""
        guard = _make_bash_path_guard(["/etc/shadow"], [], [])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"command": "cat /etc/shadow"},
        }
        result = await guard(input_data, None, None)

        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Zero-access path" in result["hookSpecificOutput"]["permissionDecisionReason"]

    async def test_bash_guard_blocks_zero_access_glob(self) -> None:
        """Test bash guard blocks commands mentioning zero-access glob patterns."""
        guard = _make_bash_path_guard(["~/.ssh/*"], [], [])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"command": "ls ~/.ssh/id_rsa"},
        }
        result = await guard(input_data, None, None)

        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_bash_guard_blocks_read_only_modification(self) -> None:
        """Test bash guard blocks modifications to read-only paths."""
        guard = _make_bash_path_guard([], ["*.lock"], [])

        # Test various modification patterns
        commands = [
            "echo 'foo' > package.lock",
            "sed -i 's/old/new/' package.lock",
            "mv backup.lock package.lock",
            "cp source.txt package.lock",
            "chmod 755 package.lock",
            "chown user:group package.lock",
            "truncate -s 0 package.lock",
        ]

        for cmd in commands:
            input_data = {
                "hook_event_name": "PreToolUse",
                "tool_input": {"command": cmd},
            }
            result = await guard(input_data, None, None)
            assert result["hookSpecificOutput"]["permissionDecision"] == "deny", f"Failed on: {cmd}"
            assert "Read-only path" in result["hookSpecificOutput"]["permissionDecisionReason"]

    async def test_bash_guard_blocks_read_only_deletion(self) -> None:
        """Test bash guard blocks deletions of read-only paths."""
        guard = _make_bash_path_guard([], ["*.lock"], [])

        commands = [
            "rm package.lock",
            "rm -rf package.lock",
            "unlink package.lock",
            "shred package.lock",
        ]

        for cmd in commands:
            input_data = {
                "hook_event_name": "PreToolUse",
                "tool_input": {"command": cmd},
            }
            result = await guard(input_data, None, None)
            assert result["hookSpecificOutput"]["permissionDecision"] == "deny", f"Failed on: {cmd}"

    async def test_bash_guard_blocks_no_delete_deletion(self) -> None:
        """Test bash guard blocks deletions (but not modifications) of no-delete paths."""
        guard = _make_bash_path_guard([], [], ["/var/log/*"])

        # Deletions should be blocked
        delete_commands = [
            "rm /var/log/app.log",
            "rm -rf /var/log/app.log",
            "unlink /var/log/app.log",
        ]

        for cmd in delete_commands:
            input_data = {
                "hook_event_name": "PreToolUse",
                "tool_input": {"command": cmd},
            }
            result = await guard(input_data, None, None)
            assert result["hookSpecificOutput"]["permissionDecision"] == "deny", f"Failed on: {cmd}"
            assert "No-delete path" in result["hookSpecificOutput"]["permissionDecisionReason"]

    async def test_bash_guard_allows_no_delete_modifications(self) -> None:
        """Test bash guard allows modifications to no-delete paths."""
        guard = _make_bash_path_guard([], [], ["/var/log/*"])

        # Modifications should be allowed
        modify_commands = [
            "echo 'log entry' >> /var/log/app.log",
            "sed -i 's/old/new/' /var/log/app.log",
            "cat >> /var/log/app.log",
        ]

        for cmd in modify_commands:
            input_data = {
                "hook_event_name": "PreToolUse",
                "tool_input": {"command": cmd},
            }
            result = await guard(input_data, None, None)
            assert result == {}, f"Should allow: {cmd}"

    async def test_bash_guard_allows_read_only_reads(self) -> None:
        """Test bash guard allows reads of read-only paths."""
        guard = _make_bash_path_guard([], ["*.lock"], [])

        read_commands = [
            "cat package.lock",
            "less package.lock",
            "grep 'foo' package.lock",
            "head -n 10 package.lock",
        ]

        for cmd in read_commands:
            input_data = {
                "hook_event_name": "PreToolUse",
                "tool_input": {"command": cmd},
            }
            result = await guard(input_data, None, None)
            assert result == {}, f"Should allow: {cmd}"

    async def test_bash_guard_allows_safe_commands(self) -> None:
        """Test bash guard allows commands not touching protected paths."""
        guard = _make_bash_path_guard(["/etc/shadow"], ["*.lock"], ["/var/log/*"])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"command": "ls -la /home/user"},
        }
        result = await guard(input_data, None, None)

        assert result == {}

    async def test_bash_guard_empty_command(self) -> None:
        """Test bash guard handles empty command."""
        guard = _make_bash_path_guard(["/etc/shadow"], [], [])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {},
        }
        result = await guard(input_data, None, None)

        assert result == {}

    async def test_bash_guard_expanduser_support(self) -> None:
        """Test bash guard expands ~ in paths."""
        guard = _make_bash_path_guard(["~/.ssh/id_rsa"], [], [])

        input_data = {
            "hook_event_name": "PreToolUse",
            "tool_input": {"command": "cat ~/.ssh/id_rsa"},
        }
        result = await guard(input_data, None, None)

        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_bash_guard_has_name(self) -> None:
        """Test bash guard has descriptive name."""
        guard = _make_bash_path_guard(["/etc/shadow"], ["*.lock"], ["/var/log/*"])

        assert guard.__name__ == "damage_control(bash/paths)"


class TestRegisterDamageControl:
    """Test register_damage_control() registers all hooks correctly."""

    def test_register_damage_control_no_patterns(self, manager: HookManager) -> None:
        """Test registering damage control with no patterns file does nothing."""
        register_damage_control(manager, patterns_path="/nonexistent.yaml")

        assert len(manager._hooks) == 0

    def test_register_damage_control_empty_config(self, manager: HookManager, tmp_path: Path) -> None:
        """Test registering damage control with empty config does nothing."""
        patterns_file = tmp_path / "empty.yaml"
        patterns_file.write_text(yaml.safe_dump({}))

        register_damage_control(manager, patterns_path=str(patterns_file))

        assert len(manager._hooks) == 0

    def test_register_damage_control_bash_block_patterns(self, manager: HookManager, tmp_path: Path) -> None:
        """Test registering bash command block patterns."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {
            "bashToolPatterns": [
                {"pattern": r"\brm\s+-rf\s+/", "ask": False},
                {"pattern": r"\bformat\b", "ask": False},
            ]
        }
        patterns_file.write_text(yaml.safe_dump(config))

        register_damage_control(manager, patterns_path=str(patterns_file))

        assert "PreToolUse" in manager._hooks
        hooks = manager._hooks["PreToolUse"]
        assert len(hooks) == 1
        assert hooks[0][0] == "Bash"  # matcher
        assert "damage_control(bash/commands)" in hooks[0][1].__name__

    def test_register_damage_control_bash_ask_patterns(self, manager: HookManager, tmp_path: Path) -> None:
        """Test registering bash command ask patterns."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {
            "bashToolPatterns": [
                {"pattern": r"\bsudo\b", "ask": True, "reason": "Requires elevated privileges"}
            ]
        }
        patterns_file.write_text(yaml.safe_dump(config))

        register_damage_control(manager, patterns_path=str(patterns_file))

        assert "PreToolUse" in manager._hooks
        hooks = manager._hooks["PreToolUse"]
        assert len(hooks) == 1
        assert hooks[0][0] == "Bash"
        assert "damage_control(bash/ask)" in hooks[0][1].__name__

    def test_register_damage_control_zero_access_paths(self, manager: HookManager, tmp_path: Path) -> None:
        """Test registering zero-access paths creates bash and read guards."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {"zeroAccessPaths": ["/etc/shadow", "~/.ssh/*"]}
        patterns_file.write_text(yaml.safe_dump(config))

        register_damage_control(manager, patterns_path=str(patterns_file))

        assert "PreToolUse" in manager._hooks
        hooks = manager._hooks["PreToolUse"]
        # Should have bash path guard and read guard
        assert len(hooks) >= 2

        # Check for bash guard
        bash_guards = [h for h in hooks if h[0] == "Bash"]
        assert len(bash_guards) == 1
        assert "damage_control(bash/paths)" in bash_guards[0][1].__name__

        # Check for read guard
        read_guards = [h for h in hooks if h[0] == "Read"]
        assert len(read_guards) == 1
        assert "damage_control(read)" in read_guards[0][1].__name__

    def test_register_damage_control_read_only_paths(self, manager: HookManager, tmp_path: Path) -> None:
        """Test registering read-only paths creates bash and write/edit guards."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {"readOnlyPaths": ["*.lock", "*.json"]}
        patterns_file.write_text(yaml.safe_dump(config))

        register_damage_control(manager, patterns_path=str(patterns_file))

        assert "PreToolUse" in manager._hooks
        hooks = manager._hooks["PreToolUse"]
        # Should have bash path guard and write/edit guard
        assert len(hooks) >= 2

        # Check for bash guard
        bash_guards = [h for h in hooks if h[0] == "Bash"]
        assert len(bash_guards) == 1

        # Check for write/edit guard
        write_guards = [h for h in hooks if h[0] == "Write|Edit"]
        assert len(write_guards) == 1
        assert "damage_control(write/edit)" in write_guards[0][1].__name__

    def test_register_damage_control_no_delete_paths(self, manager: HookManager, tmp_path: Path) -> None:
        """Test registering no-delete paths creates bash guard."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {"noDeletePaths": ["/var/log/*"]}
        patterns_file.write_text(yaml.safe_dump(config))

        register_damage_control(manager, patterns_path=str(patterns_file))

        assert "PreToolUse" in manager._hooks
        hooks = manager._hooks["PreToolUse"]
        # Should have bash path guard only
        assert len(hooks) == 1

        bash_guards = [h for h in hooks if h[0] == "Bash"]
        assert len(bash_guards) == 1
        assert "damage_control(bash/paths)" in bash_guards[0][1].__name__

    def test_register_damage_control_comprehensive(self, manager: HookManager, tmp_path: Path) -> None:
        """Test registering comprehensive damage control config."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {
            "bashToolPatterns": [
                {"pattern": r"\brm\s+-rf\s+/", "ask": False},
                {"pattern": r"\bsudo\b", "ask": True, "reason": "Needs sudo"},
            ],
            "zeroAccessPaths": ["/etc/shadow"],
            "readOnlyPaths": ["*.lock"],
            "noDeletePaths": ["/var/log/*"],
        }
        patterns_file.write_text(yaml.safe_dump(config))

        register_damage_control(manager, patterns_path=str(patterns_file))

        # Should register multiple hooks
        assert "PreToolUse" in manager._hooks
        hooks = manager._hooks["PreToolUse"]

        # Count each type
        bash_commands = [h for h in hooks if "bash/commands" in h[1].__name__]
        bash_ask = [h for h in hooks if "bash/ask" in h[1].__name__]
        bash_paths = [h for h in hooks if "bash/paths" in h[1].__name__]
        read_guards = [h for h in hooks if h[0] == "Read"]
        write_guards = [h for h in hooks if h[0] == "Write|Edit"]

        assert len(bash_commands) == 1  # block patterns
        assert len(bash_ask) == 1  # ask patterns
        assert len(bash_paths) == 1  # path guards
        assert len(read_guards) == 1  # zero-access read guard
        assert len(write_guards) == 1  # zero-access + read-only write guard

    def test_register_damage_control_uses_default_path_when_none(self, manager: HookManager, tmp_path: Path, monkeypatch) -> None:
        """Test registering damage control uses default path when patterns_path is None."""
        patterns_file = tmp_path / "default.yaml"
        config = {"zeroAccessPaths": ["/etc/shadow"]}
        patterns_file.write_text(yaml.safe_dump(config))

        monkeypatch.setattr("claude_code_bot.hooks.damage_control.DEFAULT_PATTERNS_PATHS", [patterns_file])

        register_damage_control(manager, patterns_path=None)

        assert "PreToolUse" in manager._hooks
        assert len(manager._hooks["PreToolUse"]) > 0


class TestIntegration:
    """Test full damage control integration scenarios."""

    async def test_full_damage_control_zero_access_blocks_all(self, manager: HookManager, tmp_path: Path) -> None:
        """Test zero-access path blocks all operations."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {"zeroAccessPaths": ["/etc/shadow"]}
        patterns_file.write_text(yaml.safe_dump(config))

        register_damage_control(manager, patterns_path=str(patterns_file))
        hooks = manager._hooks["PreToolUse"]

        # Read should be blocked
        read_guard = next(h[1] for h in hooks if h[0] == "Read")
        result = await read_guard(
            {"hook_event_name": "PreToolUse", "tool_input": {"file_path": "/etc/shadow"}},
            None,
            None,
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

        # Write should be blocked
        write_guard = next(h[1] for h in hooks if h[0] == "Write|Edit")
        result = await write_guard(
            {"hook_event_name": "PreToolUse", "tool_input": {"file_path": "/etc/shadow"}},
            None,
            None,
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

        # Bash mention should be blocked
        bash_guard = next(h[1] for h in hooks if h[0] == "Bash")
        result = await bash_guard(
            {"hook_event_name": "PreToolUse", "tool_input": {"command": "cat /etc/shadow"}},
            None,
            None,
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

    async def test_full_damage_control_read_only_allows_read_blocks_write(
        self, manager: HookManager, tmp_path: Path
    ) -> None:
        """Test read-only path allows reads but blocks writes."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {"readOnlyPaths": ["*.lock"]}
        patterns_file.write_text(yaml.safe_dump(config))

        register_damage_control(manager, patterns_path=str(patterns_file))
        hooks = manager._hooks["PreToolUse"]

        # Write should be blocked
        write_guard = next(h[1] for h in hooks if h[0] == "Write|Edit")
        result = await write_guard(
            {"hook_event_name": "PreToolUse", "tool_input": {"file_path": "/home/user/package.lock"}},
            None,
            None,
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

        # Bash write should be blocked
        bash_guard = next(h[1] for h in hooks if h[0] == "Bash")
        result = await bash_guard(
            {"hook_event_name": "PreToolUse", "tool_input": {"command": "echo 'x' > package.lock"}},
            None,
            None,
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

        # Bash read should be allowed
        result = await bash_guard(
            {"hook_event_name": "PreToolUse", "tool_input": {"command": "cat package.lock"}},
            None,
            None,
        )
        assert result == {}

    async def test_full_damage_control_no_delete_allows_modify_blocks_delete(
        self, manager: HookManager, tmp_path: Path
    ) -> None:
        """Test no-delete path allows modifications but blocks deletions."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {"noDeletePaths": ["/var/log/*"]}
        patterns_file.write_text(yaml.safe_dump(config))

        register_damage_control(manager, patterns_path=str(patterns_file))
        hooks = manager._hooks["PreToolUse"]
        bash_guard = next(h[1] for h in hooks if h[0] == "Bash")

        # Deletion should be blocked
        result = await bash_guard(
            {"hook_event_name": "PreToolUse", "tool_input": {"command": "rm /var/log/app.log"}},
            None,
            None,
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

        # Modification should be allowed
        result = await bash_guard(
            {"hook_event_name": "PreToolUse", "tool_input": {"command": "echo 'log' >> /var/log/app.log"}},
            None,
            None,
        )
        assert result == {}

    async def test_full_damage_control_bash_patterns_block_and_ask(
        self, manager: HookManager, tmp_path: Path
    ) -> None:
        """Test bash patterns can block or ask for confirmation."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {
            "bashToolPatterns": [
                {"pattern": r"\brm\s+-rf\s+/", "ask": False},
                {"pattern": r"\bsudo\b", "ask": True, "reason": "Needs sudo"},
            ]
        }
        patterns_file.write_text(yaml.safe_dump(config))

        register_damage_control(manager, patterns_path=str(patterns_file))
        hooks = manager._hooks["PreToolUse"]
        bash_hooks = [h[1] for h in hooks if h[0] == "Bash"]

        # Block pattern should deny
        block_guard = next(h for h in bash_hooks if "commands" in h.__name__)
        result = await block_guard(
            {"hook_event_name": "PreToolUse", "tool_input": {"command": "rm -rf /"}},
            None,
            None,
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"

        # Ask pattern should ask
        ask_guard = next(h for h in bash_hooks if "ask" in h.__name__)
        result = await ask_guard(
            {"hook_event_name": "PreToolUse", "tool_input": {"command": "sudo apt-get install curl"}},
            None,
            None,
        )
        assert result["hookSpecificOutput"]["permissionDecision"] == "ask"
        assert "Needs sudo" in result["hookSpecificOutput"]["permissionDecisionReason"]

    async def test_full_damage_control_layered_protection(
        self, manager: HookManager, tmp_path: Path
    ) -> None:
        """Test layered protection with multiple pattern types."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {
            "bashToolPatterns": [{"pattern": r"\brm\s+-rf\s+/", "ask": False}],
            "zeroAccessPaths": ["/etc/shadow"],
            "readOnlyPaths": ["*.lock"],
            "noDeletePaths": ["/var/log/*"],
        }
        patterns_file.write_text(yaml.safe_dump(config))

        register_damage_control(manager, patterns_path=str(patterns_file))

        # Verify multiple protection layers are active
        assert "PreToolUse" in manager._hooks
        hooks = manager._hooks["PreToolUse"]
        # bash commands, bash paths, read, write/edit (no bash ask since only block patterns)
        assert len(hooks) >= 4

        # Test that different protections work independently
        bash_guards = [h[1] for h in hooks if h[0] == "Bash"]
        assert len(bash_guards) >= 2  # command guard + path guard

    def test_integration_with_hook_manager_build(
        self, manager: HookManager, tmp_path: Path, mock_hook_matcher
    ) -> None:
        """Test damage control integrates with HookManager.build()."""
        patterns_file = tmp_path / "patterns.yaml"
        config = {
            "zeroAccessPaths": ["/etc/shadow"],
            "readOnlyPaths": ["*.lock"],
        }
        patterns_file.write_text(yaml.safe_dump(config))

        register_damage_control(manager, patterns_path=str(patterns_file))
        result = manager.build()

        assert "PreToolUse" in result
        matchers = result["PreToolUse"]
        assert len(matchers) >= 3  # bash, read, write|edit guards

        # Verify matchers have correct tool patterns
        bash_matchers = [m for m in matchers if m.matcher == "Bash"]
        read_matchers = [m for m in matchers if m.matcher == "Read"]
        write_matchers = [m for m in matchers if m.matcher == "Write|Edit"]

        assert len(bash_matchers) >= 1
        assert len(read_matchers) == 1
        assert len(write_matchers) == 1
