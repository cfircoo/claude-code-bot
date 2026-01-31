"""Tests for sub-agent registry."""

import pytest

from claude_code_bot.agents import BaseSubAgent, SubAgentRegistry


class DummyAgent(BaseSubAgent):
    name = "dummy"
    description = "A dummy agent for testing"

    async def handle(self, context):
        return f"handled: {context.get('query', '')}"


class AnotherAgent(BaseSubAgent):
    name = "another"
    description = "Another test agent"

    async def handle(self, context):
        return "another result"


@pytest.fixture
def registry() -> SubAgentRegistry:
    return SubAgentRegistry()


def test_register_and_get(registry: SubAgentRegistry) -> None:
    agent = DummyAgent()
    registry.register(agent)
    assert registry.get("dummy") is agent


def test_get_not_found(registry: SubAgentRegistry) -> None:
    with pytest.raises(KeyError, match="Sub-agent not found"):
        registry.get("nonexistent")


def test_list_agents(registry: SubAgentRegistry) -> None:
    registry.register(DummyAgent())
    registry.register(AnotherAgent())
    agents = registry.list()
    assert len(agents) == 2
    names = [a["name"] for a in agents]
    assert "dummy" in names
    assert "another" in names


def test_has(registry: SubAgentRegistry) -> None:
    registry.register(DummyAgent())
    assert registry.has("dummy")
    assert not registry.has("nonexistent")


@pytest.mark.asyncio
async def test_agent_handle() -> None:
    agent = DummyAgent()
    result = await agent.handle({"query": "test"})
    assert result == "handled: test"
