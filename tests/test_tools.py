"""Tests for conversation management MCP tools."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_code_bot.memory import ConversationStore
from claude_code_bot.tools import create_conversation_tools, _make_tools


@pytest.fixture()
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(path=str(tmp_path))


@pytest.fixture()
def user_id() -> str:
    return "test-user"


def _get_text(result: dict[str, object]) -> str:
    """Extract text from MCP tool response."""
    content = result["content"]
    assert isinstance(content, list)
    assert len(content) == 1
    return content[0]["text"]  # type: ignore[index]


@pytest.fixture()
def tools(store: ConversationStore, user_id: str) -> dict[str, object]:
    """Return a dict mapping tool name -> handler (async callable)."""
    tool_list = _make_tools(store, user_id)
    return {t.name: t.handler for t in tool_list}


class TestListConversations:
    @pytest.mark.asyncio()
    async def test_empty(self, tools: dict[str, object]) -> None:
        result = await tools["list_conversations"]({})
        items = json.loads(_get_text(result))
        assert items == []

    @pytest.mark.asyncio()
    async def test_with_conversations(
        self, tools: dict[str, object], store: ConversationStore, user_id: str
    ) -> None:
        store.create(user_id, "Chat A")
        store.create(user_id, "Chat B")
        result = await tools["list_conversations"]({})
        items = json.loads(_get_text(result))
        assert len(items) == 2
        assert items[0]["name"] == "Chat A"
        assert items[1]["name"] == "Chat B"
        assert "id" in items[0]
        assert "last_active" in items[0]


class TestCreateConversation:
    @pytest.mark.asyncio()
    async def test_with_name(
        self, tools: dict[str, object], store: ConversationStore, user_id: str
    ) -> None:
        result = await tools["create_conversation"]({"name": "My Chat"})
        data = json.loads(_get_text(result))
        assert data["name"] == "My Chat"
        assert "conversation_id" in data
        assert len(store.list(user_id)) == 1

    @pytest.mark.asyncio()
    async def test_auto_name(
        self, tools: dict[str, object], store: ConversationStore, user_id: str
    ) -> None:
        result = await tools["create_conversation"]({})
        data = json.loads(_get_text(result))
        assert data["name"] == "Conversation 1"


class TestSwitchConversation:
    @pytest.mark.asyncio()
    async def test_existing(
        self, tools: dict[str, object], store: ConversationStore, user_id: str
    ) -> None:
        meta = store.create(user_id, "Target")
        result = await tools["switch_conversation"](
            {"conversation_id": meta.conversation_id}
        )
        assert "Target" in _get_text(result)
        assert result.get("is_error") is None

    @pytest.mark.asyncio()
    async def test_not_found(self, tools: dict[str, object]) -> None:
        result = await tools["switch_conversation"](
            {"conversation_id": "nonexistent"}
        )
        assert result.get("is_error") is True
        assert "not found" in _get_text(result)


class TestDeleteConversation:
    @pytest.mark.asyncio()
    async def test_existing(
        self, tools: dict[str, object], store: ConversationStore, user_id: str
    ) -> None:
        meta = store.create(user_id, "ToDelete")
        result = await tools["delete_conversation"](
            {"conversation_id": meta.conversation_id}
        )
        assert "deleted" in _get_text(result)
        assert len(store.list(user_id)) == 0

    @pytest.mark.asyncio()
    async def test_not_found(self, tools: dict[str, object]) -> None:
        result = await tools["delete_conversation"](
            {"conversation_id": "nonexistent"}
        )
        assert result.get("is_error") is True
        assert "not found" in _get_text(result)


class TestCreateConversationTools:
    def test_returns_dict_config(
        self, store: ConversationStore, user_id: str
    ) -> None:
        result = create_conversation_tools(store, user_id)
        assert isinstance(result, dict)
        assert result["type"] == "sdk"
        assert result["name"] == "conversations"

    def test_all_tools_registered(
        self, store: ConversationStore, user_id: str
    ) -> None:
        tool_list = _make_tools(store, user_id)
        names = {t.name for t in tool_list}
        expected = {
            "list_conversations",
            "create_conversation",
            "switch_conversation",
            "delete_conversation",
        }
        assert names == expected
