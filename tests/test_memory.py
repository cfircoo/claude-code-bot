"""Tests for memory backends."""

import time
from pathlib import Path

import pytest

from claude_code_bot.memory import (
    JsonFileMemoryBackend,
    Message,
    create_memory_backend,
)


@pytest.fixture
def memory(tmp_path: Path) -> JsonFileMemoryBackend:
    return JsonFileMemoryBackend(path=str(tmp_path))


@pytest.mark.asyncio
async def test_save_and_load(memory: JsonFileMemoryBackend) -> None:
    messages = [
        Message(role="user", content="Hello", timestamp=time.time()),
        Message(role="assistant", content="Hi there!", timestamp=time.time()),
    ]
    await memory.save("user1", messages)
    loaded = await memory.load("user1")
    assert len(loaded) == 2
    assert loaded[0].content == "Hello"
    assert loaded[1].role == "assistant"


@pytest.mark.asyncio
async def test_load_empty(memory: JsonFileMemoryBackend) -> None:
    loaded = await memory.load("nonexistent")
    assert loaded == []


@pytest.mark.asyncio
async def test_clear(memory: JsonFileMemoryBackend) -> None:
    messages = [Message(role="user", content="Test", timestamp=time.time())]
    await memory.save("user1", messages)
    await memory.clear("user1")
    loaded = await memory.load("user1")
    assert loaded == []


@pytest.mark.asyncio
async def test_separate_users(memory: JsonFileMemoryBackend) -> None:
    msg_a = [Message(role="user", content="From A", timestamp=time.time())]
    msg_b = [Message(role="user", content="From B", timestamp=time.time())]
    await memory.save("userA", msg_a)
    await memory.save("userB", msg_b)
    assert (await memory.load("userA"))[0].content == "From A"
    assert (await memory.load("userB"))[0].content == "From B"


@pytest.mark.asyncio
async def test_persistence_across_instances(tmp_path: Path) -> None:
    mem1 = JsonFileMemoryBackend(path=str(tmp_path))
    messages = [Message(role="user", content="Persisted", timestamp=time.time())]
    await mem1.save("user1", messages)

    mem2 = JsonFileMemoryBackend(path=str(tmp_path))
    loaded = await mem2.load("user1")
    assert len(loaded) == 1
    assert loaded[0].content == "Persisted"


@pytest.mark.asyncio
async def test_memory_dir_created_automatically(tmp_path: Path) -> None:
    new_dir = tmp_path / "subdir" / "memory"
    mem = JsonFileMemoryBackend(path=str(new_dir))
    assert new_dir.exists()


def test_create_memory_backend_json() -> None:
    backend = create_memory_backend("json_file", "/tmp/test_mem")
    assert isinstance(backend, JsonFileMemoryBackend)


def test_create_memory_backend_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown memory backend"):
        create_memory_backend("unknown")


@pytest.mark.asyncio
async def test_memory_graceful_degradation_on_corrupt_file(
    memory: JsonFileMemoryBackend, tmp_path: Path
) -> None:
    """If memory file is corrupted, load should handle it gracefully."""
    filepath = tmp_path / "bad_user.json"
    filepath.write_text("not valid json{{{")
    with pytest.raises(Exception):
        await memory.load("bad_user")
