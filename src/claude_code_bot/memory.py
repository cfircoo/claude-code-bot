"""Per-user conversation memory store."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from pathlib import Path

from pydantic import BaseModel


class Message(BaseModel):
    """A single conversation message."""

    role: str  # "user" or "assistant"
    content: str
    timestamp: float


class MemoryBackend(ABC):
    """Abstract base class for memory backends."""

    @abstractmethod
    async def load(self, user_id: str) -> list[Message]:
        """Load conversation history for a user."""
        ...

    @abstractmethod
    async def save(self, user_id: str, messages: list[Message]) -> None:
        """Save conversation history for a user."""
        ...

    @abstractmethod
    async def clear(self, user_id: str) -> None:
        """Clear conversation history for a user."""
        ...


class JsonFileMemoryBackend(MemoryBackend):
    """Stores one JSON file per user_id in a configurable directory."""

    def __init__(self, path: str = "data/") -> None:
        self.base_path = Path(path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _user_file(self, user_id: str) -> Path:
        safe_id = user_id.replace("/", "_").replace("..", "_")
        return self.base_path / f"{safe_id}.json"

    async def load(self, user_id: str) -> list[Message]:
        """Load conversation history from JSON file."""
        filepath = self._user_file(user_id)
        if not filepath.exists():
            return []
        raw = json.loads(filepath.read_text())
        return [Message(**m) for m in raw]

    async def save(self, user_id: str, messages: list[Message]) -> None:
        """Save conversation history to JSON file."""
        filepath = self._user_file(user_id)
        data = [m.model_dump() for m in messages]
        filepath.write_text(json.dumps(data, indent=2))

    async def clear(self, user_id: str) -> None:
        """Delete conversation history file."""
        filepath = self._user_file(user_id)
        if filepath.exists():
            filepath.unlink()


def create_memory_backend(backend: str = "json_file", path: str = "data/") -> MemoryBackend:
    """Factory function to create a memory backend."""
    if backend == "json_file":
        return JsonFileMemoryBackend(path=path)
    raise ValueError(f"Unknown memory backend: {backend}")
