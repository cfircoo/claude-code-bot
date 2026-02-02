"""Conversation metadata store for multi-conversation support."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class ConversationMeta(BaseModel):
    """Metadata for a single conversation."""

    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    user_id: str
    name: str
    session_id: str | None = None
    created_at: float = Field(default_factory=time.time)
    last_active: float = Field(default_factory=time.time)
    total_cost_usd: float = 0.0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    message_count: int = 0


class ConversationStore:
    """Manages conversation metadata per user, stored as JSON files."""

    def __init__(self, path: str = "data/conversations") -> None:
        self.base_path = Path(path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _user_file(self, user_id: str) -> Path:
        safe_id = user_id.replace("/", "_").replace("..", "_")
        return self.base_path / f"{safe_id}.json"

    def _load_raw(self, user_id: str) -> list[dict[str, Any]]:
        filepath = self._user_file(user_id)
        if not filepath.exists():
            return []
        return json.loads(filepath.read_text())  # type: ignore[no-any-return]

    def _save_raw(self, user_id: str, data: list[dict[str, Any]]) -> None:
        filepath = self._user_file(user_id)
        filepath.write_text(json.dumps(data, indent=2))

    def list(self, user_id: str) -> list[ConversationMeta]:
        """List all conversations for a user."""
        raw = self._load_raw(user_id)
        return [ConversationMeta(**item) for item in raw]

    def get(self, user_id: str, conv_id: str) -> ConversationMeta | None:
        """Get a specific conversation by ID."""
        for item in self._load_raw(user_id):
            if item.get("conversation_id") == conv_id:
                return ConversationMeta(**item)
        return None

    def create(self, user_id: str, name: str | None = None) -> ConversationMeta:
        """Create a new conversation. Auto-generates name if not provided."""
        existing = self._load_raw(user_id)
        if name is None:
            name = f"Conversation {len(existing) + 1}"
        meta = ConversationMeta(user_id=user_id, name=name)
        existing.append(meta.model_dump())
        self._save_raw(user_id, existing)
        return meta

    def update(self, meta: ConversationMeta) -> None:
        """Update an existing conversation's metadata."""
        raw = self._load_raw(meta.user_id)
        for i, item in enumerate(raw):
            if item.get("conversation_id") == meta.conversation_id:
                raw[i] = meta.model_dump()
                self._save_raw(meta.user_id, raw)
                return
        raise KeyError(f"Conversation {meta.conversation_id} not found")

    def delete(self, user_id: str, conv_id: str) -> None:
        """Delete a conversation by ID."""
        raw = self._load_raw(user_id)
        filtered = [item for item in raw if item.get("conversation_id") != conv_id]
        if len(filtered) == len(raw):
            raise KeyError(f"Conversation {conv_id} not found")
        self._save_raw(user_id, filtered)
