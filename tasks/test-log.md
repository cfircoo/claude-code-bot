# Ralph Test Log

## US-101: Replace memory.py with ConversationStore
- **Date:** 2026-01-31T22:00:00Z
- **Tests created:**
  - `tests/test_conversation_store.py` — 13 tests for ConversationStore CRUD, auto-name, safe ID, persistence, dir creation
- **Tests modified:**
  - `tests/test_agent.py` — rewritten for new ConversationStore-based AgentService
- **Coverage notes:** Full coverage of ConversationStore public API

## US-102: Create conversation management MCP tools
- **Date:** 2026-01-31T23:00:00Z
- **Tests created:**
  - `tests/test_tools.py::TestListConversations::test_empty` — empty list returns []
  - `tests/test_tools.py::TestListConversations::test_with_conversations` — lists conversations with id, name, last_active
  - `tests/test_tools.py::TestCreateConversation::test_with_name` — creates with explicit name
  - `tests/test_tools.py::TestCreateConversation::test_auto_name` — auto-generates "Conversation N"
  - `tests/test_tools.py::TestSwitchConversation::test_existing` — switches to valid conversation
  - `tests/test_tools.py::TestSwitchConversation::test_not_found` — returns is_error for missing conversation
  - `tests/test_tools.py::TestDeleteConversation::test_existing` — deletes and verifies removal
  - `tests/test_tools.py::TestDeleteConversation::test_not_found` — returns is_error for missing conversation
  - `tests/test_tools.py::TestCreateConversationTools::test_returns_dict_config` — verifies McpSdkServerConfig shape
  - `tests/test_tools.py::TestCreateConversationTools::test_all_tools_registered` — verifies all 4 tools present
- **Coverage notes:** All 4 tool handlers tested for success and error paths
