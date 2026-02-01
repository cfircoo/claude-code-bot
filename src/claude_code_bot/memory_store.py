"""Persistent memory system with folder-based zones."""

from __future__ import annotations

from pathlib import Path


class MemoryStore:
    """Manages a file-based memory folder with read-only core/ zone.

    Folder structure:
        memory_path/
            core/       — read-only (owner-curated)
            to_improve/ — bot writes self-improvement suggestions
            ...         — bot freely organizes its own notes
    """

    def __init__(self, memory_path: str | Path = "~/.claude-bot/memory") -> None:
        self.memory_path = Path(memory_path).expanduser().resolve()
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """Create memory directories if they don't exist."""
        self.memory_path.mkdir(parents=True, exist_ok=True)
        (self.memory_path / "core").mkdir(exist_ok=True)
        (self.memory_path / "to_improve").mkdir(exist_ok=True)

    def _resolve_and_validate(self, path: str) -> Path:
        """Resolve a relative path within memory_path and validate no traversal."""
        resolved = (self.memory_path / path).resolve()
        if not str(resolved).startswith(str(self.memory_path)):
            raise PermissionError(f"Path traversal not allowed: {path}")
        return resolved

    def _is_core(self, resolved: Path) -> bool:
        """Check if resolved path is inside core/."""
        core = self.memory_path / "core"
        return str(resolved).startswith(str(core.resolve()))

    def load_core(self) -> str:
        """Read all files in core/ recursively and return combined text."""
        core = self.memory_path / "core"
        parts: list[str] = []
        for f in sorted(core.rglob("*")):
            if f.is_file():
                try:
                    parts.append(f"### {f.relative_to(core)}\n{f.read_text()}")
                except Exception:
                    pass
        return "\n\n".join(parts)

    def load_all(self) -> str:
        """Read all files in memory (core + to_improve + custom)."""
        parts: list[str] = []
        for f in sorted(self.memory_path.rglob("*")):
            if f.is_file():
                try:
                    rel = f.relative_to(self.memory_path)
                    parts.append(f"### {rel}\n{f.read_text()}")
                except Exception:
                    pass
        return "\n\n".join(parts)

    def write(self, path: str, content: str) -> Path:
        """Write content to a file in memory. Refuses core/."""
        resolved = self._resolve_and_validate(path)
        if self._is_core(resolved):
            raise PermissionError("Cannot write to core/ — it is read-only")
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content)
        return resolved

    def delete(self, path: str) -> None:
        """Delete a file from memory. Refuses core/."""
        resolved = self._resolve_and_validate(path)
        if self._is_core(resolved):
            raise PermissionError("Cannot delete from core/ — it is read-only")
        if resolved.is_file():
            resolved.unlink()

    def list(self, subfolder: str | None = None) -> list[str]:
        """List files in memory root or subfolder."""
        base = self.memory_path
        if subfolder:
            base = self._resolve_and_validate(subfolder)
        if not base.is_dir():
            return []
        return [
            str(f.relative_to(self.memory_path))
            for f in sorted(base.rglob("*"))
            if f.is_file()
        ]
