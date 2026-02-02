"""Tests for TelegramAuthGuard authorization and permissions logic."""

import pytest

from claude_code_bot.config import AllowedUser
from claude_code_bot.hooks.telegram_auth import TelegramAuthGuard, _match_any


class TestTelegramAuthGuardBasicAuth:
    """Test basic authorization (is_authorized, get_user, has_restrictions)."""

    def test_empty_allowed_list_authorizes_all_users(self) -> None:
        """When allowed_users is empty, all users should be authorized."""
        guard = TelegramAuthGuard(allowed_users=[])

        assert guard.is_authorized(user_id=12345, username="alice")
        assert guard.is_authorized(user_id=67890, username="bob")
        assert guard.is_authorized(user_id=99999, username="charlie")

    def test_empty_allowed_list_authorizes_even_with_none_username(self) -> None:
        """When allowed_users is empty, even None username should be authorized."""
        guard = TelegramAuthGuard(allowed_users=[])

        assert guard.is_authorized(user_id=12345, username=None)

    def test_has_restrictions_empty_list(self) -> None:
        """has_restrictions should return False when allowed_users is empty."""
        guard = TelegramAuthGuard(allowed_users=[])

        assert not guard.has_restrictions

    def test_has_restrictions_with_users(self) -> None:
        """has_restrictions should return True when allowed_users is not empty."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert guard.has_restrictions

    def test_user_in_list_is_authorized(self) -> None:
        """User with matching user_id and username should be authorized."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert guard.is_authorized(user_id=12345, username="alice")

    def test_user_not_in_list_is_denied(self) -> None:
        """User not in allowed list should be denied."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert not guard.is_authorized(user_id=99999, username="bob")

    def test_matching_user_id_but_wrong_username_is_denied(self) -> None:
        """User with matching user_id but wrong username should be denied."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert not guard.is_authorized(user_id=12345, username="bob")

    def test_matching_username_but_wrong_user_id_is_denied(self) -> None:
        """User with matching username but wrong user_id should be denied."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert not guard.is_authorized(user_id=99999, username="alice")

    def test_none_username_is_denied_when_list_not_empty(self) -> None:
        """User with None username should be denied when allowed list is not empty."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert not guard.is_authorized(user_id=12345, username=None)
        assert not guard.is_authorized(user_id=99999, username=None)

    def test_multiple_allowed_users(self) -> None:
        """Multiple users in allowed list should all be authorized."""
        allowed = [
            AllowedUser(user_id=12345, username="alice"),
            AllowedUser(user_id=67890, username="bob"),
            AllowedUser(user_id=11111, username="charlie"),
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # All allowed users should be authorized
        assert guard.is_authorized(user_id=12345, username="alice")
        assert guard.is_authorized(user_id=67890, username="bob")
        assert guard.is_authorized(user_id=11111, username="charlie")

        # User not in list should be denied
        assert not guard.is_authorized(user_id=99999, username="dave")

        # Mixed credentials should be denied
        assert not guard.is_authorized(user_id=12345, username="bob")
        assert not guard.is_authorized(user_id=67890, username="alice")

    def test_custom_deny_message(self) -> None:
        """Custom deny message should be set correctly."""
        custom_message = "Access denied. Contact admin for help."
        guard = TelegramAuthGuard(
            allowed_users=[],
            deny_message=custom_message
        )

        assert guard.deny_message == custom_message

    def test_default_deny_message(self) -> None:
        """Default deny message should be set when not provided."""
        guard = TelegramAuthGuard(allowed_users=[])

        assert guard.deny_message == "You are not authorized to use this bot."

    def test_get_user_returns_user_when_found(self) -> None:
        """get_user should return AllowedUser when user exists."""
        allowed = [
            AllowedUser(user_id=12345, username="alice", allowed_tools=["Read", "Write"]),
            AllowedUser(user_id=67890, username="bob"),
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        user = guard.get_user(user_id=12345, username="alice")
        assert user is not None
        assert user.user_id == 12345
        assert user.username == "alice"
        assert user.allowed_tools == ["Read", "Write"]

    def test_get_user_returns_none_when_not_found(self) -> None:
        """get_user should return None when user does not exist."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        user = guard.get_user(user_id=99999, username="bob")
        assert user is None

    def test_get_user_returns_none_when_username_is_none(self) -> None:
        """get_user should return None when username is None."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        user = guard.get_user(user_id=12345, username=None)
        assert user is None

    def test_get_user_returns_none_for_empty_guard(self) -> None:
        """get_user should return None when allowed_users is empty."""
        guard = TelegramAuthGuard(allowed_users=[])

        user = guard.get_user(user_id=12345, username="alice")
        assert user is None

    @pytest.mark.parametrize("user_id,username,expected", [
        (12345, "alice", True),
        (12345, "bob", False),
        (99999, "alice", False),
        (99999, "bob", False),
        (12345, None, False),
        (99999, None, False),
    ])
    def test_authorization_parametrized(
        self, user_id: int, username: str | None, expected: bool
    ) -> None:
        """Parametrized test for various authorization scenarios."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert guard.is_authorized(user_id=user_id, username=username) == expected

    def test_case_sensitive_username(self) -> None:
        """Username matching should be case-sensitive."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert guard.is_authorized(user_id=12345, username="alice")
        assert not guard.is_authorized(user_id=12345, username="Alice")
        assert not guard.is_authorized(user_id=12345, username="ALICE")

    def test_username_with_special_characters(self) -> None:
        """Usernames with special characters should work correctly."""
        allowed = [
            AllowedUser(user_id=12345, username="alice_123"),
            AllowedUser(user_id=67890, username="bob-dev"),
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert guard.is_authorized(user_id=12345, username="alice_123")
        assert guard.is_authorized(user_id=67890, username="bob-dev")

    def test_large_user_id(self) -> None:
        """Large user IDs should be handled correctly."""
        large_id = 9999999999
        allowed = [AllowedUser(user_id=large_id, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert guard.is_authorized(user_id=large_id, username="alice")
        assert not guard.is_authorized(user_id=large_id - 1, username="alice")


class TestTelegramAuthGuardToolPermissions:
    """Test check_tool method for tool-level permissions."""

    def test_empty_allowed_tools_permits_all_tools(self) -> None:
        """When allowed_tools is empty, all tools should be permitted."""
        allowed = [AllowedUser(user_id=12345, username="alice", allowed_tools=[])]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert guard.check_tool(user_id=12345, username="alice", tool_name="Read")
        assert guard.check_tool(user_id=12345, username="alice", tool_name="Write")
        assert guard.check_tool(user_id=12345, username="alice", tool_name="Bash")
        assert guard.check_tool(user_id=12345, username="alice", tool_name="Edit")

    def test_specific_allowed_tools_restricts_access(self) -> None:
        """When allowed_tools is specified, only those tools should be permitted."""
        allowed = [
            AllowedUser(user_id=12345, username="alice", allowed_tools=["Read", "Write"])
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # Allowed tools
        assert guard.check_tool(user_id=12345, username="alice", tool_name="Read")
        assert guard.check_tool(user_id=12345, username="alice", tool_name="Write")

        # Disallowed tools
        assert not guard.check_tool(user_id=12345, username="alice", tool_name="Bash")
        assert not guard.check_tool(user_id=12345, username="alice", tool_name="Edit")
        assert not guard.check_tool(user_id=12345, username="alice", tool_name="Delete")

    def test_user_not_found_with_restrictions_denies_tools(self) -> None:
        """When restrictions exist but user not found, tools should be denied."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # User not in list
        assert not guard.check_tool(user_id=99999, username="bob", tool_name="Read")
        assert not guard.check_tool(user_id=99999, username="bob", tool_name="Bash")

    def test_user_not_found_without_restrictions_allows_tools(self) -> None:
        """When no restrictions exist (empty list), tools should be allowed."""
        guard = TelegramAuthGuard(allowed_users=[])

        assert guard.check_tool(user_id=12345, username="alice", tool_name="Read")
        assert guard.check_tool(user_id=99999, username="bob", tool_name="Bash")

    def test_none_username_with_restrictions_denies_tools(self) -> None:
        """When username is None and restrictions exist, tools should be denied."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert not guard.check_tool(user_id=12345, username=None, tool_name="Read")
        assert not guard.check_tool(user_id=99999, username=None, tool_name="Write")

    def test_none_username_without_restrictions_allows_tools(self) -> None:
        """When username is None and no restrictions, tools should be allowed."""
        guard = TelegramAuthGuard(allowed_users=[])

        assert guard.check_tool(user_id=12345, username=None, tool_name="Read")
        assert guard.check_tool(user_id=99999, username=None, tool_name="Bash")

    def test_different_users_different_tool_permissions(self) -> None:
        """Different users can have different tool permissions."""
        allowed = [
            AllowedUser(user_id=12345, username="alice", allowed_tools=["Read"]),
            AllowedUser(user_id=67890, username="bob", allowed_tools=["Read", "Write", "Bash"]),
            AllowedUser(user_id=11111, username="charlie", allowed_tools=[]),  # all tools
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # Alice: only Read
        assert guard.check_tool(user_id=12345, username="alice", tool_name="Read")
        assert not guard.check_tool(user_id=12345, username="alice", tool_name="Write")
        assert not guard.check_tool(user_id=12345, username="alice", tool_name="Bash")

        # Bob: Read, Write, Bash
        assert guard.check_tool(user_id=67890, username="bob", tool_name="Read")
        assert guard.check_tool(user_id=67890, username="bob", tool_name="Write")
        assert guard.check_tool(user_id=67890, username="bob", tool_name="Bash")
        assert not guard.check_tool(user_id=67890, username="bob", tool_name="Edit")

        # Charlie: all tools
        assert guard.check_tool(user_id=11111, username="charlie", tool_name="Read")
        assert guard.check_tool(user_id=11111, username="charlie", tool_name="Write")
        assert guard.check_tool(user_id=11111, username="charlie", tool_name="Bash")
        assert guard.check_tool(user_id=11111, username="charlie", tool_name="Edit")

    @pytest.mark.parametrize("tool_name", ["Read", "Write", "Edit", "Bash", "Delete", "CustomTool"])
    def test_empty_allowed_tools_permits_any_tool_name(self, tool_name: str) -> None:
        """Empty allowed_tools should permit any tool name."""
        allowed = [AllowedUser(user_id=12345, username="alice", allowed_tools=[])]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert guard.check_tool(user_id=12345, username="alice", tool_name=tool_name)


class TestTelegramAuthGuardWritablePaths:
    """Test check_writable method for write/edit permissions."""

    def test_empty_writable_paths_permits_all_paths(self) -> None:
        """When writable_paths is empty, all paths should be writable."""
        allowed = [AllowedUser(user_id=12345, username="alice", writable_paths=[])]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert guard.check_writable(user_id=12345, username="alice", file_path="/home/user/file.txt")
        assert guard.check_writable(user_id=12345, username="alice", file_path="/etc/config.yaml")
        assert guard.check_writable(user_id=12345, username="alice", file_path="src/main.py")

    def test_specific_writable_paths_restricts_access(self) -> None:
        """When writable_paths is specified, only matching paths should be writable."""
        allowed = [
            AllowedUser(user_id=12345, username="alice", writable_paths=["*.py", "docs/*.md"])
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # Allowed patterns
        assert guard.check_writable(user_id=12345, username="alice", file_path="test.py")
        assert guard.check_writable(user_id=12345, username="alice", file_path="main.py")
        assert guard.check_writable(user_id=12345, username="alice", file_path="docs/README.md")

        # Disallowed patterns
        assert not guard.check_writable(user_id=12345, username="alice", file_path="test.txt")
        assert not guard.check_writable(user_id=12345, username="alice", file_path="config.yaml")
        assert not guard.check_writable(user_id=12345, username="alice", file_path="src/test.js")

    def test_glob_patterns_for_writable_paths(self) -> None:
        """Glob patterns should work correctly for writable paths."""
        allowed = [
            AllowedUser(user_id=12345, username="alice", writable_paths=["src/**", "*.txt"])
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # src/** pattern
        assert guard.check_writable(user_id=12345, username="alice", file_path="src/main.py")
        assert guard.check_writable(user_id=12345, username="alice", file_path="src/utils/helper.py")

        # *.txt pattern
        assert guard.check_writable(user_id=12345, username="alice", file_path="notes.txt")
        assert guard.check_writable(user_id=12345, username="alice", file_path="README.txt")

        # Not matching patterns
        assert not guard.check_writable(user_id=12345, username="alice", file_path="docs/guide.md")
        assert not guard.check_writable(user_id=12345, username="alice", file_path="test.py")

    def test_prefix_matching_for_directories(self) -> None:
        """Directory prefix matching should work for writable paths."""
        allowed = [
            AllowedUser(user_id=12345, username="alice", writable_paths=["/home/alice/", "src/"])
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # /home/alice/ prefix
        assert guard.check_writable(user_id=12345, username="alice", file_path="/home/alice/file.txt")
        assert guard.check_writable(user_id=12345, username="alice", file_path="/home/alice/docs/readme.md")

        # src/ prefix
        assert guard.check_writable(user_id=12345, username="alice", file_path="src/main.py")
        assert guard.check_writable(user_id=12345, username="alice", file_path="src/utils/helper.py")

        # Not matching prefixes
        assert not guard.check_writable(user_id=12345, username="alice", file_path="/home/bob/file.txt")
        assert not guard.check_writable(user_id=12345, username="alice", file_path="tests/test_main.py")

    def test_user_not_found_with_restrictions_denies_write(self) -> None:
        """When restrictions exist but user not found, writes should be denied."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert not guard.check_writable(user_id=99999, username="bob", file_path="file.txt")

    def test_user_not_found_without_restrictions_allows_write(self) -> None:
        """When no restrictions exist, writes should be allowed."""
        guard = TelegramAuthGuard(allowed_users=[])

        assert guard.check_writable(user_id=12345, username="alice", file_path="file.txt")

    def test_none_username_with_restrictions_denies_write(self) -> None:
        """When username is None and restrictions exist, writes should be denied."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert not guard.check_writable(user_id=12345, username=None, file_path="file.txt")

    def test_none_username_without_restrictions_allows_write(self) -> None:
        """When username is None and no restrictions, writes should be allowed."""
        guard = TelegramAuthGuard(allowed_users=[])

        assert guard.check_writable(user_id=12345, username=None, file_path="file.txt")

    def test_different_users_different_writable_paths(self) -> None:
        """Different users can have different writable path permissions."""
        allowed = [
            AllowedUser(user_id=12345, username="alice", writable_paths=["*.py"]),
            AllowedUser(user_id=67890, username="bob", writable_paths=["docs/"]),
            AllowedUser(user_id=11111, username="charlie", writable_paths=[]),  # all paths
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # Alice: only *.py
        assert guard.check_writable(user_id=12345, username="alice", file_path="test.py")
        assert not guard.check_writable(user_id=12345, username="alice", file_path="test.txt")

        # Bob: only docs/
        assert guard.check_writable(user_id=67890, username="bob", file_path="docs/readme.md")
        assert not guard.check_writable(user_id=67890, username="bob", file_path="test.py")

        # Charlie: all paths
        assert guard.check_writable(user_id=11111, username="charlie", file_path="test.py")
        assert guard.check_writable(user_id=11111, username="charlie", file_path="test.txt")
        assert guard.check_writable(user_id=11111, username="charlie", file_path="docs/readme.md")


class TestTelegramAuthGuardReadablePaths:
    """Test check_readable method for read permissions."""

    def test_empty_readable_paths_permits_all_paths(self) -> None:
        """When readable_paths is empty, all paths should be readable."""
        allowed = [AllowedUser(user_id=12345, username="alice", readable_paths=[])]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert guard.check_readable(user_id=12345, username="alice", file_path="/home/user/file.txt")
        assert guard.check_readable(user_id=12345, username="alice", file_path="/etc/config.yaml")
        assert guard.check_readable(user_id=12345, username="alice", file_path="src/main.py")

    def test_specific_readable_paths_restricts_access(self) -> None:
        """When readable_paths is specified, only matching paths should be readable."""
        allowed = [
            AllowedUser(user_id=12345, username="alice", readable_paths=["*.py", "docs/*.md"])
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # Allowed patterns
        assert guard.check_readable(user_id=12345, username="alice", file_path="test.py")
        assert guard.check_readable(user_id=12345, username="alice", file_path="main.py")
        assert guard.check_readable(user_id=12345, username="alice", file_path="docs/README.md")

        # Disallowed patterns
        assert not guard.check_readable(user_id=12345, username="alice", file_path="test.txt")
        assert not guard.check_readable(user_id=12345, username="alice", file_path="config.yaml")
        assert not guard.check_readable(user_id=12345, username="alice", file_path="src/test.js")

    def test_glob_patterns_for_readable_paths(self) -> None:
        """Glob patterns should work correctly for readable paths."""
        allowed = [
            AllowedUser(user_id=12345, username="alice", readable_paths=["src/**", "*.txt"])
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # src/** pattern
        assert guard.check_readable(user_id=12345, username="alice", file_path="src/main.py")
        assert guard.check_readable(user_id=12345, username="alice", file_path="src/utils/helper.py")

        # *.txt pattern
        assert guard.check_readable(user_id=12345, username="alice", file_path="notes.txt")
        assert guard.check_readable(user_id=12345, username="alice", file_path="README.txt")

        # Not matching patterns
        assert not guard.check_readable(user_id=12345, username="alice", file_path="docs/guide.md")
        assert not guard.check_readable(user_id=12345, username="alice", file_path="test.py")

    def test_prefix_matching_for_directories(self) -> None:
        """Directory prefix matching should work for readable paths."""
        allowed = [
            AllowedUser(user_id=12345, username="alice", readable_paths=["/home/alice/", "src/"])
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # /home/alice/ prefix
        assert guard.check_readable(user_id=12345, username="alice", file_path="/home/alice/file.txt")
        assert guard.check_readable(user_id=12345, username="alice", file_path="/home/alice/docs/readme.md")

        # src/ prefix
        assert guard.check_readable(user_id=12345, username="alice", file_path="src/main.py")
        assert guard.check_readable(user_id=12345, username="alice", file_path="src/utils/helper.py")

        # Not matching prefixes
        assert not guard.check_readable(user_id=12345, username="alice", file_path="/home/bob/file.txt")
        assert not guard.check_readable(user_id=12345, username="alice", file_path="tests/test_main.py")

    def test_user_not_found_with_restrictions_denies_read(self) -> None:
        """When restrictions exist but user not found, reads should be denied."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert not guard.check_readable(user_id=99999, username="bob", file_path="file.txt")

    def test_user_not_found_without_restrictions_allows_read(self) -> None:
        """When no restrictions exist, reads should be allowed."""
        guard = TelegramAuthGuard(allowed_users=[])

        assert guard.check_readable(user_id=12345, username="alice", file_path="file.txt")

    def test_none_username_with_restrictions_denies_read(self) -> None:
        """When username is None and restrictions exist, reads should be denied."""
        allowed = [AllowedUser(user_id=12345, username="alice")]
        guard = TelegramAuthGuard(allowed_users=allowed)

        assert not guard.check_readable(user_id=12345, username=None, file_path="file.txt")

    def test_none_username_without_restrictions_allows_read(self) -> None:
        """When username is None and no restrictions, reads should be allowed."""
        guard = TelegramAuthGuard(allowed_users=[])

        assert guard.check_readable(user_id=12345, username=None, file_path="file.txt")

    def test_different_users_different_readable_paths(self) -> None:
        """Different users can have different readable path permissions."""
        allowed = [
            AllowedUser(user_id=12345, username="alice", readable_paths=["*.py"]),
            AllowedUser(user_id=67890, username="bob", readable_paths=["docs/"]),
            AllowedUser(user_id=11111, username="charlie", readable_paths=[]),  # all paths
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # Alice: only *.py
        assert guard.check_readable(user_id=12345, username="alice", file_path="test.py")
        assert not guard.check_readable(user_id=12345, username="alice", file_path="test.txt")

        # Bob: only docs/
        assert guard.check_readable(user_id=67890, username="bob", file_path="docs/readme.md")
        assert not guard.check_readable(user_id=67890, username="bob", file_path="test.py")

        # Charlie: all paths
        assert guard.check_readable(user_id=11111, username="charlie", file_path="test.py")
        assert guard.check_readable(user_id=11111, username="charlie", file_path="test.txt")
        assert guard.check_readable(user_id=11111, username="charlie", file_path="docs/readme.md")

    def test_readable_and_writable_paths_can_differ(self) -> None:
        """Users can have different readable and writable path permissions."""
        allowed = [
            AllowedUser(
                user_id=12345,
                username="alice",
                readable_paths=["*.py", "*.txt", "docs/"],
                writable_paths=["*.txt"]
            )
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # Can read .py but not write
        assert guard.check_readable(user_id=12345, username="alice", file_path="test.py")
        assert not guard.check_writable(user_id=12345, username="alice", file_path="test.py")

        # Can read and write .txt
        assert guard.check_readable(user_id=12345, username="alice", file_path="notes.txt")
        assert guard.check_writable(user_id=12345, username="alice", file_path="notes.txt")

        # Can read docs/ but not write
        assert guard.check_readable(user_id=12345, username="alice", file_path="docs/readme.md")
        assert not guard.check_writable(user_id=12345, username="alice", file_path="docs/readme.md")


class TestMatchAnyHelper:
    """Test the _match_any helper function for path matching."""

    def test_basename_pattern_matching(self) -> None:
        """Basename patterns like *.py should match files."""
        assert _match_any("test.py", ["*.py"])
        assert _match_any("main.py", ["*.py"])
        assert _match_any("/home/user/test.py", ["*.py"])
        assert not _match_any("test.txt", ["*.py"])

    def test_multiple_patterns(self) -> None:
        """Should match if any pattern matches."""
        patterns = ["*.py", "*.txt", "*.md"]
        assert _match_any("test.py", patterns)
        assert _match_any("notes.txt", patterns)
        assert _match_any("README.md", patterns)
        assert not _match_any("config.yaml", patterns)

    def test_glob_pattern_matching(self) -> None:
        """Glob patterns with ** should work."""
        assert _match_any("src/main.py", ["src/**"])
        assert _match_any("src/utils/helper.py", ["src/**"])
        assert not _match_any("tests/test.py", ["src/**"])

    def test_prefix_matching_for_directories(self) -> None:
        """Directory prefixes without wildcards should match."""
        assert _match_any("/home/alice/file.txt", ["/home/alice/"])
        assert _match_any("/home/alice/docs/readme.md", ["/home/alice/"])
        assert not _match_any("/home/bob/file.txt", ["/home/alice/"])

    def test_prefix_matching_relative_paths(self) -> None:
        """Relative directory prefixes should match."""
        assert _match_any("src/main.py", ["src/"])
        assert _match_any("src/utils/helper.py", ["src/"])
        assert not _match_any("tests/test.py", ["src/"])

    def test_no_match_returns_false(self) -> None:
        """Should return False when no patterns match."""
        patterns = ["*.py", "src/"]
        assert not _match_any("test.txt", patterns)
        assert not _match_any("docs/readme.md", patterns)

    def test_empty_patterns_returns_false(self) -> None:
        """Empty patterns list should return False."""
        assert not _match_any("test.py", [])
        assert not _match_any("/home/user/file.txt", [])

    def test_path_normalization(self) -> None:
        """Paths should be normalized before matching."""
        # Normalization should handle .. and .
        assert _match_any("./test.py", ["*.py"])
        assert _match_any("src/../test.py", ["*.py"])

    def test_tilde_expansion(self) -> None:
        """Tilde should be expanded in paths and patterns."""
        import os
        home = os.path.expanduser("~")
        assert _match_any(f"{home}/file.txt", ["~/"])
        assert _match_any("~/file.txt", ["~/"])

    def test_exact_match(self) -> None:
        """Exact path matching should work."""
        assert _match_any("test.py", ["test.py"])
        assert _match_any("/home/user/test.py", ["/home/user/test.py"])
        assert not _match_any("test.py", ["other.py"])

    def test_complex_glob_patterns(self) -> None:
        """Complex glob patterns should work."""
        assert _match_any("test_file.py", ["test_*.py"])
        assert _match_any("main.test.py", ["*.test.py"])
        assert not _match_any("main.py", ["test_*.py"])

    @pytest.mark.parametrize("file_path,pattern,expected", [
        ("test.py", "*.py", True),
        ("test.txt", "*.py", False),
        ("src/main.py", "src/", True),
        ("src/utils/helper.py", "src/", True),
        ("tests/test.py", "src/", False),
        ("/home/alice/file.txt", "/home/alice/", True),
        ("/home/bob/file.txt", "/home/alice/", False),
        ("docs/readme.md", "docs/**", True),
        ("docs/api/guide.md", "docs/**", True),
        ("readme.md", "docs/**", False),
    ])
    def test_match_any_parametrized(
        self, file_path: str, pattern: str, expected: bool
    ) -> None:
        """Parametrized tests for various path and pattern combinations."""
        assert _match_any(file_path, [pattern]) == expected


class TestTelegramAuthGuardIntegration:
    """Integration tests for multiple permissions combined."""

    def test_user_with_all_restrictions(self) -> None:
        """User with tool, writable, and readable restrictions."""
        allowed = [
            AllowedUser(
                user_id=12345,
                username="alice",
                allowed_tools=["Read"],
                writable_paths=["*.txt"],
                readable_paths=["*.py", "*.txt"]
            )
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # Basic auth
        assert guard.is_authorized(user_id=12345, username="alice")
        assert guard.has_restrictions

        # Tool permissions
        assert guard.check_tool(user_id=12345, username="alice", tool_name="Read")
        assert not guard.check_tool(user_id=12345, username="alice", tool_name="Write")

        # Path permissions
        assert guard.check_readable(user_id=12345, username="alice", file_path="test.py")
        assert guard.check_readable(user_id=12345, username="alice", file_path="notes.txt")
        assert not guard.check_readable(user_id=12345, username="alice", file_path="config.yaml")

        assert guard.check_writable(user_id=12345, username="alice", file_path="notes.txt")
        assert not guard.check_writable(user_id=12345, username="alice", file_path="test.py")

    def test_user_with_no_restrictions(self) -> None:
        """User with no restrictions (all empty lists)."""
        allowed = [
            AllowedUser(
                user_id=12345,
                username="alice",
                allowed_tools=[],
                writable_paths=[],
                readable_paths=[]
            )
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # Basic auth
        assert guard.is_authorized(user_id=12345, username="alice")

        # All tools allowed
        assert guard.check_tool(user_id=12345, username="alice", tool_name="Read")
        assert guard.check_tool(user_id=12345, username="alice", tool_name="Write")
        assert guard.check_tool(user_id=12345, username="alice", tool_name="Bash")

        # All paths allowed
        assert guard.check_readable(user_id=12345, username="alice", file_path="any/file.txt")
        assert guard.check_writable(user_id=12345, username="alice", file_path="any/file.txt")

    def test_multiple_users_with_mixed_permissions(self) -> None:
        """Multiple users with different permission levels."""
        allowed = [
            AllowedUser(
                user_id=12345,
                username="alice",
                allowed_tools=["Read"],
                readable_paths=["*.py"]
            ),
            AllowedUser(
                user_id=67890,
                username="bob",
                allowed_tools=["Read", "Write"],
                writable_paths=["docs/"],
                readable_paths=["**"]
            ),
            AllowedUser(
                user_id=11111,
                username="charlie",
                allowed_tools=[],
                writable_paths=[],
                readable_paths=[]
            ),
        ]
        guard = TelegramAuthGuard(allowed_users=allowed)

        # All authorized
        assert guard.is_authorized(user_id=12345, username="alice")
        assert guard.is_authorized(user_id=67890, username="bob")
        assert guard.is_authorized(user_id=11111, username="charlie")

        # Alice: limited
        assert guard.check_tool(user_id=12345, username="alice", tool_name="Read")
        assert not guard.check_tool(user_id=12345, username="alice", tool_name="Write")
        assert guard.check_readable(user_id=12345, username="alice", file_path="test.py")
        assert not guard.check_readable(user_id=12345, username="alice", file_path="test.txt")

        # Bob: more access
        assert guard.check_tool(user_id=67890, username="bob", tool_name="Read")
        assert guard.check_tool(user_id=67890, username="bob", tool_name="Write")
        assert guard.check_readable(user_id=67890, username="bob", file_path="any/file.txt")
        assert guard.check_writable(user_id=67890, username="bob", file_path="docs/readme.md")
        assert not guard.check_writable(user_id=67890, username="bob", file_path="src/main.py")

        # Charlie: full access
        assert guard.check_tool(user_id=11111, username="charlie", tool_name="Read")
        assert guard.check_tool(user_id=11111, username="charlie", tool_name="Write")
        assert guard.check_tool(user_id=11111, username="charlie", tool_name="Bash")
        assert guard.check_readable(user_id=11111, username="charlie", file_path="any/file.txt")
        assert guard.check_writable(user_id=11111, username="charlie", file_path="any/file.txt")
