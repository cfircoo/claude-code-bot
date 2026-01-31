"""Tests for the agent service."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest

from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ToolUseBlock,
)
from claude_agent_sdk.types import StreamEvent

from claude_code_bot.agent import AgentService, CONVERSATION_INSTRUCTION
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


def test_build_system_prompt(agent: AgentService) -> None:
    prompt = agent._build_system_prompt()
    assert "You are a test bot." in prompt
    assert "Be brief" in prompt
    assert CONVERSATION_INSTRUCTION.strip() in prompt


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


def test_resolve_conversation_creates_new(agent: AgentService, store: ConversationStore) -> None:
    meta = agent._resolve_conversation("user1", None)
    assert meta.user_id == "user1"
    assert meta.name == "Conversation 1"
    # Persisted
    assert len(store.list("user1")) == 1


def test_resolve_conversation_uses_most_recent(agent: AgentService, store: ConversationStore) -> None:
    c1 = store.create("user1", "Old")
    c1.last_active = time.time() - 100
    store.update(c1)
    c2 = store.create("user1", "New")
    meta = agent._resolve_conversation("user1", None)
    assert meta.conversation_id == c2.conversation_id


def test_resolve_conversation_by_id(agent: AgentService, store: ConversationStore) -> None:
    c1 = store.create("user1", "Target")
    store.create("user1", "Other")
    meta = agent._resolve_conversation("user1", c1.conversation_id)
    assert meta.conversation_id == c1.conversation_id


def test_resolve_conversation_fallback_on_bad_id(agent: AgentService, store: ConversationStore) -> None:
    store.create("user1", "Existing")
    meta = agent._resolve_conversation("user1", "nonexistent-id")
    assert meta.name == "Existing"


# --- Streaming tests ---


def _make_stream(*messages):
    """Create a mock async generator yielding the given messages."""
    async def mock_query(prompt, options):
        for m in messages:
            yield m
    return mock_query


@pytest.mark.asyncio
async def test_chat_stream_captures_session_id(agent: AgentService, store: ConversationStore) -> None:
    stream = _make_stream(
        SystemMessage(subtype="init", data={"session_id": "sess-123"}),
        AssistantMessage(content=[TextBlock(text="Hello!")], model="claude"),
        ResultMessage(
            subtype="result", duration_ms=100, duration_api_ms=80,
            is_error=False, num_turns=1, session_id="sess-123",
            result="Hello!",
        ),
    )
    with patch("claude_code_bot.agent.claude_query", stream):
        events = [e async for e in agent.chat_stream("user1", "hi")]

    result_events = [e for e in events if e["type"] == "result"]
    assert len(result_events) == 1
    assert result_events[0]["session_id"] == "sess-123"

    # Session persisted to store
    convos = store.list("user1")
    assert len(convos) == 1
    assert convos[0].session_id == "sess-123"


@pytest.mark.asyncio
async def test_chat_stream_resumes_session(agent: AgentService, store: ConversationStore) -> None:
    meta = store.create("user1", "Test")
    meta.session_id = "old-sess"
    store.update(meta)

    captured_options = {}

    async def mock_query(prompt, options):
        captured_options.update(vars(options))
        yield ResultMessage(
            subtype="result", duration_ms=100, duration_api_ms=80,
            is_error=False, num_turns=1, session_id="new-sess",
            result="Resumed!",
        )

    with patch("claude_code_bot.agent.claude_query", mock_query):
        events = [e async for e in agent.chat_stream("user1", "hi", meta.conversation_id)]

    assert captured_options["resume"] == "old-sess"
    assert captured_options["include_partial_messages"] is True


@pytest.mark.asyncio
async def test_chat_stream_text_events(agent: AgentService) -> None:
    stream = _make_stream(
        StreamEvent(
            uuid="1", session_id="s1", event={
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "Hello "},
            }
        ),
        StreamEvent(
            uuid="2", session_id="s1", event={
                "type": "content_block_delta",
                "delta": {"type": "text_delta", "text": "world!"},
            }
        ),
        ResultMessage(
            subtype="result", duration_ms=100, duration_api_ms=80,
            is_error=False, num_turns=1, session_id="s1",
            result="Hello world!",
        ),
    )
    with patch("claude_code_bot.agent.claude_query", stream):
        events = [e async for e in agent.chat_stream("user1", "hi")]

    text_events = [e for e in events if e["type"] == "text"]
    assert len(text_events) == 2
    assert text_events[0]["content"] == "Hello "
    assert text_events[1]["content"] == "world!"


@pytest.mark.asyncio
async def test_chat_stream_tool_events(agent: AgentService) -> None:
    stream = _make_stream(
        StreamEvent(
            uuid="1", session_id="s1", event={
                "type": "content_block_start",
                "content_block": {"type": "tool_use", "name": "read_file"},
            }
        ),
        AssistantMessage(
            content=[ToolUseBlock(id="tu1", name="read_file", input={"path": "/tmp"})],
            model="claude",
        ),
        ResultMessage(
            subtype="result", duration_ms=100, duration_api_ms=80,
            is_error=False, num_turns=1, session_id="s1",
            result="Done",
        ),
    )
    with patch("claude_code_bot.agent.claude_query", stream):
        events = [e async for e in agent.chat_stream("user1", "hi")]

    assert {"type": "tool_start", "tool": "read_file"} in events
    assert {"type": "tool_done", "tool": "read_file"} in events


@pytest.mark.asyncio
async def test_chat_stream_conversation_switched(agent: AgentService, store: ConversationStore) -> None:
    store.create("user1", "Target")

    stream = _make_stream(
        AssistantMessage(
            content=[ToolUseBlock(
                id="tu1",
                name="mcp__conversations__switch_conversation",
                input={"conversation_id": "conv-xyz"},
            )],
            model="claude",
        ),
        ResultMessage(
            subtype="result", duration_ms=100, duration_api_ms=80,
            is_error=False, num_turns=1, session_id="s1",
            result="Switched!",
        ),
    )
    with patch("claude_code_bot.agent.claude_query", stream):
        events = [e async for e in agent.chat_stream("user1", "switch")]

    switched = [e for e in events if e["type"] == "conversation_switched"]
    assert len(switched) == 1
    assert switched[0]["conversation_id"] == "conv-xyz"


@pytest.mark.asyncio
async def test_chat_stream_retries_on_failure(agent: AgentService) -> None:
    call_count = 0

    async def failing_then_ok(prompt, options):
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("Transient error")
        yield ResultMessage(
            subtype="result", duration_ms=100, duration_api_ms=80,
            is_error=False, num_turns=1, session_id="s1",
            result="Recovered!",
        )

    with patch("claude_code_bot.agent.claude_query", failing_then_ok):
        with patch("claude_code_bot.agent.BACKOFF_BASE", 0.01):
            events = [e async for e in agent.chat_stream("user1", "hi")]

    result_events = [e for e in events if e["type"] == "result"]
    assert len(result_events) == 1
    assert result_events[0]["content"] == "Recovered!"
    assert call_count == 2


@pytest.mark.asyncio
async def test_chat_stream_all_retries_exhausted(agent: AgentService) -> None:
    async def always_fail(prompt, options):
        raise RuntimeError("Permanent error")
        yield  # make it a generator  # noqa: E501 - unreachable but needed for type

    with patch("claude_code_bot.agent.claude_query", always_fail):
        with patch("claude_code_bot.agent.BACKOFF_BASE", 0.01):
            events = [e async for e in agent.chat_stream("user1", "hi")]

    error_events = [e for e in events if e["type"] == "error"]
    assert len(error_events) == 1
    assert error_events[0]["content"] == "Oops, something went wrong."


@pytest.mark.asyncio
async def test_chat_stream_auto_creates_conversation(agent: AgentService, store: ConversationStore) -> None:
    assert len(store.list("user1")) == 0

    stream = _make_stream(
        ResultMessage(
            subtype="result", duration_ms=100, duration_api_ms=80,
            is_error=False, num_turns=1, session_id="s1",
            result="Hi!",
        ),
    )
    with patch("claude_code_bot.agent.claude_query", stream):
        events = [e async for e in agent.chat_stream("user1", "hi")]

    assert len(store.list("user1")) == 1


@pytest.mark.asyncio
async def test_chat_stream_registers_mcp_tools(agent: AgentService) -> None:
    captured_options = {}

    async def mock_query(prompt, options):
        captured_options.update(vars(options))
        yield ResultMessage(
            subtype="result", duration_ms=100, duration_api_ms=80,
            is_error=False, num_turns=1, session_id="s1",
            result="ok",
        )

    with patch("claude_code_bot.agent.claude_query", mock_query):
        _ = [e async for e in agent.chat_stream("user1", "hi")]

    assert "conversations" in captured_options["mcp_servers"]
    assert "mcp__conversations__list_conversations" in captured_options["allowed_tools"]
