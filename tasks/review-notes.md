# Ralph Review Notes

## US-103: Rewrite AgentService with streaming and session resume
- **Date:** 2026-02-01T00:30:00Z
- **Additional test ideas:**
  - Edge case: what happens when store.update() fails after a successful query (session_id lost)
  - Missing: no test for the backward-compatible chat() method directly
  - Missing: no test for concurrent chat_stream calls for the same user (race on conversation resolution)
- **Potential issues to watch:**
  - The `import time` inside chat_stream is a minor code smell — could be at module level
  - StreamEvent.event dict structure depends on Anthropic API internals — may change across SDK versions
  - The tool_done detection relies on AssistantMessage arriving after StreamEvent tool_start — if SDK changes ordering, tool_done events could be missed
- **Suggestions for user:**
  - Consider adding a timeout to the overall chat_stream call (not just per-retry)
  - The conversation_switched event only fires for switch_conversation tool — if the agent creates a new conversation and immediately uses it, no switch event is emitted
  - May want to add a max_turns limit to prevent runaway agent loops
- **Related areas that may need attention:**
  - app.py POST /chat still uses the sync chat() wrapper — US-104 will replace with SSE
  - telegram.py uses chat() — US-106 will migrate to chat_stream with typing indicators
