"""Tests for POST /chat/stream SSE endpoint and conversation CRUD endpoints."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from claude_code_bot.app import app
from claude_code_bot.memory import ConversationMeta


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- SSE Streaming Endpoint Tests ---


async def _fake_chat_stream(user_id: str, message: str, conversation_id: str | None = None):
    """Fake async generator that yields test events."""
    yield {"type": "text", "content": "Hello"}
    yield {"type": "text", "content": " world"}
    yield {"type": "result", "content": "Hello world", "session_id": "sess-1"}


@pytest.mark.asyncio
async def test_chat_stream_returns_sse(client: AsyncClient) -> None:
    with patch("claude_code_bot.app._agent_service") as mock_svc:
        mock_svc.chat_stream = _fake_chat_stream
        response = await client.post(
            "/chat/stream",
            json={"user_id": "u1", "message": "hi"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    lines = response.text.strip().split("\n\n")
    events = [json.loads(line.removeprefix("data: ")) for line in lines]
    assert len(events) == 3
    assert events[0] == {"type": "text", "content": "Hello"}
    assert events[1] == {"type": "text", "content": " world"}
    assert events[2]["type"] == "result"
    assert events[2]["content"] == "Hello world"


@pytest.mark.asyncio
async def test_chat_stream_passes_conversation_id(client: AsyncClient) -> None:
    captured: dict = {}

    async def capturing_stream(user_id: str, message: str, conversation_id: str | None = None):
        captured["conversation_id"] = conversation_id
        yield {"type": "result", "content": "ok", "session_id": "s"}

    with patch("claude_code_bot.app._agent_service") as mock_svc:
        mock_svc.chat_stream = capturing_stream
        response = await client.post(
            "/chat/stream",
            json={"user_id": "u1", "message": "hi", "conversation_id": "conv-123"},
        )
    assert response.status_code == 200
    assert captured["conversation_id"] == "conv-123"


@pytest.mark.asyncio
async def test_chat_stream_empty_message(client: AsyncClient) -> None:
    response = await client.post(
        "/chat/stream",
        json={"user_id": "u1", "message": "   "},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_chat_stream_auth_rejected(client: AsyncClient) -> None:
    with patch("claude_code_bot.app._get_http_api_key", return_value="secret"):
        response = await client.post(
            "/chat/stream",
            json={"user_id": "u1", "message": "hi"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_stream_auth_accepted(client: AsyncClient) -> None:
    with (
        patch("claude_code_bot.app._get_http_api_key", return_value="secret"),
        patch("claude_code_bot.app._agent_service") as mock_svc,
    ):
        mock_svc.chat_stream = _fake_chat_stream
        response = await client.post(
            "/chat/stream",
            json={"user_id": "u1", "message": "hi"},
            headers={"X-API-Key": "secret"},
        )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_stream_not_initialized(client: AsyncClient) -> None:
    with patch("claude_code_bot.app._agent_service", None):
        response = await client.post(
            "/chat/stream",
            json={"user_id": "u1", "message": "hi"},
        )
    assert response.status_code == 503


# --- Conversation CRUD Endpoint Tests ---


@pytest.mark.asyncio
async def test_list_conversations(client: AsyncClient) -> None:
    meta = ConversationMeta(user_id="u1", name="Test Conv")
    mock_store = MagicMock()
    mock_store.list.return_value = [meta]
    with patch("claude_code_bot.app._store", mock_store):
        response = await client.get("/conversations/u1")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["name"] == "Test Conv"
    assert "conversation_id" in data[0]
    assert "created_at" in data[0]
    assert "last_active" in data[0]


@pytest.mark.asyncio
async def test_list_conversations_empty(client: AsyncClient) -> None:
    mock_store = MagicMock()
    mock_store.list.return_value = []
    with patch("claude_code_bot.app._store", mock_store):
        response = await client.get("/conversations/u1")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_create_conversation_with_name(client: AsyncClient) -> None:
    meta = ConversationMeta(user_id="u1", name="My Chat")
    mock_store = MagicMock()
    mock_store.create.return_value = meta
    with patch("claude_code_bot.app._store", mock_store):
        response = await client.post(
            "/conversations/u1",
            json={"name": "My Chat"},
        )
    assert response.status_code == 201
    assert response.json()["name"] == "My Chat"
    mock_store.create.assert_called_once_with("u1", name="My Chat")


@pytest.mark.asyncio
async def test_create_conversation_without_name(client: AsyncClient) -> None:
    meta = ConversationMeta(user_id="u1", name="Conversation 1")
    mock_store = MagicMock()
    mock_store.create.return_value = meta
    with patch("claude_code_bot.app._store", mock_store):
        response = await client.post("/conversations/u1")
    assert response.status_code == 201
    mock_store.create.assert_called_once_with("u1", name=None)


@pytest.mark.asyncio
async def test_delete_conversation(client: AsyncClient) -> None:
    mock_store = MagicMock()
    with patch("claude_code_bot.app._store", mock_store):
        response = await client.delete("/conversations/u1/conv-123")
    assert response.status_code == 200
    assert response.json()["status"] == "deleted"
    mock_store.delete.assert_called_once_with("u1", "conv-123")


@pytest.mark.asyncio
async def test_delete_conversation_not_found(client: AsyncClient) -> None:
    mock_store = MagicMock()
    mock_store.delete.side_effect = KeyError("not found")
    with patch("claude_code_bot.app._store", mock_store):
        response = await client.delete("/conversations/u1/nonexistent")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_conversation_store_not_initialized(client: AsyncClient) -> None:
    with patch("claude_code_bot.app._store", None):
        response = await client.get("/conversations/u1")
    assert response.status_code == 503
