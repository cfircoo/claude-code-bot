"""Tests for ConversationStore."""

from pathlib import Path

import pytest

from claude_code_bot.memory import ConversationMeta, ConversationStore


@pytest.fixture
def store(tmp_path: Path) -> ConversationStore:
    return ConversationStore(path=str(tmp_path))


def test_create_conversation(store: ConversationStore) -> None:
    meta = store.create("user1", "My Chat")
    assert meta.name == "My Chat"
    assert meta.user_id == "user1"
    assert meta.conversation_id
    assert meta.session_id is None


def test_create_auto_name(store: ConversationStore) -> None:
    c1 = store.create("user1")
    assert c1.name == "Conversation 1"
    c2 = store.create("user1")
    assert c2.name == "Conversation 2"


def test_list_conversations(store: ConversationStore) -> None:
    store.create("user1", "A")
    store.create("user1", "B")
    convs = store.list("user1")
    assert len(convs) == 2
    assert convs[0].name == "A"
    assert convs[1].name == "B"


def test_list_empty(store: ConversationStore) -> None:
    assert store.list("nobody") == []


def test_get_conversation(store: ConversationStore) -> None:
    created = store.create("user1", "Test")
    fetched = store.get("user1", created.conversation_id)
    assert fetched is not None
    assert fetched.name == "Test"
    assert fetched.conversation_id == created.conversation_id


def test_get_nonexistent(store: ConversationStore) -> None:
    assert store.get("user1", "fake-id") is None


def test_update_conversation(store: ConversationStore) -> None:
    created = store.create("user1", "Original")
    created.name = "Updated"
    created.session_id = "sess-123"
    store.update(created)
    fetched = store.get("user1", created.conversation_id)
    assert fetched is not None
    assert fetched.name == "Updated"
    assert fetched.session_id == "sess-123"


def test_update_nonexistent(store: ConversationStore) -> None:
    meta = ConversationMeta(user_id="user1", name="Ghost", conversation_id="fake")
    with pytest.raises(KeyError):
        store.update(meta)


def test_delete_conversation(store: ConversationStore) -> None:
    created = store.create("user1", "ToDelete")
    store.delete("user1", created.conversation_id)
    assert store.get("user1", created.conversation_id) is None
    assert store.list("user1") == []


def test_delete_nonexistent(store: ConversationStore) -> None:
    with pytest.raises(KeyError):
        store.delete("user1", "fake-id")


def test_safe_user_id(store: ConversationStore) -> None:
    store.create("user/with/../dots", "Safe")
    convs = store.list("user/with/../dots")
    assert len(convs) == 1


def test_persistence(tmp_path: Path) -> None:
    s1 = ConversationStore(path=str(tmp_path))
    created = s1.create("user1", "Persist")

    s2 = ConversationStore(path=str(tmp_path))
    convs = s2.list("user1")
    assert len(convs) == 1
    assert convs[0].conversation_id == created.conversation_id


def test_dir_auto_created(tmp_path: Path) -> None:
    new_dir = tmp_path / "sub" / "dir"
    ConversationStore(path=str(new_dir))
    assert new_dir.exists()
