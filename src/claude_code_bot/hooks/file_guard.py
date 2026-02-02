"""File guard hook — blocks Write/Edit to protected file patterns."""

from __future__ import annotations

import fnmatch
import os
from typing import Any

import structlog

logger = structlog.get_logger()


def _match_path(file_path: str, pattern: str) -> bool:
    """Match file path against pattern (glob or prefix)."""
    is_glob = any(c in pattern for c in "*?[")
    normalized = os.path.normpath(file_path)
    expanded = os.path.expanduser(normalized)

    if is_glob:
        basename = os.path.basename(expanded).lower()
        pat_lower = pattern.lower()
        exp_pat_lower = os.path.expanduser(pattern).lower()
        return (
            fnmatch.fnmatch(basename, pat_lower)
            or fnmatch.fnmatch(basename, exp_pat_lower)
            or fnmatch.fnmatch(expanded.lower(), exp_pat_lower)
        )
    else:
        exp_pattern = os.path.expanduser(pattern)
        return expanded.startswith(exp_pattern) or expanded == exp_pattern.rstrip("/")


def make_file_guard(patterns: list[str]) -> Any:
    """Create a PreToolUse callback that blocks Write/Edit to matching files."""

    async def file_guard(input_data: dict, _tool_use_id: str | None, _ctx: Any) -> dict:
        file_path = input_data.get("tool_input", {}).get("file_path", "")
        if not file_path:
            return {}
        for pat in patterns:
            if _match_path(file_path, pat):
                logger.info("hook_file_guard_blocked", file_path=file_path, pattern=pat)
                return {
                    "hookSpecificOutput": {
                        "hookEventName": input_data["hook_event_name"],
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"File guard: {pat} blocks {file_path}",
                    }
                }
        return {}

    file_guard.__name__ = f"file_guard({', '.join(patterns)})"
    return file_guard
