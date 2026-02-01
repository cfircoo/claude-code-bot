"""Tests for PermissionManager interactive tool permissions."""

from __future__ import annotations

import asyncio

import pytest

from claude_code_bot.permissions import PermissionManager, _summarize_input


def test_summarize_bash_command() -> None:
    summary = _summarize_input("Bash", {"command": "ls -la"})
    assert summary == "Run command: ls -la"


def test_summarize_write_file() -> None:
    summary = _summarize_input("Write", {"file_path": "/tmp/test.txt", "content": "hi"})
    assert summary == "Write file: /tmp/test.txt"


def test_summarize_edit_file() -> None:
    summary = _summarize_input("Edit", {"file_path": "/tmp/test.txt"})
    assert summary == "Edit file: /tmp/test.txt"


def test_summarize_generic() -> None:
    summary = _summarize_input("CustomTool", {"a": 1, "b": 2})
    assert summary == "CustomTool(a, b)"


def test_tools_requiring_approval_default() -> None:
    pm = PermissionManager()
    assert pm.tools_requiring_approval == ["Bash"]


def test_tools_requiring_approval_custom() -> None:
    pm = PermissionManager(tools_requiring_approval=["Bash", "Write"])
    assert "Write" in pm.tools_requiring_approval


@pytest.mark.asyncio
async def test_allowed_tool_auto_approved() -> None:
    """Tools not in the approval list should be auto-allowed."""
    from claude_agent_sdk.types import PermissionResultAllow, ToolPermissionContext

    pm = PermissionManager(tools_requiring_approval=["Bash"])
    callback = pm.make_callback()
    result = await callback("Read", {"file_path": "/tmp/x"}, ToolPermissionContext())
    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_approval_flow_approved() -> None:
    """When notifier is called and resolve(True) is called, should return Allow."""
    from claude_agent_sdk.types import PermissionResultAllow, ToolPermissionContext

    pm = PermissionManager(tools_requiring_approval=["Bash"], timeout=5.0)

    notified: list[tuple[str, str, str]] = []

    async def fake_notifier(request_id: str, tool_name: str, summary: str) -> None:
        notified.append((request_id, tool_name, summary))
        # Simulate user approving after a short delay
        asyncio.get_event_loop().call_later(0.1, pm.resolve, request_id, True)

    pm.set_notifier(fake_notifier)
    callback = pm.make_callback()
    result = await callback("Bash", {"command": "ls"}, ToolPermissionContext())
    assert isinstance(result, PermissionResultAllow)
    assert len(notified) == 1
    assert notified[0][1] == "Bash"


@pytest.mark.asyncio
async def test_approval_flow_denied() -> None:
    """When resolve(False) is called, should return Deny."""
    from claude_agent_sdk.types import PermissionResultDeny, ToolPermissionContext

    pm = PermissionManager(tools_requiring_approval=["Bash"], timeout=5.0)

    async def fake_notifier(request_id: str, tool_name: str, summary: str) -> None:
        asyncio.get_event_loop().call_later(0.1, pm.resolve, request_id, False)

    pm.set_notifier(fake_notifier)
    callback = pm.make_callback()
    result = await callback("Bash", {"command": "rm -rf /"}, ToolPermissionContext())
    assert isinstance(result, PermissionResultDeny)


@pytest.mark.asyncio
async def test_timeout_denies() -> None:
    """If no response within timeout, should deny."""
    from claude_agent_sdk.types import PermissionResultDeny, ToolPermissionContext

    pm = PermissionManager(tools_requiring_approval=["Bash"], timeout=0.1)

    async def noop_notifier(request_id: str, tool_name: str, summary: str) -> None:
        pass  # Don't resolve — let it timeout

    pm.set_notifier(noop_notifier)
    callback = pm.make_callback()
    result = await callback("Bash", {"command": "ls"}, ToolPermissionContext())
    assert isinstance(result, PermissionResultDeny)


def test_resolve_unknown_request() -> None:
    pm = PermissionManager()
    assert pm.resolve("nonexistent-id", True) is False


@pytest.mark.asyncio
async def test_no_notifier_denies() -> None:
    """Without a notifier set, should deny."""
    from claude_agent_sdk.types import PermissionResultDeny, ToolPermissionContext

    pm = PermissionManager(tools_requiring_approval=["Bash"])
    callback = pm.make_callback()
    result = await callback("Bash", {"command": "ls"}, ToolPermissionContext())
    assert isinstance(result, PermissionResultDeny)
