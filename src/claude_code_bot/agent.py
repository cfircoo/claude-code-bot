"""Main agent service powered by claude-agent-sdk with streaming and session resume."""

from __future__ import annotations

import asyncio
from typing import AsyncGenerator

import structlog
from claude_agent_sdk import (
    ClaudeAgentOptions,
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
    query as claude_query,
)
from claude_agent_sdk.types import StreamEvent

from claude_code_bot.agents import SubAgentRegistry
from claude_code_bot.config import BotConfig
from claude_code_bot.memory import ConversationMeta, ConversationStore
from claude_code_bot.tools import create_conversation_tools

logger = structlog.get_logger()

MAX_RETRIES = 3
BACKOFF_BASE = 1.0

CONVERSATION_INSTRUCTION = (
    "\n\nYou can manage conversations when the user asks. "
    "Use the conversation tools to list, create, switch, or delete conversations."
)


class AgentService:
    """Agent service with streaming output and session resume."""

    def __init__(
        self,
        config: BotConfig,
        store: ConversationStore,
        registry: SubAgentRegistry,
    ) -> None:
        self.config = config
        self.store = store
        self.registry = registry

    def _build_system_prompt(self) -> str:
        """Build the system prompt from persona config."""
        persona = self.config.persona
        parts = [persona.system_prompt]

        if persona.constraints:
            parts.append("\n\nBehavioral rules:")
            for i, constraint in enumerate(persona.constraints, 1):
                parts.append(f"{i}. {constraint}")

        agents = self.registry.list()
        if agents:
            parts.append("\n\nYou have access to the following specialized sub-agents:")
            for agent_info in agents:
                parts.append(
                    f"- {agent_info['name']}: {agent_info['description']}"
                )
            parts.append(
                "\nTo use a sub-agent, call the corresponding tool with a 'query' parameter."
            )

        parts.append(CONVERSATION_INSTRUCTION)
        return "\n".join(parts)

    def _resolve_conversation(
        self, user_id: str, conversation_id: str | None
    ) -> ConversationMeta:
        """Get the target conversation, using most recent or auto-creating."""
        if conversation_id:
            meta = self.store.get(user_id, conversation_id)
            if meta:
                return meta

        convos = self.store.list(user_id)
        if convos:
            return max(convos, key=lambda c: c.last_active)

        return self.store.create(user_id)

    async def chat_stream(
        self,
        user_id: str,
        message: str,
        conversation_id: str | None = None,
    ) -> AsyncGenerator[dict[str, str], None]:
        """Process a message and yield streaming events.

        Event types:
          - {type: "text", content: str}
          - {type: "tool_start", tool: str}
          - {type: "tool_done", tool: str}
          - {type: "result", content: str, session_id: str}
          - {type: "error", content: str}
          - {type: "conversation_switched", conversation_id: str}
        """
        meta = self._resolve_conversation(user_id, conversation_id)
        system_prompt = self._build_system_prompt()

        mcp_tools = create_conversation_tools(self.store, user_id)
        mcp_servers: dict[str, object] = {"conversations": mcp_tools}

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            include_partial_messages=True,
            mcp_servers=mcp_servers,  # type: ignore[arg-type]
            allowed_tools=[
                "mcp__conversations__list_conversations",
                "mcp__conversations__create_conversation",
                "mcp__conversations__switch_conversation",
                "mcp__conversations__delete_conversation",
            ],
        )

        if meta.session_id:
            options.resume = meta.session_id

        last_error: Exception | None = None
        active_tools: set[str] = set()
        result_text_parts: list[str] = []
        session_id: str | None = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async for msg in claude_query(prompt=message, options=options):
                    if isinstance(msg, SystemMessage):
                        if msg.subtype == "init":
                            sid = msg.data.get("session_id")
                            if sid:
                                session_id = sid

                    elif isinstance(msg, StreamEvent):
                        event = msg.event
                        event_type = event.get("type", "")
                        if event_type == "content_block_start":
                            cb = event.get("content_block", {})
                            if cb.get("type") == "tool_use":
                                tool_name = cb.get("name", "unknown")
                                active_tools.add(tool_name)
                                yield {"type": "tool_start", "tool": tool_name}
                            elif cb.get("type") == "text":
                                pass  # text delta will follow
                        elif event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                text = delta.get("text", "")
                                if text:
                                    yield {"type": "text", "content": text}

                    elif isinstance(msg, AssistantMessage):
                        for block in msg.content:
                            if isinstance(block, TextBlock):
                                result_text_parts.append(block.text)
                            elif isinstance(block, ToolUseBlock):
                                tool_name = block.name
                                if tool_name in active_tools:
                                    active_tools.discard(tool_name)
                                    yield {"type": "tool_done", "tool": tool_name}
                                # Check for conversation switch
                                if tool_name == "mcp__conversations__switch_conversation":
                                    switched_id = block.input.get("conversation_id", "")
                                    if switched_id:
                                        yield {
                                            "type": "conversation_switched",
                                            "conversation_id": switched_id,
                                        }

                    elif isinstance(msg, ResultMessage):
                        if msg.session_id:
                            session_id = msg.session_id
                        if msg.result:
                            result_text_parts.append(msg.result)

                # Success — persist session
                import time

                meta.last_active = time.time()
                if session_id:
                    meta.session_id = session_id
                self.store.update(meta)

                final_text = "".join(result_text_parts) or "..."
                yield {
                    "type": "result",
                    "content": final_text,
                    "session_id": session_id or "",
                }
                return

            except Exception as e:
                last_error = e
                logger.error(
                    "llm_call_failed",
                    attempt=attempt,
                    error=str(e),
                    error_type=type(e).__name__,
                )
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))

        logger.error("llm_all_retries_exhausted", error=str(last_error))
        yield {"type": "error", "content": self.config.persona.fallback_message}

    async def chat(self, user_id: str, message: str, channel: str = "http") -> str:
        """Non-streaming convenience method. Consumes chat_stream and returns final text."""
        result = ""
        async for event in self.chat_stream(user_id, message):
            if event["type"] == "result":
                result = event["content"]
            elif event["type"] == "error":
                result = event["content"]
        return result
