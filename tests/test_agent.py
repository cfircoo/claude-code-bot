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

from claude_code_bot.agent import AgentService
from claude_code_bot.agents import BaseSubAgent, SubAgentRegistry
from claude_code_bot.config import BotConfig, PersonaConfig
from claude_code_bot.memory import ConversationStore
from claude_code_bot.memory_store import MemoryStore
from claude_code_bot.permissions import PermissionManager


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


def test_build_system_prompt_with_memory(config: BotConfig, store: ConversationStore, registry: SubAgentRegistry, tmp_path: Path) -> None:
    """Memory store content should appear in system prompt."""
    mem = MemoryStore(memory_path=tmp_path / "mem")
    (mem.memory_path / "core" / "info.txt").write_text("Core knowledge")
    mem.write("notes/tip.txt", "A useful tip")
    agent = AgentService(config=config, store=store, registry=registry, memory_store=mem)
    prompt = agent._build_system_prompt()
    assert "## Memory" in prompt
    assert "Core knowledge" in prompt
    assert "A useful tip" in prompt


def test_build_system_prompt_no_memory(agent: AgentService) -> None:
    """Without memory store, no memory section."""
    prompt = agent._build_system_prompt()
    assert "## Memory" not in prompt


def test_resolve_conversation_creates_new(agent: AgentService, store: ConversationStore) -> None:
    meta = agent._resolve_conversation("user1", None)
    assert meta.user_id == "user1"
    assert meta.name == "Conversation 1"
    # Persisted
    assert len(store.list("user1")) == 1


def test_resolve_conversation_creates_new_when_no_id(agent: AgentService, store: ConversationStore) -> None:
    store.create("user1", "Old")
    store.create("user1", "New")
    meta = agent._resolve_conversation("user1", None)
    # Should create a fresh conversation, not reuse existing
    existing_ids = {c.conversation_id for c in store.list("user1")}
    assert meta.conversation_id not in existing_ids or len(store.list("user1")) == 3


def test_resolve_conversation_by_id(agent: AgentService, store: ConversationStore) -> None:
    c1 = store.create("user1", "Target")
    store.create("user1", "Other")
    meta = agent._resolve_conversation("user1", c1.conversation_id)
    assert meta.conversation_id == c1.conversation_id


def test_resolve_conversation_fallback_on_bad_id(agent: AgentService, store: ConversationStore) -> None:
    store.create("user1", "Existing")
    meta = agent._resolve_conversation("user1", "nonexistent-id")
    # Should create a new conversation when ID not found
    assert meta.conversation_id != "nonexistent-id"


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
    assert result_events[0]["session_id"] == "s1"
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
async def test_chat_stream_metadata_in_system_prompt(agent: AgentService) -> None:
    """Metadata dict should be injected into system prompt status lines."""
    captured_options = {}

    async def mock_query(prompt, options):
        captured_options["system_prompt"] = options.system_prompt
        yield ResultMessage(
            subtype="result", duration_ms=100, duration_api_ms=80,
            is_error=False, num_turns=1, session_id="s1",
            result="ok",
        )

    with patch("claude_code_bot.agent.claude_query", mock_query):
        _ = [e async for e in agent.chat_stream("user1", "hi", metadata={"channel": "telegram", "username": "alice"})]

    prompt = captured_options["system_prompt"]
    assert "channel: telegram" in prompt
    assert "username: alice" in prompt


@pytest.mark.asyncio
async def test_chat_stream_usage_extraction(agent: AgentService, store: ConversationStore) -> None:
    """Usage stats from ResultMessage should appear in result event and be persisted."""
    stream = _make_stream(
        ResultMessage(
            subtype="result", duration_ms=500, duration_api_ms=400,
            is_error=False, num_turns=2, session_id="s1",
            result="Done",
            usage={"input_tokens": 100, "output_tokens": 50, "cache_read_input_tokens": 10, "cache_creation_input_tokens": 5},
            total_cost_usd=0.01,
        ),
    )
    with patch("claude_code_bot.agent.claude_query", stream):
        events = [e async for e in agent.chat_stream("user1", "hi")]

    result = [e for e in events if e["type"] == "result"][0]
    assert "usage" in result
    assert result["usage"]["input_tokens"] == 110  # 100 + 10 cache_read
    assert result["usage"]["output_tokens"] == 50
    assert result["usage"]["cost_usd"] == 0.01

    # Persisted to store
    convos = store.list("user1")
    assert convos[0].total_cost_usd == 0.01
    assert convos[0].total_input_tokens == 110


@pytest.mark.asyncio
async def test_chat_stream_with_permission_manager(config: BotConfig, store: ConversationStore, registry: SubAgentRegistry) -> None:
    """When permission_manager is set, streaming prompt should be used and can_use_tool set."""
    pm = PermissionManager(tools_requiring_approval=["Bash"])
    agent = AgentService(config=config, store=store, registry=registry, permission_manager=pm)

    captured_options = {}

    async def mock_query(prompt, options):
        captured_options["can_use_tool"] = options.can_use_tool
        captured_options["system_prompt"] = options.system_prompt
        # Consume the async iterable prompt
        if hasattr(prompt, "__aiter__"):
            async for _ in prompt:
                pass
        yield ResultMessage(
            subtype="result", duration_ms=100, duration_api_ms=80,
            is_error=False, num_turns=1, session_id="s1",
            result="ok",
        )

    with patch("claude_code_bot.agent.claude_query", mock_query):
        _ = [e async for e in agent.chat_stream("user1", "hi")]

    assert captured_options["can_use_tool"] is not None


@pytest.mark.asyncio
async def test_chat_non_streaming(agent: AgentService) -> None:
    """chat() should collect text events and return joined text."""
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
        result = await agent.chat("user1", "hi")

    assert result == "Hello world!"


@pytest.mark.asyncio
async def test_chat_returns_fallback_on_error(agent: AgentService) -> None:
    """chat() should return fallback message on error."""
    async def always_fail(prompt, options):
        raise RuntimeError("fail")
        yield

    with patch("claude_code_bot.agent.claude_query", always_fail):
        with patch("claude_code_bot.agent.BACKOFF_BASE", 0.01):
            result = await agent.chat("user1", "hi")

    assert result == "Oops, something went wrong."


@pytest.mark.asyncio
async def test_chat_returns_ellipsis_on_empty(agent: AgentService) -> None:
    """chat() should return '...' when no text events."""
    stream = _make_stream(
        ResultMessage(
            subtype="result", duration_ms=100, duration_api_ms=80,
            is_error=False, num_turns=1, session_id="s1",
            result="",
        ),
    )
    with patch("claude_code_bot.agent.claude_query", stream):
        result = await agent.chat("user1", "hi")

    assert result == "..."


@pytest.mark.asyncio
async def test_chat_stream_allowed_tools(config: BotConfig, store: ConversationStore, registry: SubAgentRegistry) -> None:
    """allowed_tools and disallowed_tools should be passed to options."""
    config.allowed_tools = ["Read", "Write"]
    config.disallowed_tools = ["Bash"]
    agent = AgentService(config=config, store=store, registry=registry)

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

    assert "Read" in captured_options["allowed_tools"]
    assert "Write" in captured_options["allowed_tools"]
    assert "Skill" in captured_options["allowed_tools"]
    assert captured_options["disallowed_tools"] == ["Bash"]
