"""Audit logger hook — logs all tool calls via structlog or custom function."""

from __future__ import annotations

from typing import Any, Callable

import structlog

logger = structlog.get_logger()


def make_audit_hooks(
    log_fn: Callable[..., Any] | None = None,
) -> tuple[Any, Any]:
    """Create PreToolUse and PostToolUse audit callbacks.

    Returns:
        Tuple of (pre_hook, post_hook) callbacks.
    """

    async def audit_pre(input_data: dict, tool_use_id: str | None, _ctx: Any) -> dict:
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

    async def audit_post(input_data: dict, tool_use_id: str | None, _ctx: Any) -> dict:
        info = {
            "tool": input_data.get("tool_name", ""),
            "tool_use_id": tool_use_id,
        }
        if log_fn:
            log_fn("post_tool_use", **info)
        else:
            logger.info("hook_audit_post_tool", **info)
        return {}

    audit_pre.__name__ = "audit_logger(pre)"
    audit_post.__name__ = "audit_logger(post)"
    return audit_pre, audit_post
