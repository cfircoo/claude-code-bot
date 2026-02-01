"""Main agent service powered by claude-agent-sdk with streaming and session resume."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, AsyncIterable

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
from claude_code_bot.memory_store import MemoryStore
from claude_code_bot.permissions import PermissionManager
logger = structlog.get_logger()

MAX_RETRIES = 3
BACKOFF_BASE = 1.0


class AgentService:
    """Agent service with streaming output and session resume."""

    def __init__(
        self,
        config: BotConfig,
        store: ConversationStore,
        registry: SubAgentRegistry,
        memory_store: MemoryStore | None = None,
        permission_manager: PermissionManager | None = None,
    ) -> None:
        self.config = config
        self.store = store
        self.registry = registry
        self.memory_store = memory_store
        self.permission_manager = permission_manager

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

        # Append memory content if available
        if self.memory_store:
            core = self.memory_store.load_core()
            all_notes = self.memory_store.load_all()
            # Remove core content from all_notes to avoid duplication
            # all_notes includes core, so we show it structured
            if core or all_notes:
                parts.append("\n\n## Memory")
                if core:
                    parts.append(f"### Core\n{core}")
                if all_notes:
                    parts.append(f"### Notes\n{all_notes}")

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

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            include_partial_messages=True,
            max_turns=self.config.max_turns,
            permission_mode=self.config.permission_mode,
        )
        if self.config.allowed_tools:
            options.allowed_tools = self.config.allowed_tools
        if self.config.disallowed_tools:
            options.disallowed_tools = self.config.disallowed_tools
        if self.permission_manager:
            options.can_use_tool = self.permission_manager.make_callback()

        if meta.session_id:
            options.resume = meta.session_id

        last_error: Exception | None = None
        active_tools: set[str] = set()
        result_text_parts: list[str] = []
        session_id: str | None = None

        use_streaming_prompt = options.can_use_tool is not None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # SDK requires AsyncIterable prompt when can_use_tool is set
                prompt: str | AsyncIterable[dict[str, Any]]
                if use_streaming_prompt:

                    async def _make_prompt() -> AsyncIterable[dict[str, Any]]:
                        yield {
                            "type": "user",
                            "message": {"role": "user", "content": message},
                        }

                    prompt = _make_prompt()
                else:
                    prompt = message

                async for msg in claude_query(prompt=prompt, options=options):
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
                            if isinstance(block, ToolUseBlock):
                                tool_name = block.name
                                if tool_name in active_tools:
                                    active_tools.discard(tool_name)
                                    yield {"type": "tool_done", "tool": tool_name}

                    elif isinstance(msg, ResultMessage):
                        if msg.session_id:
                            session_id = msg.session_id

                # Success — persist session
                import time

                meta.last_active = time.time()
                if session_id:
                    meta.session_id = session_id
                self.store.update(meta)

                yield {
                    "type": "result",
                    "session_id": session_id or "",
                    "conversation_id": meta.conversation_id,
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
        """Non-streaming convenience method. Collects streamed text and returns it."""
        parts: list[str] = []
        async for event in self.chat_stream(user_id, message):
            if event["type"] == "text":
                parts.append(event.get("content", ""))
            elif event["type"] == "error":
                return event.get("content", "")
        return "".join(parts) or "..."
