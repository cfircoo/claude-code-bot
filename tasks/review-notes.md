# Ralph Review Notes

## US-104: Add SSE streaming endpoint and conversation REST API
- **Date:** 2026-02-01T12:00:00Z
- **Additional test ideas:**
  - No test for SSE connection drop mid-stream (client disconnect handling)
  - No test for very large conversation lists (pagination not implemented)
  - No auth on conversation CRUD endpoints — currently anyone can access any user's conversations
- **Potential issues to watch:**
  - Conversation endpoints have no authentication — the user_id is in the URL path, no verification the caller owns it
  - No pagination on list_conversations — could be slow with many conversations
  - SSE streaming doesn't set a timeout — long-running agent calls could hang the connection
- **Suggestions for user:**
  - Consider adding API key auth to conversation CRUD endpoints (same as chat)
  - Consider adding pagination to GET /conversations/{user_id}
  - The old POST /chat endpoint was removed — any clients using it need to migrate to /chat/stream
- **Related areas that may need attention:**
  - US-105 (CLI) will need to consume the new SSE format
  - US-106 (Telegram) uses chat_stream() directly, not the HTTP endpoint — no impact
