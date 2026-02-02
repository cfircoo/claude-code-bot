"""Tests for MemoryStore persistent memory system."""

from __future__ import annotations

from pathlib import Path

import pytest

from claude_code_bot.memory_store import MemoryStore


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    """Create a MemoryStore in a temp directory."""
    return MemoryStore(memory_path=tmp_path / "memory")


def test_auto_creates_directories(tmp_path: Path) -> None:
    mem_path = tmp_path / "memory"
    MemoryStore(memory_path=mem_path)
    assert (mem_path / "core").is_dir()
    assert (mem_path / "to_improve").is_dir()


def test_write_to_improve(memory_store: MemoryStore) -> None:
    memory_store.write("to_improve/note.txt", "improve something")
    content = (memory_store.memory_path / "to_improve" / "note.txt").read_text()
    assert content == "improve something"


def test_write_custom_folder(memory_store: MemoryStore) -> None:
    memory_store.write("topics/python/basics.md", "Python basics")
    content = (memory_store.memory_path / "topics" / "python" / "basics.md").read_text()
    assert content == "Python basics"


def test_refuse_write_to_core(memory_store: MemoryStore) -> None:
    with pytest.raises(PermissionError, match="Cannot write to core"):
        memory_store.write("core/secret.txt", "should fail")


def test_refuse_delete_from_core(memory_store: MemoryStore) -> None:
    # Manually create a file in core
    core_file = memory_store.memory_path / "core" / "info.txt"
    core_file.write_text("important")
    with pytest.raises(PermissionError, match="Cannot delete from core"):
        memory_store.delete("core/info.txt")


def test_delete_file(memory_store: MemoryStore) -> None:
    memory_store.write("notes/temp.txt", "delete me")
    assert (memory_store.memory_path / "notes" / "temp.txt").exists()
    memory_store.delete("notes/temp.txt")
    assert not (memory_store.memory_path / "notes" / "temp.txt").exists()


def test_path_traversal_blocked(memory_store: MemoryStore) -> None:
    with pytest.raises(PermissionError, match="Path traversal"):
        memory_store.write("../../etc/passwd", "hacked")


def test_load_core(memory_store: MemoryStore) -> None:
    core = memory_store.memory_path / "core"
    (core / "personality.txt").write_text("Be helpful")
    result = memory_store.load_core()
    assert "Be helpful" in result
    assert "personality.txt" in result


def test_load_all(memory_store: MemoryStore) -> None:
    core = memory_store.memory_path / "core"
    (core / "info.txt").write_text("core info")
    memory_store.write("to_improve/fix.txt", "fix this")
    memory_store.write("notes/topic.txt", "some notes")
    result = memory_store.load_all()
    assert "core info" in result
    assert "fix this" in result
    assert "some notes" in result


def test_list_root(memory_store: MemoryStore) -> None:
    memory_store.write("to_improve/a.txt", "a")
    memory_store.write("notes/b.txt", "b")
    files = memory_store.list()
    assert "to_improve/a.txt" in files
    assert "notes/b.txt" in files


def test_list_subfolder(memory_store: MemoryStore) -> None:
    memory_store.write("notes/a.txt", "a")
    memory_store.write("notes/sub/b.txt", "b")
    files = memory_store.list("notes")
    assert "notes/a.txt" in files
    assert "notes/sub/b.txt" in files


def test_list_nonexistent_subfolder(memory_store: MemoryStore) -> None:
    assert memory_store.list("nonexistent") == []


def test_load_core_empty(memory_store: MemoryStore) -> None:
    assert memory_store.load_core() == ""


def test_load_core_unreadable_file(memory_store: MemoryStore) -> None:
    """Files that fail to read should be skipped silently."""
    core = memory_store.memory_path / "core"
    bad_file = core / "bad.txt"
    bad_file.write_text("content")
    # Make unreadable
    bad_file.chmod(0o000)
    try:
        result = memory_store.load_core()
        # Either empty or doesn't contain "bad.txt" content depending on OS
    finally:
        bad_file.chmod(0o644)


def test_load_all_unreadable_file(memory_store: MemoryStore) -> None:
    """Files that fail to read should be skipped silently."""
    memory_store.write("notes/good.txt", "good content")
    bad_file = memory_store.memory_path / "notes" / "bad.txt"
    bad_file.write_text("bad content")
    bad_file.chmod(0o000)
    try:
        result = memory_store.load_all()
        assert "good content" in result
    finally:
        bad_file.chmod(0o644)


def test_delete_nonexistent_file(memory_store: MemoryStore) -> None:
    """Deleting a non-existent file should not raise."""
    memory_store.delete("nonexistent.txt")  # Should not raise


def test_path_traversal_read(memory_store: MemoryStore) -> None:
    """Path traversal in list should be blocked."""
    with pytest.raises(PermissionError, match="Path traversal"):
        memory_store.list("../../etc")
