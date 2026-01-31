# Ralph Test Log

## US-101: Replace memory.py with ConversationStore
- **Date:** 2026-01-31T22:00:00Z
- **Tests created:**
  - `tests/test_conversation_store.py` — 13 tests for ConversationStore CRUD, auto-name, safe ID, persistence
- **Tests modified:**
  - `tests/test_agent.py` — rewritten for new AgentService signature (4 tests)

## US-102: Create conversation management MCP tools
- **Date:** 2026-01-31T23:00:00Z
- **Tests created:**
  - `tests/test_tools.py` — 10 tests for list, create, switch, delete tools + config structure

## US-103: Rewrite AgentService with streaming and session resume
- **Date:** 2026-02-01T00:30:00Z
- **Tests created:**
  - `tests/test_agent.py::test_resolve_conversation_creates_new` — auto-create when no conversations exist
  - `tests/test_agent.py::test_resolve_conversation_uses_most_recent` — picks most recent by last_active
  - `tests/test_agent.py::test_resolve_conversation_by_id` — resolves specific conversation
  - `tests/test_agent.py::test_resolve_conversation_fallback_on_bad_id` — falls back to most recent on bad ID
  - `tests/test_agent.py::test_chat_stream_captures_session_id` — captures from SystemMessage init + persists
  - `tests/test_agent.py::test_chat_stream_resumes_session` — passes resume option when session_id exists
  - `tests/test_agent.py::test_chat_stream_text_events` — yields text events from StreamEvent deltas
  - `tests/test_agent.py::test_chat_stream_tool_events` — yields tool_start/tool_done events
  - `tests/test_agent.py::test_chat_stream_conversation_switched` — emits conversation_switched on tool use
  - `tests/test_agent.py::test_chat_stream_retries_on_failure` — retries transient errors with backoff
  - `tests/test_agent.py::test_chat_stream_all_retries_exhausted` — yields error after max retries
  - `tests/test_agent.py::test_chat_stream_auto_creates_conversation` — creates conversation on first message
  - `tests/test_agent.py::test_chat_stream_registers_mcp_tools` — passes MCP config to options
- **Tests modified:**
  - `tests/test_agent.py::test_build_system_prompt` — updated to check conversation instruction
- **Coverage notes:** 15 tests covering streaming, session resume, retry, conversation resolution, MCP registration
