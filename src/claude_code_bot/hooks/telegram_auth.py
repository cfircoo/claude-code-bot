"""Telegram auth guard — blocks unauthorized users and enforces per-user permissions."""

from __future__ import annotations

import fnmatch
import os
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from claude_code_bot.config import AllowedUser

logger = structlog.get_logger()


class TelegramAuthGuard:
    """Checks Telegram user_id + username against an allow-list.

    Per-user restrictions:
    - allowed_tools: which SDK tools the user can trigger (empty = all)
    - writable_paths: glob patterns for files the user can write/edit (empty = all)
    - readable_paths: glob patterns for files the user can read (empty = all)
    """

    def __init__(
        self,
        allowed_users: list[AllowedUser],
        deny_message: str = "You are not authorized to use this bot.",
    ) -> None:
        self._users: dict[tuple[int, str], AllowedUser] = {
            (u.user_id, u.username): u for u in allowed_users
        }
        self.deny_message = deny_message

    @property
    def has_restrictions(self) -> bool:
        return len(self._users) > 0

    def is_authorized(self, user_id: int, username: str | None) -> bool:
        """Check if a user is authorized to use the bot."""
        if not self._users:
            return True
        if username is None:
            return False
        return (user_id, username) in self._users

    def get_user(self, user_id: int, username: str | None) -> AllowedUser | None:
        """Get the AllowedUser config for a user, or None."""
        if username is None:
            return None
        return self._users.get((user_id, username))

    def check_tool(self, user_id: int, username: str | None, tool_name: str) -> bool:
        """Check if user is allowed to use a specific tool. True = allowed."""
        user = self.get_user(user_id, username)
        if user is None:
            return not self._users  # no restrictions = allow
        if not user.allowed_tools:
            return True  # empty = all tools allowed
        return tool_name in user.allowed_tools

    def check_writable(self, user_id: int, username: str | None, file_path: str) -> bool:
        """Check if user can write/edit to a file path. True = allowed."""
        user = self.get_user(user_id, username)
        if user is None:
            return not self._users
        if not user.writable_paths:
            return True  # empty = all paths writable
        return _match_any(file_path, user.writable_paths)

    def check_readable(self, user_id: int, username: str | None, file_path: str) -> bool:
        """Check if user can read a file path. True = allowed."""
        user = self.get_user(user_id, username)
        if user is None:
            return not self._users
        if not user.readable_paths:
            return True  # empty = all paths readable
        return _match_any(file_path, user.readable_paths)


def _match_any(file_path: str, patterns: list[str]) -> bool:
    """Check if file_path matches any of the glob patterns."""
    normalized = os.path.normpath(file_path)
    basename = os.path.basename(normalized)
    expanded = os.path.expanduser(normalized)
    for pat in patterns:
        exp_pat = os.path.expanduser(pat)
        # Match against basename (e.g. "*.py") or full path (e.g. "src/**")
        if fnmatch.fnmatch(basename, pat):
            return True
        if fnmatch.fnmatch(expanded, exp_pat):
            return True
        # Prefix match for directories (e.g. "src/")
        if not any(c in pat for c in "*?[") and expanded.startswith(exp_pat):
            return True
    return False
