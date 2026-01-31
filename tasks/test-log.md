# Ralph Test Log

## US-101: Replace memory.py with ConversationStore
- **Date:** 2026-01-31T22:00:00Z
- **Tests created:**
  - `tests/test_conversation_store.py` — 13 tests for ConversationStore CRUD, auto-name, persistence, safe ID

## US-102: Create conversation management MCP tools
- **Date:** 2026-01-31T23:00:00Z
- **Tests created:**
  - `tests/test_tools.py` — 10 tests for list, create, switch, delete tool handlers + config

## US-103: Rewrite AgentService with streaming and session resume
- **Date:** 2026-02-01T00:30:00Z
- **Tests created:**
  - `tests/test_agent.py` — 15 tests for chat_stream events, session capture/resume, retries, MCP registration

## US-104: Add SSE streaming endpoint and conversation REST API
- **Date:** 2026-02-01T12:00:00Z
- **Tests created:**
  - `tests/test_stream_and_conversations.py::test_chat_stream_returns_sse` — verifies SSE format and event parsing
  - `tests/test_stream_and_conversations.py::test_chat_stream_passes_conversation_id` — verifies conversation_id forwarded
  - `tests/test_stream_and_conversations.py::test_chat_stream_empty_message` — 400 on empty message
  - `tests/test_stream_and_conversations.py::test_chat_stream_auth_rejected` — 401 without API key
  - `tests/test_stream_and_conversations.py::test_chat_stream_auth_accepted` — 200 with correct API key
  - `tests/test_stream_and_conversations.py::test_chat_stream_not_initialized` — 503 when service not ready
  - `tests/test_stream_and_conversations.py::test_list_conversations` — GET returns conversation list
  - `tests/test_stream_and_conversations.py::test_list_conversations_empty` — GET returns empty list
  - `tests/test_stream_and_conversations.py::test_create_conversation_with_name` — POST with name returns 201
  - `tests/test_stream_and_conversations.py::test_create_conversation_without_name` — POST without body returns 201
  - `tests/test_stream_and_conversations.py::test_delete_conversation` — DELETE returns 200
  - `tests/test_stream_and_conversations.py::test_delete_conversation_not_found` — DELETE returns 404
  - `tests/test_stream_and_conversations.py::test_conversation_store_not_initialized` — 503 when store not ready
- **Tests modified:**
  - `tests/test_chat.py` — replaced with stub (old /chat endpoint removed)
