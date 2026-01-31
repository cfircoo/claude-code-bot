"""Tests for the agent service."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from claude_code_bot.agent import AgentService
from claude_code_bot.agents import BaseSubAgent, SubAgentRegistry
from claude_code_bot.config import BotConfig, PersonaConfig
from claude_code_bot.memory import ConversationStore


@pytest.fixture
def config() -> BotConfig:
    return BotConfig(
        persona=PersonaConfig(
            name="TestBot",
            system_prompt="You are a test bot.",
            constraints=["Be brief"],
            fallback_message="Oops, something went wrong.",
        )
    )


@pytest.fixture
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(path=str(tmp_path))


@pytest.fixture
def registry() -> SubAgentRegistry:
    return SubAgentRegistry()


@pytest.fixture
def agent(config: BotConfig, store: ConversationStore, registry: SubAgentRegistry) -> AgentService:
    return AgentService(config=config, store=store, registry=registry)


def _make_mock_query(text: str):
    """Create an async generator mock for claude_query."""
    mock_block = MagicMock()
    mock_block.text = text
    mock_event = MagicMock()
    mock_event.content = [mock_block]

    async def mock_fn(*args, **kwargs):
        yield mock_event

    return mock_fn


def test_build_system_prompt(agent: AgentService) -> None:
    prompt = agent._build_system_prompt()
    assert "You are a test bot." in prompt
    assert "Be brief" in prompt


def test_build_system_prompt_with_agents(agent: AgentService) -> None:
    class FakeAgent(BaseSubAgent):
        name = "helper"
        description = "Helps with stuff"

        async def handle(self, context):
            return "done"

    agent.registry.register(FakeAgent())
    prompt = agent._build_system_prompt()
    assert "helper" in prompt
    assert "Helps with stuff" in prompt


@pytest.mark.asyncio
async def test_chat_returns_fallback_on_llm_failure(agent: AgentService) -> None:
    with patch("claude_code_bot.agent.claude_query", side_effect=Exception("API down")):
        result = await agent.chat("user1", "hello")
    assert result == "Oops, something went wrong."


@pytest.mark.asyncio
async def test_chat_returns_response(agent: AgentService) -> None:
    mock_fn = _make_mock_query("Hello back!")
    with patch("claude_code_bot.agent.claude_query", mock_fn):
        result = await agent.chat("user1", "hello")
    assert "Hello back!" in result
