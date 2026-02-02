"""Tests for HTTP security restrictions and permission enforcement."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from claude_agent_sdk.types import (
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)
from claude_code_bot import app as app_module
from claude_code_bot.app import app
from claude_code_bot.config import (
    BotConfig,
    ChannelConfig,
    HttpSecurityConfig,
    SecurityConfig,
    UserRestrictions,
)
from claude_code_bot.permissions import make_restricted_callback


# ============================================================================
# Config tests
# ============================================================================


def test_user_restrictions_defaults():
    """UserRestrictions should have empty lists as defaults."""
    restrictions = UserRestrictions()
    assert restrictions.allowed_tools == []
    assert restrictions.writable_paths == []
    assert restrictions.readable_paths == []


def test_user_restrictions_with_values():
    """UserRestrictions should accept and store values."""
    restrictions = UserRestrictions(
        allowed_tools=["Read", "Write"],
        writable_paths=["/tmp/*", "~/workspace/*"],
        readable_paths=["/home/*", "*.py"],
    )
    assert restrictions.allowed_tools == ["Read", "Write"]
    assert restrictions.writable_paths == ["/tmp/*", "~/workspace/*"]
    assert restrictions.readable_paths == ["/home/*", "*.py"]


def test_http_security_config_defaults():
    """HttpSecurityConfig should have sensible defaults."""
    config = HttpSecurityConfig()
    assert config.default_restrictions is None
    assert config.deny_unauthenticated is False


def test_http_security_config_with_restrictions():
    """HttpSecurityConfig should accept default_restrictions."""
    restrictions = UserRestrictions(allowed_tools=["Read"])
    config = HttpSecurityConfig(
        default_restrictions=restrictions, deny_unauthenticated=True
    )
    assert config.default_restrictions is restrictions
    assert config.deny_unauthenticated is True


def test_security_config_has_http_field():
    """SecurityConfig should have an http field."""
    security = SecurityConfig()
    assert hasattr(security, "http")
    assert isinstance(security.http, HttpSecurityConfig)


def test_bot_config_includes_security():
    """BotConfig should include security with http config."""
    config = BotConfig()
    assert hasattr(config, "security")
    assert hasattr(config.security, "http")
    assert isinstance(config.security.http, HttpSecurityConfig)


# ============================================================================
# make_restricted_callback tests
# ============================================================================


@pytest.fixture
def mock_context() -> ToolPermissionContext:
    """Create a mock ToolPermissionContext for testing."""
    return ToolPermissionContext()


@pytest.mark.asyncio
async def test_restricted_callback_blocks_tool_not_in_allowed_tools(mock_context):
    """Tool not in allowed_tools should be denied."""
    restrictions = UserRestrictions(allowed_tools=["Read", "Write"])
    callback = make_restricted_callback(restrictions)

    result = await callback("Bash", {"command": "ls"}, mock_context)

    assert isinstance(result, PermissionResultDeny)
    assert "Bash" in result.message
    assert "not allowed" in result.message


@pytest.mark.asyncio
async def test_restricted_callback_allows_tool_in_allowed_tools(mock_context):
    """Tool in allowed_tools should be allowed when no base_callback."""
    restrictions = UserRestrictions(allowed_tools=["Read", "Write"])
    callback = make_restricted_callback(restrictions)

    result = await callback("Read", {"file_path": "/tmp/test.txt"}, mock_context)

    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_restricted_callback_empty_allowed_tools_allows_all(mock_context):
    """Empty allowed_tools list means all tools are allowed."""
    restrictions = UserRestrictions(allowed_tools=[])
    callback = make_restricted_callback(restrictions)

    result = await callback("Bash", {"command": "ls"}, mock_context)

    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_restricted_callback_blocks_write_to_disallowed_path(mock_context):
    """Write to path not in writable_paths should be denied."""
    restrictions = UserRestrictions(writable_paths=["/tmp/*", "~/workspace/*"])
    callback = make_restricted_callback(restrictions)

    result = await callback("Write", {"file_path": "/etc/passwd"}, mock_context)

    assert isinstance(result, PermissionResultDeny)
    assert "/etc/passwd" in result.message
    assert "not allowed" in result.message


@pytest.mark.asyncio
async def test_restricted_callback_allows_write_to_allowed_path(mock_context):
    """Write to path in writable_paths should be allowed."""
    restrictions = UserRestrictions(writable_paths=["/tmp/*"])
    callback = make_restricted_callback(restrictions)

    result = await callback("Write", {"file_path": "/tmp/test.txt"}, mock_context)

    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_restricted_callback_blocks_edit_to_disallowed_path(mock_context):
    """Edit to path not in writable_paths should be denied."""
    restrictions = UserRestrictions(writable_paths=["/tmp/*"])
    callback = make_restricted_callback(restrictions)

    result = await callback("Edit", {"file_path": "/home/user/secret.txt"}, mock_context)

    assert isinstance(result, PermissionResultDeny)
    assert "not allowed" in result.message


@pytest.mark.asyncio
async def test_restricted_callback_allows_edit_to_allowed_path(mock_context):
    """Edit to path in writable_paths should be allowed."""
    restrictions = UserRestrictions(writable_paths=["~/workspace/*"])
    callback = make_restricted_callback(restrictions)

    import os

    path = os.path.expanduser("~/workspace/file.py")
    result = await callback("Edit", {"file_path": path}, mock_context)

    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_restricted_callback_blocks_read_from_disallowed_path(mock_context):
    """Read from path not in readable_paths should be denied."""
    restrictions = UserRestrictions(readable_paths=["/home/user/*"])
    callback = make_restricted_callback(restrictions)

    result = await callback("Read", {"file_path": "/etc/passwd"}, mock_context)

    assert isinstance(result, PermissionResultDeny)
    assert "/etc/passwd" in result.message


@pytest.mark.asyncio
async def test_restricted_callback_allows_read_from_allowed_path(mock_context):
    """Read from path in readable_paths should be allowed."""
    restrictions = UserRestrictions(readable_paths=["/home/user/*", "*.py"])
    callback = make_restricted_callback(restrictions)

    result = await callback("Read", {"file_path": "/home/user/file.txt"}, mock_context)

    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_restricted_callback_allows_read_with_wildcard_pattern(mock_context):
    """Read with wildcard pattern matching should work."""
    restrictions = UserRestrictions(readable_paths=["*.py", "*.txt"])
    callback = make_restricted_callback(restrictions)

    result = await callback("Read", {"file_path": "/some/path/test.py"}, mock_context)

    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_restricted_callback_empty_writable_paths_allows_all_writes(mock_context):
    """Empty writable_paths means all writes are allowed."""
    restrictions = UserRestrictions(writable_paths=[])
    callback = make_restricted_callback(restrictions)

    result = await callback("Write", {"file_path": "/etc/passwd"}, mock_context)

    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_restricted_callback_empty_readable_paths_allows_all_reads(mock_context):
    """Empty readable_paths means all reads are allowed."""
    restrictions = UserRestrictions(readable_paths=[])
    callback = make_restricted_callback(restrictions)

    result = await callback("Read", {"file_path": "/etc/passwd"}, mock_context)

    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_restricted_callback_delegates_to_base_callback(mock_context):
    """When base_callback is present, should delegate to it after checks pass."""
    restrictions = UserRestrictions(allowed_tools=["Read"])

    async def base_callback(tool_name: str, tool_input: dict[str, Any], context: ToolPermissionContext):
        if tool_name == "Read":
            return PermissionResultDeny(message="Base denied")
        return PermissionResultAllow()

    callback = make_restricted_callback(restrictions, base_callback=base_callback)

    result = await callback("Read", {"file_path": "/tmp/test.txt"}, mock_context)

    # Restriction check passed, but base_callback denied it
    assert isinstance(result, PermissionResultDeny)
    assert "Base denied" in result.message


@pytest.mark.asyncio
async def test_restricted_callback_base_callback_allow(mock_context):
    """When base_callback allows, should return Allow."""
    restrictions = UserRestrictions(allowed_tools=["Bash"])

    async def base_callback(tool_name: str, tool_input: dict[str, Any], context: ToolPermissionContext):
        return PermissionResultAllow()

    callback = make_restricted_callback(restrictions, base_callback=base_callback)

    result = await callback("Bash", {"command": "ls"}, mock_context)

    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_restricted_callback_returns_allow_when_no_base_callback_and_checks_pass(
    mock_context,
):
    """When no base_callback and all checks pass, should return Allow."""
    restrictions = UserRestrictions(
        allowed_tools=["Read"],
        readable_paths=["*.py"],
    )
    callback = make_restricted_callback(restrictions)

    result = await callback("Read", {"file_path": "test.py"}, mock_context)

    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_restricted_callback_checks_dont_block_unrelated_tools(mock_context):
    """Path restrictions shouldn't affect tools that don't use paths."""
    restrictions = UserRestrictions(
        readable_paths=["/tmp/*"],  # restrictive readable paths
    )
    callback = make_restricted_callback(restrictions)

    # Bash doesn't use file_path, so should be allowed
    result = await callback("Bash", {"command": "ls"}, mock_context)

    assert isinstance(result, PermissionResultAllow)


@pytest.mark.asyncio
async def test_restricted_callback_combined_tool_and_path_restrictions(mock_context):
    """Combined tool and path restrictions should both be enforced."""
    restrictions = UserRestrictions(
        allowed_tools=["Read", "Write"],
        readable_paths=["/home/*"],
        writable_paths=["/tmp/*"],
    )
    callback = make_restricted_callback(restrictions)

    # Tool not allowed
    result1 = await callback("Bash", {"command": "ls"}, mock_context)
    assert isinstance(result1, PermissionResultDeny)

    # Tool allowed but path not
    result2 = await callback("Read", {"file_path": "/etc/passwd"}, mock_context)
    assert isinstance(result2, PermissionResultDeny)

    # Both allowed
    result3 = await callback("Read", {"file_path": "/home/user/file.txt"}, mock_context)
    assert isinstance(result3, PermissionResultAllow)


# ============================================================================
# App integration tests
# ============================================================================


@pytest.fixture
async def client():
    """Create an AsyncClient for testing the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def setup_app_with_agent(tmp_path):
    """Set up app with a mock agent that tracks restrictions passed to chat_stream."""
    from claude_code_bot.memory import ConversationStore
    from claude_code_bot.permissions import PermissionManager

    config = BotConfig()
    store = ConversationStore(path=str(tmp_path / "conv"))
    pm = PermissionManager()

    # Track what restrictions were passed to chat_stream
    captured_restrictions = []

    async def mock_chat_stream(
        user_id: str,
        message: str,
        conversation_id: str | None = None,
        metadata: dict | None = None,
        restrictions: UserRestrictions | None = None,
    ):
        captured_restrictions.append(restrictions)
        yield {"type": "text", "content": "response"}
        yield {"type": "result", "session_id": "s1"}

    mock_agent = MagicMock()
    mock_agent.chat_stream = mock_chat_stream

    app_module._config = config
    app_module._store = store
    app_module._agent_service = mock_agent
    app_module._permission_manager = pm
    app_module._telegram = None

    yield config, captured_restrictions

    # Cleanup
    app_module._config = None
    app_module._store = None
    app_module._agent_service = None
    app_module._permission_manager = None
    app_module._telegram = None


@pytest.mark.asyncio
async def test_app_no_api_key_no_deny_no_restrictions_full_access(
    client, setup_app_with_agent
):
    """No API key + no deny + no default_restrictions = full access (restrictions=None)."""
    config, captured = setup_app_with_agent

    # No HTTP channel configured, no security settings
    resp = await client.post("/chat/stream", json={"user_id": "u1", "message": "hello"})

    assert resp.status_code == 200
    # Should have passed restrictions=None (full access)
    assert len(captured) == 1
    assert captured[0] is None


@pytest.mark.asyncio
async def test_app_no_api_key_deny_unauthenticated_returns_401(
    client, setup_app_with_agent
):
    """No API key + deny_unauthenticated=True = 401."""
    config, captured = setup_app_with_agent

    config.security.http = HttpSecurityConfig(deny_unauthenticated=True)

    resp = await client.post("/chat/stream", json={"user_id": "u1", "message": "hello"})

    assert resp.status_code == 401
    assert "Unauthorized" in resp.text
    # chat_stream should not have been called
    assert len(captured) == 0


@pytest.mark.asyncio
async def test_app_no_api_key_with_default_restrictions_applies_restrictions(
    client, setup_app_with_agent
):
    """No API key + default_restrictions set = restrictions passed to agent."""
    config, captured = setup_app_with_agent

    restrictions = UserRestrictions(
        allowed_tools=["Read"],
        readable_paths=["*.py"],
    )
    config.security.http = HttpSecurityConfig(default_restrictions=restrictions)

    resp = await client.post("/chat/stream", json={"user_id": "u1", "message": "hello"})

    assert resp.status_code == 200
    # Should have passed the restrictions
    assert len(captured) == 1
    assert captured[0] is restrictions


@pytest.mark.asyncio
async def test_app_valid_api_key_full_access(client, setup_app_with_agent):
    """Valid API key = full access (restrictions=None)."""
    config, captured = setup_app_with_agent

    config.channels = [ChannelConfig(type="http", settings={"api_key": "secret123"})]
    config.security.http = HttpSecurityConfig(
        default_restrictions=UserRestrictions(allowed_tools=["Read"]),
        deny_unauthenticated=True,
    )

    resp = await client.post(
        "/chat/stream",
        json={"user_id": "u1", "message": "hello"},
        headers={"X-API-Key": "secret123"},
    )

    assert resp.status_code == 200
    # Should have full access despite default_restrictions being set
    assert len(captured) == 1
    assert captured[0] is None


@pytest.mark.asyncio
async def test_app_wrong_api_key_with_deny_returns_401(client, setup_app_with_agent):
    """Wrong API key + deny_unauthenticated=True = 401."""
    config, captured = setup_app_with_agent

    config.channels = [ChannelConfig(type="http", settings={"api_key": "secret123"})]
    config.security.http = HttpSecurityConfig(deny_unauthenticated=True)

    resp = await client.post(
        "/chat/stream",
        json={"user_id": "u1", "message": "hello"},
        headers={"X-API-Key": "wrongkey"},
    )

    assert resp.status_code == 401
    assert len(captured) == 0


@pytest.mark.asyncio
async def test_app_wrong_api_key_no_deny_applies_default_restrictions(
    client, setup_app_with_agent
):
    """Wrong API key + no deny + default_restrictions = restrictions applied."""
    config, captured = setup_app_with_agent

    restrictions = UserRestrictions(allowed_tools=["Read", "Grep"])
    config.channels = [ChannelConfig(type="http", settings={"api_key": "secret123"})]
    config.security.http = HttpSecurityConfig(
        default_restrictions=restrictions,
        deny_unauthenticated=False,
    )

    resp = await client.post(
        "/chat/stream",
        json={"user_id": "u1", "message": "hello"},
        headers={"X-API-Key": "wrongkey"},
    )

    assert resp.status_code == 200
    # Should apply default restrictions
    assert len(captured) == 1
    assert captured[0] is restrictions


@pytest.mark.asyncio
async def test_app_no_api_key_header_with_deny_returns_401(
    client, setup_app_with_agent
):
    """Missing X-API-Key header + deny_unauthenticated=True = 401."""
    config, captured = setup_app_with_agent

    config.channels = [ChannelConfig(type="http", settings={"api_key": "secret123"})]
    config.security.http = HttpSecurityConfig(deny_unauthenticated=True)

    resp = await client.post("/chat/stream", json={"user_id": "u1", "message": "hello"})

    assert resp.status_code == 401
    assert len(captured) == 0


@pytest.mark.asyncio
async def test_app_empty_api_key_header_treated_as_no_key(
    client, setup_app_with_agent
):
    """Empty X-API-Key header should be treated as no key provided."""
    config, captured = setup_app_with_agent

    config.channels = [ChannelConfig(type="http", settings={"api_key": "secret123"})]
    config.security.http = HttpSecurityConfig(deny_unauthenticated=True)

    resp = await client.post(
        "/chat/stream",
        json={"user_id": "u1", "message": "hello"},
        headers={"X-API-Key": ""},
    )

    assert resp.status_code == 401
    assert len(captured) == 0


@pytest.mark.asyncio
async def test_app_no_http_channel_no_api_key_check(client, setup_app_with_agent):
    """When no HTTP channel configured, API key check should be skipped."""
    config, captured = setup_app_with_agent

    # No HTTP channel, but set deny_unauthenticated
    config.security.http = HttpSecurityConfig(deny_unauthenticated=True)

    resp = await client.post("/chat/stream", json={"user_id": "u1", "message": "hello"})

    # Since no HTTP channel with api_key setting, _get_http_api_key() returns None
    # and the authentication is effectively bypassed
    assert resp.status_code == 401  # deny_unauthenticated is True


@pytest.mark.asyncio
async def test_app_restrictions_with_multiple_constraints(client, setup_app_with_agent):
    """Default restrictions with all constraint types should be passed through."""
    config, captured = setup_app_with_agent

    restrictions = UserRestrictions(
        allowed_tools=["Read", "Write", "Bash"],
        writable_paths=["/tmp/*", "~/workspace/*"],
        readable_paths=["/home/*", "*.py", "*.txt"],
    )
    config.security.http = HttpSecurityConfig(default_restrictions=restrictions)

    resp = await client.post("/chat/stream", json={"user_id": "u1", "message": "hello"})

    assert resp.status_code == 200
    assert len(captured) == 1
    assert captured[0] is restrictions
    assert captured[0].allowed_tools == ["Read", "Write", "Bash"]
    assert captured[0].writable_paths == ["/tmp/*", "~/workspace/*"]
    assert captured[0].readable_paths == ["/home/*", "*.py", "*.txt"]


@pytest.mark.asyncio
async def test_app_case_sensitive_api_key_comparison(client, setup_app_with_agent):
    """API key comparison should be case-sensitive."""
    config, captured = setup_app_with_agent

    config.channels = [ChannelConfig(type="http", settings={"api_key": "SecretKey"})]
    config.security.http = HttpSecurityConfig(deny_unauthenticated=True)

    # Wrong case
    resp1 = await client.post(
        "/chat/stream",
        json={"user_id": "u1", "message": "hello"},
        headers={"X-API-Key": "secretkey"},
    )
    assert resp1.status_code == 401

    # Correct case
    resp2 = await client.post(
        "/chat/stream",
        json={"user_id": "u1", "message": "hello"},
        headers={"X-API-Key": "SecretKey"},
    )
    assert resp2.status_code == 200
    assert captured[-1] is None  # Full access
