"""Sub-agent base class and registry."""

from __future__ import annotations

import importlib
import structlog
from abc import ABC, abstractmethod
from typing import Any

logger = structlog.get_logger()


class BaseSubAgent(ABC):
    """Abstract base class for sub-agents."""

    name: str
    description: str

    @abstractmethod
    async def handle(self, context: dict[str, Any]) -> str:
        """Handle a delegated task.

        Args:
            context: Dict with keys: user_id, channel, query, conversation_summary,
                     and optionally send_proactive callback.

        Returns:
            String result for the main agent to incorporate.
        """
        ...


class SubAgentRegistry:
    """Registry for sub-agents."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseSubAgent] = {}

    def register(self, agent: BaseSubAgent) -> None:
        """Register a sub-agent instance."""
        self._agents[agent.name] = agent
        logger.info("sub_agent_registered", agent_name=agent.name)

    def get(self, name: str) -> BaseSubAgent:
        """Get a registered sub-agent by name.

        Raises:
            KeyError: If no agent with that name is registered.
        """
        if name not in self._agents:
            raise KeyError(f"Sub-agent not found: {name}")
        return self._agents[name]

    def list(self) -> list[dict[str, str]]:
        """List all registered sub-agents with name and description."""
        return [
            {"name": a.name, "description": a.description}
            for a in self._agents.values()
        ]

    def has(self, name: str) -> bool:
        """Check if a sub-agent is registered."""
        return name in self._agents


def load_sub_agents_from_config(
    agents_config: dict[str, Any],
) -> SubAgentRegistry:
    """Load and register sub-agents from configuration.

    Args:
        agents_config: Dict of agent_name -> SubAgentConfig-like dicts.

    Returns:
        Populated SubAgentRegistry.
    """
    registry = SubAgentRegistry()

    for agent_name, agent_conf in agents_config.items():
        import_path = agent_conf.import_path if hasattr(agent_conf, "import_path") else agent_conf.get("import_path", "")
        if not import_path:
            logger.warning("sub_agent_missing_import_path", agent_name=agent_name)
            continue

        try:
            module_path, class_name = import_path.rsplit(".", 1)
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)
            agent_instance = agent_class()
            if not hasattr(agent_instance, "name"):
                agent_instance.name = agent_name
            if not hasattr(agent_instance, "description") or not agent_instance.description:
                desc = agent_conf.description if hasattr(agent_conf, "description") else agent_conf.get("description", "")
                agent_instance.description = desc
            registry.register(agent_instance)
        except Exception as e:
            logger.error(
                "sub_agent_load_failed",
                agent_name=agent_name,
                import_path=import_path,
                error=str(e),
            )
            raise ImportError(
                f"Failed to load sub-agent '{agent_name}' from '{import_path}': {e}"
            ) from e

    return registry
