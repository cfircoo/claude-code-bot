# Ralph Review Notes

## US-102: Create conversation management MCP tools
- **Date:** 2026-01-31T23:00:00Z
- **Additional test ideas:**
  - Edge case: what happens when switch_conversation is called with empty string?
  - Missing: no concurrency test (two tools modifying same user's file simultaneously)
  - Could test that list_conversations returns items sorted by last_active
- **Potential issues to watch:**
  - The switch_conversation tool only confirms the conversation exists — the actual "switching" logic will be in AgentService (US-103). The tool is a signal, not a state change.
  - Tool input_schema uses simple `{"name": str}` — the SDK may or may not enforce required vs optional. `create_conversation` treats missing `name` as None which works, but verify SDK behavior.
- **Suggestions for user:**
  - Consider whether `switch_conversation` should update `last_active` timestamp on the target conversation
  - The `delete_conversation` tool doesn't warn if deleting the currently active conversation — US-103 should handle this gracefully
- **Related areas that may need attention:**
  - US-103 will need to wire these tools into AgentService via `mcp_servers` option and handle the `conversation_switched` event type
