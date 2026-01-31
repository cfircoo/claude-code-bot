"""Tests for the agent service."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_code_bot.agent import AgentService
from claude_code_bot.agents import BaseSubAgent, SubAgentRegistry
from claude_code_bot.config import BotConfig, PersonaConfig
from claude_code_bot.memory import JsonFileMemoryBackend, Message


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
def memory(tmp_path):
    return JsonFileMemoryBackend(path=str(tmp_path))


@pytest.fixture
def registry() -> SubAgentRegistry:
    return SubAgentRegistry()


@pytest.fixture
def agent(config, memory, registry) -> AgentService:
    return AgentService(config=config, memory=memory, registry=registry)


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


def test_truncate_history(agent: AgentService) -> None:
    messages = [
        Message(role="user", content=f"msg{i}", timestamp=time.time())
        for i in range(100)
    ]
    truncated = agent._truncate_history(messages, max_messages=10)
    assert len(truncated) == 10
    assert truncated[0].content == "msg90"


def test_truncate_history_no_op_when_short(agent: AgentService) -> None:
    messages = [Message(role="user", content="hi", timestamp=time.time())]
    truncated = agent._truncate_history(messages, max_messages=50)
    assert len(truncated) == 1


@pytest.mark.asyncio
async def test_chat_returns_fallback_on_llm_failure(agent: AgentService) -> None:
    with patch("claude_code_bot.agent.claude_query", side_effect=Exception("API down")):
        result = await agent.chat("user1", "hello")
    assert result == "Oops, something went wrong."


@pytest.mark.asyncio
async def test_chat_saves_to_memory(agent: AgentService) -> None:
    mock_fn = _make_mock_query("Hello back!")
    with patch("claude_code_bot.agent.claude_query", mock_fn):
        result = await agent.chat("user1", "hello")

    assert "Hello back!" in result
    history = await agent.memory.load("user1")
    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].role == "assistant"


@pytest.mark.asyncio
async def test_chat_continues_on_memory_save_failure(agent: AgentService) -> None:
    mock_fn = _make_mock_query("Response")
    with (
        patch("claude_code_bot.agent.claude_query", mock_fn),
        patch.object(agent.memory, "save", side_effect=IOError("disk full")),
    ):
        result = await agent.chat("user1", "hello")

    assert "Response" in result
