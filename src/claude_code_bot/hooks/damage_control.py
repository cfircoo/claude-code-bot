"""Damage control hook — loads patterns.yaml and registers comprehensive security guards.

Replicates the damage-control hook system as native SDK hooks:
- bashToolPatterns: regex-based command blocking + ask patterns
- zeroAccessPaths: block ALL operations (read/write/edit) on sensitive files
- readOnlyPaths: block write/edit but allow reads
- noDeletePaths: block deletion but allow read/write/edit
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog
import yaml

from claude_code_bot.hooks.command_guard import make_command_ask, make_command_guard
from claude_code_bot.hooks.file_guard import _match_path

if TYPE_CHECKING:
    from claude_code_bot.hooks.manager import HookManager

logger = structlog.get_logger()

DEFAULT_PATTERNS_PATHS = [
    Path.home() / ".claude" / "hooks" / "damage-control" / "patterns.yaml",
    Path(".claude") / "hooks" / "damage-control" / "patterns.yaml",
]


def load_patterns(patterns_path: str | None = None) -> dict[str, Any]:
    """Load patterns from YAML file.

    Searches default locations if no path given.
    """
    if patterns_path:
        p = Path(patterns_path)
        if p.exists():
            with open(p) as f:
                return yaml.safe_load(f) or {}
        logger.warning("damage_control_patterns_not_found", path=patterns_path)
        return {}

    for candidate in DEFAULT_PATTERNS_PATHS:
        if candidate.exists():
            with open(candidate) as f:
                data = yaml.safe_load(f) or {}
            logger.info("damage_control_patterns_loaded", path=str(candidate))
            return data

    logger.warning("damage_control_no_patterns_found")
    return {}


def _make_read_guard(zero_access_paths: list[str]) -> Any:
    """Block Read tool on zero-access paths."""

    async def read_guard(input_data: dict, _tool_use_id: str | None, _ctx: Any) -> dict:
        file_path = input_data.get("tool_input", {}).get("file_path", "")
        if not file_path:
            return {}
        for zp in zero_access_paths:
            if _match_path(file_path, zp):
                logger.info("hook_damage_control_read_blocked", file_path=file_path, pattern=zp)
                return {
                    "hookSpecificOutput": {
                        "hookEventName": input_data["hook_event_name"],
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Zero-access path: {zp}",
                    }
                }
        return {}

    read_guard.__name__ = "damage_control(read)"
    return read_guard


def _make_write_edit_guard(
    zero_access_paths: list[str], read_only_paths: list[str]
) -> Any:
    """Block Write/Edit on zero-access and read-only paths."""

    async def write_edit_guard(input_data: dict, _tool_use_id: str | None, _ctx: Any) -> dict:
        file_path = input_data.get("tool_input", {}).get("file_path", "")
        if not file_path:
            return {}
        for zp in zero_access_paths:
            if _match_path(file_path, zp):
                logger.info("hook_damage_control_write_blocked", file_path=file_path, pattern=zp)
                return {
                    "hookSpecificOutput": {
                        "hookEventName": input_data["hook_event_name"],
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Zero-access path: {zp}",
                    }
                }
        for rp in read_only_paths:
            if _match_path(file_path, rp):
                logger.info("hook_damage_control_readonly_blocked", file_path=file_path, pattern=rp)
                return {
                    "hookSpecificOutput": {
                        "hookEventName": input_data["hook_event_name"],
                        "permissionDecision": "deny",
                        "permissionDecisionReason": f"Read-only path: {rp}",
                    }
                }
        return {}

    write_edit_guard.__name__ = "damage_control(write/edit)"
    return write_edit_guard


def _make_bash_path_guard(
    zero_access_paths: list[str],
    read_only_paths: list[str],
    no_delete_paths: list[str],
) -> Any:
    """Block Bash commands that touch protected paths."""

    # Modification patterns for read-only paths
    MODIFY_PATTERNS = [
        r">\s*{path}", r"\btee\s+.*{path}", r"\bsed\s+-i.*{path}",
        r"\bmv\s+.*\s+{path}", r"\bcp\s+.*\s+{path}",
        r"\bchmod\s+.*{path}", r"\bchown\s+.*{path}",
        r"\btruncate\s+.*{path}",
    ]
    DELETE_PATTERNS = [
        r"\brm\s+.*{path}", r"\bunlink\s+.*{path}",
        r"\brmdir\s+.*{path}", r"\bshred\s+.*{path}",
    ]

    def _is_glob(pattern: str) -> bool:
        return any(c in pattern for c in "*?[")

    def _check_path_in_command(command: str, path: str, patterns: list[str]) -> bool:
        if _is_glob(path):
            # Convert glob chars for regex
            regex_path = path.replace(".", r"\.").replace("*", r"[^\s/]*").replace("?", r"[^\s/]")
            for pt in patterns:
                prefix = pt.replace("{path}", "")
                try:
                    if re.search(prefix + regex_path, command, re.IGNORECASE):
                        return True
                except re.error:
                    continue
        else:
            expanded = os.path.expanduser(path)
            for pt in patterns:
                for p in [re.escape(expanded), re.escape(path)]:
                    try:
                        if re.search(pt.replace("{path}", p), command):
                            return True
                    except re.error:
                        continue
        return False

    async def bash_path_guard(input_data: dict, _tool_use_id: str | None, _ctx: Any) -> dict:
        command = input_data.get("tool_input", {}).get("command", "")
        if not command:
            return {}

        # Zero-access: block any mention in command
        for zp in zero_access_paths:
            if _is_glob(zp):
                regex_zp = zp.replace(".", r"\.").replace("*", r"[^\s/]*").replace("?", r"[^\s/]")
                try:
                    if re.search(regex_zp, command, re.IGNORECASE):
                        return _deny(input_data, f"Zero-access path: {zp}")
                except re.error:
                    continue
            else:
                expanded = os.path.expanduser(zp)
                if re.search(re.escape(expanded), command) or re.search(re.escape(zp), command):
                    return _deny(input_data, f"Zero-access path: {zp}")

        # Read-only: block modifications
        all_modify = MODIFY_PATTERNS + DELETE_PATTERNS
        for rp in read_only_paths:
            if _check_path_in_command(command, rp, all_modify):
                return _deny(input_data, f"Read-only path: {rp}")

        # No-delete: block deletions only
        for ndp in no_delete_paths:
            if _check_path_in_command(command, ndp, DELETE_PATTERNS):
                return _deny(input_data, f"No-delete path: {ndp}")

        return {}

    bash_path_guard.__name__ = "damage_control(bash/paths)"
    return bash_path_guard


def _deny(input_data: dict, reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": input_data["hook_event_name"],
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def register_damage_control(
    manager: HookManager, patterns_path: str | None = None
) -> None:
    """Load patterns.yaml and register all damage-control hooks on the manager."""
    config = load_patterns(patterns_path)
    if not config:
        return

    bash_patterns = config.get("bashToolPatterns", [])
    zero_access = config.get("zeroAccessPaths", [])
    read_only = config.get("readOnlyPaths", [])
    no_delete = config.get("noDeletePaths", [])

    # 1. Bash command patterns (block + ask)
    block_patterns = [p["pattern"] for p in bash_patterns if not p.get("ask")]
    ask_patterns = [p for p in bash_patterns if p.get("ask")]

    if block_patterns:
        cb = make_command_guard(block_patterns, use_regex=True)
        cb.__name__ = "damage_control(bash/commands)"
        manager.add("PreToolUse", cb, matcher="Bash")

    if ask_patterns:
        cb = make_command_ask(ask_patterns)
        cb.__name__ = "damage_control(bash/ask)"
        manager.add("PreToolUse", cb, matcher="Bash")

    # 2. Bash path guards (zero-access, read-only, no-delete)
    if zero_access or read_only or no_delete:
        manager.add(
            "PreToolUse",
            _make_bash_path_guard(zero_access, read_only, no_delete),
            matcher="Bash",
        )

    # 3. Read tool — block zero-access paths
    if zero_access:
        manager.add("PreToolUse", _make_read_guard(zero_access), matcher="Read")

    # 4. Write/Edit tool — block zero-access + read-only paths
    if zero_access or read_only:
        manager.add(
            "PreToolUse",
            _make_write_edit_guard(zero_access, read_only),
            matcher="Write|Edit",
        )
