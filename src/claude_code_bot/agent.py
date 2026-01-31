"""Main agent service powered by claude-agent-sdk."""

from __future__ import annotations

import asyncio

import structlog
from claude_agent_sdk import query as claude_query, ClaudeAgentOptions

from claude_code_bot.config import BotConfig
from claude_code_bot.memory import ConversationStore
from claude_code_bot.agents import SubAgentRegistry

logger = structlog.get_logger()

MAX_RETRIES = 3
BACKOFF_BASE = 1.0


class AgentService:
    """Thin wrapper around claude-agent-sdk for persona-based conversations."""

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

        return "\n".join(parts)

    async def chat(self, user_id: str, message: str, channel: str = "http") -> str:
        """Process a user message and return the bot's response.

        Note: This is a temporary simplified version. US-103 will rewrite this
        with streaming and session resume support.
        """
        system_prompt = self._build_system_prompt()

        # Call claude-agent-sdk with retries
        response_text = await self._call_with_retry(system_prompt, [{"role": "user", "content": message}])

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
