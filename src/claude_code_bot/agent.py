"""Main agent service powered by claude-agent-sdk."""

from __future__ import annotations

import asyncio
import time

import structlog
from claude_agent_sdk import query as claude_query, ClaudeAgentOptions

from claude_code_bot.config import BotConfig
from claude_code_bot.memory import MemoryBackend, Message
from claude_code_bot.agents import SubAgentRegistry

logger = structlog.get_logger()

MAX_RETRIES = 3
BACKOFF_BASE = 1.0


class AgentService:
    """Thin wrapper around claude-agent-sdk for persona-based conversations."""

    def __init__(
        self,
        config: BotConfig,
        memory: MemoryBackend,
        registry: SubAgentRegistry,
    ) -> None:
        self.config = config
        self.memory = memory
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

        return "\n".join(parts)

    def _format_history(self, messages: list[Message]) -> list[dict[str, str]]:
        """Format message history for the SDK."""
        return [{"role": m.role, "content": m.content} for m in messages]

    def _truncate_history(
        self, messages: list[Message], max_messages: int = 50
    ) -> list[Message]:
        """Truncate history keeping most recent messages."""
        if len(messages) <= max_messages:
            return messages
        removed = len(messages) - max_messages
        logger.info("conversation_truncated", removed_messages=removed)
        return messages[-max_messages:]

    async def chat(self, user_id: str, message: str, channel: str = "http") -> str:
        """Process a user message and return the bot's response."""
        # Load history
        try:
            history = await self.memory.load(user_id)
        except Exception:
            logger.warning("memory_load_failed", user_id=user_id)
            history = []

        # Add user message
        user_msg = Message(role="user", content=message, timestamp=time.time())
        history.append(user_msg)

        # Truncate if needed
        history = self._truncate_history(history)

        # Build prompt with history
        system_prompt = self._build_system_prompt()
        conversation = self._format_history(history)

        # Call claude-agent-sdk with retries
        response_text = await self._call_with_retry(system_prompt, conversation)

        # Save to memory
        assistant_msg = Message(
            role="assistant", content=response_text, timestamp=time.time()
        )
        history.append(assistant_msg)
        try:
            await self.memory.save(user_id, history)
        except Exception:
            logger.warning("memory_save_failed", user_id=user_id)

        return response_text

    async def _call_with_retry(
        self, system_prompt: str, conversation: list[dict[str, str]]
    ) -> str:
        """Call the LLM with exponential backoff retry."""
        last_error: Exception | None = None

        # Build the prompt from conversation
        prompt_parts = []
        for msg in conversation:
            prompt_parts.append(f"{msg['role']}: {msg['content']}")
        prompt = "\n".join(prompt_parts)

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result_parts: list[str] = []
                async for message in claude_query(
                    prompt=prompt,
                    options=ClaudeAgentOptions(
                        system_prompt=system_prompt,
                        max_turns=1,
                    ),
                ):
                    if hasattr(message, "content"):
                        for block in message.content:
                            if hasattr(block, "text"):
                                result_parts.append(block.text)

                return "".join(result_parts) if result_parts else "..."

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
        return self.config.persona.fallback_message
