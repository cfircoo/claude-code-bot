"""Tests for FastAPI application endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from claude_code_bot import app as app_module
from claude_code_bot.app import app
from claude_code_bot.memory import ConversationStore


@pytest.fixture
def store(tmp_path) -> ConversationStore:
    return ConversationStore(path=str(tmp_path / "conv"))


@pytest.fixture
def setup_app(store):
    """Set up app module globals for testing without lifespan."""
    from claude_code_bot.config import BotConfig
    from claude_code_bot.permissions import PermissionManager

    config = BotConfig()
    pm = PermissionManager()
    mock_agent = MagicMock()

    # Patch module-level globals
    app_module._config = config
    app_module._store = store
    app_module._agent_service = mock_agent
    app_module._permission_manager = pm
    app_module._telegram = None

    yield config, mock_agent, pm

    # Cleanup
    app_module._config = None
    app_module._store = None
    app_module._agent_service = None
    app_module._permission_manager = None
    app_module._telegram = None


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_health(client) -> None:
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_chat_stream_empty_message(client, setup_app) -> None:
    resp = await client.post("/chat/stream", json={"user_id": "u1", "message": "  "})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_chat_stream_unauthorized(client, setup_app) -> None:
    config, _, _ = setup_app
    from claude_code_bot.config import ChannelConfig
    config.channels = [ChannelConfig(type="http", settings={"api_key": "secret"})]

    resp = await client.post(
        "/chat/stream",
        json={"user_id": "u1", "message": "hi"},
        headers={"X-API-Key": "wrong"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_chat_stream_success(client, setup_app) -> None:
    _, mock_agent, _ = setup_app

    async def fake_stream(user_id, message, conversation_id=None):
        yield {"type": "text", "content": "hello"}
        yield {"type": "result", "session_id": "s1"}

    mock_agent.chat_stream = fake_stream

    resp = await client.post("/chat/stream", json={"user_id": "u1", "message": "hi"})
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_chat_stream_not_initialized(client) -> None:
    """When agent_service is None, should return 503."""
    app_module._agent_service = None
    app_module._config = None
    resp = await client.post("/chat/stream", json={"user_id": "u1", "message": "hi"})
    assert resp.status_code == 503
    app_module._config = None


@pytest.mark.asyncio
async def test_list_conversations(client, setup_app, store) -> None:
    store.create("u1", "Test Conv")
    resp = await client.get("/conversations/u1")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test Conv"


@pytest.mark.asyncio
async def test_create_conversation(client, setup_app) -> None:
    resp = await client.post("/conversations/u1", json={"name": "New Conv"})
    assert resp.status_code == 201
    assert resp.json()["name"] == "New Conv"


@pytest.mark.asyncio
async def test_create_conversation_no_body(client, setup_app) -> None:
    resp = await client.post("/conversations/u1")
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_delete_conversation(client, setup_app, store) -> None:
    c = store.create("u1", "ToDelete")
    resp = await client.delete(f"/conversations/u1/{c.conversation_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"


@pytest.mark.asyncio
async def test_delete_conversation_not_found(client, setup_app) -> None:
    resp = await client.delete("/conversations/u1/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_resolve_permission(client, setup_app) -> None:
    _, _, pm = setup_app
    import asyncio
    event = asyncio.Event()
    pm._pending["req-1"] = (event, None)

    resp = await client.post("/permissions/req-1", json={"approved": True})
    assert resp.status_code == 200
    assert resp.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_resolve_permission_not_found(client, setup_app) -> None:
    resp = await client.post("/permissions/nonexistent", json={"approved": True})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_proactive_no_telegram(client, setup_app) -> None:
    resp = await client.post("/proactive?user_id=u1&message=hi")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_proactive_with_telegram(client, setup_app) -> None:
    mock_tg = AsyncMock()
    app_module._telegram = mock_tg
    resp = await client.post("/proactive?user_id=u1&message=hi")
    assert resp.status_code == 200
    mock_tg.send_proactive_message.assert_called_once_with("u1", "hi")
    app_module._telegram = None


@pytest.mark.asyncio
async def test_conversations_store_not_initialized(client) -> None:
    """When store is None, conversation endpoints should return 503."""
    app_module._store = None
    app_module._config = None
    resp = await client.get("/conversations/u1")
    assert resp.status_code == 503
    app_module._store = None


@pytest.mark.asyncio
async def test_list_conversations_store_not_init(client) -> None:
    """Store=None on create conversation should 503."""
    app_module._store = None
    app_module._config = None
    resp = await client.post("/conversations/u1", json={"name": "X"})
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_delete_conversation_store_not_init(client) -> None:
    app_module._store = None
    app_module._config = None
    resp = await client.delete("/conversations/u1/abc")
    assert resp.status_code == 503


def test_get_http_api_key_no_config() -> None:
    app_module._config = None
    from claude_code_bot.app import _get_http_api_key
    assert _get_http_api_key() is None
    app_module._config = None


def test_get_http_api_key_with_http_channel() -> None:
    from claude_code_bot.config import BotConfig, ChannelConfig
    from claude_code_bot.app import _get_http_api_key
    app_module._config = BotConfig(channels=[ChannelConfig(type="http", settings={"api_key": "mykey"})])
    assert _get_http_api_key() == "mykey"
    app_module._config = None


def test_get_http_api_key_no_http_channel() -> None:
    from claude_code_bot.config import BotConfig, ChannelConfig
    from claude_code_bot.app import _get_http_api_key
    app_module._config = BotConfig(channels=[ChannelConfig(type="telegram", settings={})])
    assert _get_http_api_key() is None
    app_module._config = None


def test_has_channel() -> None:
    from claude_code_bot.config import BotConfig, ChannelConfig
    from claude_code_bot.app import _has_channel
    app_module._config = BotConfig(channels=[ChannelConfig(type="telegram")])
    assert _has_channel("telegram") is True
    assert _has_channel("http") is False
    app_module._config = None


def test_has_channel_no_config() -> None:
    from claude_code_bot.app import _has_channel
    app_module._config = None
    assert _has_channel("telegram") is False


@pytest.mark.asyncio
async def test_lifespan_startup_shutdown(tmp_path) -> None:
    """Test lifespan context manager with a minimal config."""
    import yaml
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump({"persona": {"name": "Test"}}))

    with patch.dict("os.environ", {"CONFIG_PATH": str(config_path)}):
        with patch("claude_code_bot.app.TelegramChannel"):
            async with app_module.lifespan(app):
                assert app_module._agent_service is not None
                assert app_module._config is not None
                assert app_module._store is not None

    # Cleanup
    app_module._agent_service = None
    app_module._config = None
    app_module._store = None
    app_module._permission_manager = None
    app_module._telegram = None


@pytest.mark.asyncio
async def test_lifespan_missing_config() -> None:
    """Missing config should use defaults."""
    with patch.dict("os.environ", {"CONFIG_PATH": "/nonexistent/config.yaml"}):
        with patch("claude_code_bot.app.TelegramChannel"):
            async with app_module.lifespan(app):
                assert app_module._config is not None
                assert app_module._config.persona.name == "Assistant"

    app_module._agent_service = None
    app_module._config = None
    app_module._store = None
    app_module._permission_manager = None
    app_module._telegram = None


@pytest.mark.asyncio
async def test_lifespan_with_telegram(tmp_path) -> None:
    """Lifespan with telegram channel configured should start polling."""
    import yaml
    config_path = tmp_path / "config.yaml"
    config_path.write_text(yaml.dump({
        "channels": [{"type": "telegram", "settings": {"show_tool_activity": True, "thinking_threshold": 5}}],
        "api_keys": {"telegram_bot_token": "123:ABC"},
    }))

    mock_tg = MagicMock()
    mock_tg.start_polling = AsyncMock()
    mock_tg.stop = AsyncMock()
    mock_tg.set_permission_manager = MagicMock()
    mock_tg.set_agent_service = MagicMock()

    with patch.dict("os.environ", {"CONFIG_PATH": str(config_path)}):
        with patch("claude_code_bot.app.TelegramChannel", return_value=mock_tg):
            async with app_module.lifespan(app):
                assert app_module._telegram is mock_tg
                mock_tg.set_agent_service.assert_called_once()

    app_module._agent_service = None
    app_module._config = None
    app_module._store = None
    app_module._permission_manager = None
    app_module._telegram = None


@pytest.mark.asyncio
async def test_permission_manager_not_initialized(client) -> None:
    """When permission_manager is None, should return 503."""
    app_module._permission_manager = None
    app_module._config = None
    resp = await client.post("/permissions/req-1", json={"approved": True})
    assert resp.status_code == 503
    app_module._permission_manager = None
