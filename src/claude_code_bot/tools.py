"""Conversation management MCP tools for the agent."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from claude_agent_sdk import tool, create_sdk_mcp_server, SdkMcpTool
from claude_agent_sdk.types import McpSdkServerConfig

from claude_code_bot.memory import ConversationStore


def _text(text: str) -> dict[str, object]:
    """Helper to create a text MCP response."""
    return {"content": [{"type": "text", "text": text}]}


def _make_tools(
    store: ConversationStore, user_id: str
) -> list[SdkMcpTool[object]]:
    """Create the individual MCP tool instances (for testing and registration)."""

    @tool(
        "list_conversations",
        "List all conversations for the current user. Returns id, name, and last_active for each.",
        {},
    )
    async def list_conversations(args: dict[str, object]) -> dict[str, object]:
        convos = store.list(user_id)
        items = [
            {
                "id": c.conversation_id,
                "name": c.name,
                "last_active": datetime.fromtimestamp(
                    c.last_active, tz=timezone.utc
                ).isoformat(),
            }
            for c in convos
        ]
        return _text(json.dumps(items, indent=2))

    @tool(
        "create_conversation",
        "Create a new conversation. Optionally provide a name.",
        {"name": str},
    )
    async def create_conversation(args: dict[str, object]) -> dict[str, object]:
        name = args.get("name")
        meta = store.create(user_id, name=str(name) if name else None)
        return _text(
            json.dumps(
                {
                    "conversation_id": meta.conversation_id,
                    "name": meta.name,
                    "created_at": datetime.fromtimestamp(
                        meta.created_at, tz=timezone.utc
                    ).isoformat(),
                },
                indent=2,
            )
        )

    @tool(
        "switch_conversation",
        "Switch to a different conversation by its ID.",
        {"conversation_id": str},
    )
    async def switch_conversation(args: dict[str, object]) -> dict[str, object]:
        conv_id = str(args["conversation_id"])
        meta = store.get(user_id, conv_id)
        if meta is None:
            return {
                "content": [{"type": "text", "text": f"Conversation {conv_id} not found."}],
                "is_error": True,
            }
        return _text(f"Switched to conversation: {meta.name}")

    @tool(
        "delete_conversation",
        "Delete a conversation by its ID.",
        {"conversation_id": str},
    )
    async def delete_conversation(args: dict[str, object]) -> dict[str, object]:
        conv_id = str(args["conversation_id"])
        try:
            store.delete(user_id, conv_id)
        except KeyError:
            return {
                "content": [{"type": "text", "text": f"Conversation {conv_id} not found."}],
                "is_error": True,
            }
        return _text(f"Conversation {conv_id} deleted.")

    return [list_conversations, create_conversation, switch_conversation, delete_conversation]


def create_conversation_tools(
    store: ConversationStore, user_id: str
) -> McpSdkServerConfig:
    """Create MCP server with conversation management tools bound to a user.

    Each tool accesses the ConversationStore via closure over ``store``
    and ``user_id``.
    """
    tools = _make_tools(store, user_id)
    return create_sdk_mcp_server(name="conversations", tools=tools)
