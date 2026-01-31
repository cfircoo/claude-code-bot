"""Tests for /chat endpoint."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from claude_code_bot.app import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_chat_endpoint(client: AsyncClient) -> None:
    with patch("claude_code_bot.app._agent_service") as mock_svc:
        mock_svc.chat = AsyncMock(return_value="Hi there!")
        response = await client.post(
            "/chat",
            json={"user_id": "test", "message": "hello"},
        )
    assert response.status_code == 200
    assert response.json()["response"] == "Hi there!"


@pytest.mark.asyncio
async def test_chat_empty_message(client: AsyncClient) -> None:
    response = await client.post(
        "/chat",
        json={"user_id": "test", "message": ""},
    )
    assert response.status_code == 200
    assert "didn't catch" in response.json()["response"]


@pytest.mark.asyncio
async def test_chat_auth_rejected(client: AsyncClient) -> None:
    with patch("claude_code_bot.app._get_http_api_key", return_value="secret"):
        response = await client.post(
            "/chat",
            json={"user_id": "test", "message": "hello"},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_chat_auth_accepted(client: AsyncClient) -> None:
    with (
        patch("claude_code_bot.app._get_http_api_key", return_value="secret"),
        patch("claude_code_bot.app._agent_service") as mock_svc,
    ):
        mock_svc.chat = AsyncMock(return_value="Authed response")
        response = await client.post(
            "/chat",
            json={"user_id": "test", "message": "hello"},
            headers={"X-API-Key": "secret"},
        )
    assert response.status_code == 200
    assert response.json()["response"] == "Authed response"


@pytest.mark.asyncio
async def test_health_no_auth_needed(client: AsyncClient) -> None:
    with patch("claude_code_bot.app._get_http_api_key", return_value="secret"):
        response = await client.get("/health")
    assert response.status_code == 200
