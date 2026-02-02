"""Tests for sub-agent loading from config."""

from __future__ import annotations

from typing import Any

import pytest

from claude_code_bot.agents import BaseSubAgent, SubAgentRegistry, load_sub_agents_from_config


class DummySubAgent(BaseSubAgent):
    name = "dummy"
    description = "A dummy agent"

    async def handle(self, context: dict[str, Any]) -> str:
        return "dummy result"


def test_load_sub_agents_valid_config() -> None:
    """Valid import_path should load and register the agent."""
    config = {
        "dummy": {
            "import_path": "tests.test_agents.DummySubAgent",
            "description": "Test dummy",
        }
    }
    # Use dict-style config
    registry = load_sub_agents_from_config(config)
    assert registry.has("dummy")
    info = registry.list()
    assert len(info) == 1
    assert info[0]["name"] == "dummy"


def test_load_sub_agents_missing_import_path() -> None:
    """Missing import_path should skip the agent."""
    config = {"broken": {"import_path": "", "description": "No path"}}
    registry = load_sub_agents_from_config(config)
    assert not registry.has("broken")


def test_load_sub_agents_bad_import_path() -> None:
    """Invalid import path should raise ImportError."""
    config = {"bad": {"import_path": "nonexistent.module.Class", "description": "Bad"}}
    with pytest.raises(ImportError, match="Failed to load sub-agent"):
        load_sub_agents_from_config(config)


def test_load_sub_agents_with_pydantic_config() -> None:
    """Config objects with attributes (like pydantic models) should also work."""
    from claude_code_bot.config import SubAgentConfig
    config = {
        "dummy": SubAgentConfig(
            import_path="tests.test_agents.DummySubAgent",
            description="From pydantic",
        )
    }
    registry = load_sub_agents_from_config(config)
    assert registry.has("dummy")
