"""Auto-approve hook — automatically approves specified tools."""

from __future__ import annotations

from typing import Any


def make_auto_approve(tools: list[str]) -> Any:
    """Create a PreToolUse callback that auto-approves the given tools."""

    async def auto_approve(input_data: dict, _tool_use_id: str | None, _ctx: Any) -> dict:
        return {
            "hookSpecificOutput": {
                "hookEventName": input_data["hook_event_name"],
                "permissionDecision": "allow",
                "permissionDecisionReason": "Auto-approved by hook",
            }
        }

    auto_approve.__name__ = f"auto_approve({', '.join(tools)})"
    return auto_approve
