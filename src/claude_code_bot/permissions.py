"""Interactive tool permission system using can_use_tool callback."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable
from uuid import uuid4

import structlog
from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

logger = structlog.get_logger()

# Type alias for the channel notifier callback
PermissionNotifier = Callable[[str, str, str], Awaitable[None]]
# PermissionNotifier(request_id, tool_name, input_summary) -> sends prompt to user


def _summarize_input(tool_name: str, tool_input: dict[str, Any]) -> str:
    """Create a human-readable summary of what the tool wants to do."""
    if tool_name == "Bash" and "command" in tool_input:
        return f"Run command: {tool_input['command']}"
    if tool_name == "Write" and "file_path" in tool_input:
        return f"Write file: {tool_input['file_path']}"
    if tool_name == "Edit" and "file_path" in tool_input:
        return f"Edit file: {tool_input['file_path']}"
    # Generic fallback
    keys = list(tool_input.keys())[:3]
    return f"{tool_name}({', '.join(keys)})"


class PermissionManager:
    """Manages interactive tool permission requests.

    Holds pending requests (request_id -> Event + result).
    The can_use_tool callback creates a request, notifies the channel,
    then awaits the Event. The channel handler sets the event.
    """

    def __init__(
        self,
        tools_requiring_approval: list[str] | None = None,
        timeout: float = 60.0,
    ) -> None:
        self.tools_requiring_approval = tools_requiring_approval or ["Bash"]
        self.timeout = timeout
        self._pending: dict[str, tuple[asyncio.Event, bool | None]] = {}
        self._notifier: PermissionNotifier | None = None

    def set_notifier(self, notifier: PermissionNotifier) -> None:
        """Set the callback that sends permission prompts to the user's channel."""
        self._notifier = notifier

    def resolve(self, request_id: str, approved: bool) -> bool:
        """Resolve a pending permission request. Returns True if found."""
        if request_id not in self._pending:
            return False
        event, _ = self._pending[request_id]
        self._pending[request_id] = (event, approved)
        event.set()
        return True

    async def _request_permission(
        self, tool_name: str, tool_input: dict[str, Any]
    ) -> bool:
        """Send a permission request and wait for response."""
        if self._notifier is None:
            logger.warning("permission_no_notifier", tool=tool_name)
            return False

        request_id = str(uuid4())
        event = asyncio.Event()
        self._pending[request_id] = (event, None)

        summary = _summarize_input(tool_name, tool_input)
        await self._notifier(request_id, tool_name, summary)

        try:
            await asyncio.wait_for(event.wait(), timeout=self.timeout)
        except asyncio.TimeoutError:
            logger.warning("permission_timeout", request_id=request_id, tool=tool_name)
            self._pending.pop(request_id, None)
            return False

        _, approved = self._pending.pop(request_id, (None, None))
        return approved is True

    def make_callback(
        self,
    ) -> Callable[
        [str, dict[str, Any], ToolPermissionContext],
        Awaitable[PermissionResultAllow | PermissionResultDeny],
    ]:
        """Create the can_use_tool callback for ClaudeAgentOptions."""

        async def can_use_tool(
            tool_name: str,
            tool_input: dict[str, Any],
            context: ToolPermissionContext,
        ) -> PermissionResultAllow | PermissionResultDeny:
            if tool_name not in self.tools_requiring_approval:
                return PermissionResultAllow()

            approved = await self._request_permission(tool_name, tool_input)
            if approved:
                return PermissionResultAllow()
            return PermissionResultDeny(message="User denied permission")

        return can_use_tool
