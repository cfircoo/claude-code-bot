# Ralph Review Notes

## US-105: Update CLI agent.py with streaming display
- **Date:** 2026-02-01T14:00:00Z
- **Additional test ideas:**
  - Interactive mode test with mocked stdin (EOFError, "quit", normal flow)
  - Test with API key authentication header if HTTP channel has api_key configured
  - Test behavior when server closes connection mid-stream
- **Potential issues to watch:**
  - No API key support in CLI yet — if HTTP channel requires auth, CLI will get 401
  - 300s read timeout may not be enough for very long agent runs
  - No retry on connection drop during streaming (single attempt)
- **Suggestions for user:**
  - Consider adding `--api-key` flag for authenticated HTTP channels
  - Consider adding color/ANSI formatting for tool indicators and result separator
  - May want to persist conversation_id between interactive mode messages (currently must be set via flag)
- **Related areas that may need attention:**
  - US-106 (Telegram) should follow similar streaming event handling patterns
  - US-107 cleanup should verify no references to old POST /chat in CLI tests

## US-107: Clean up old code and update config
- **Date:** 2026-02-01T15:00:00Z
- **Additional test ideas:**
  - Test that loading a config.yaml with a `memory:` section still works (Pydantic ignores extra fields by default, or may error)
- **Potential issues to watch:**
  - If users have existing config.yaml with `memory:` section, Pydantic may reject it as an unknown field (depending on model_config). Consider adding `model_config = ConfigDict(extra="ignore")` to BotConfig if backward compat matters.
- **Suggestions for user:**
  - Consider adding `extra="ignore"` to BotConfig so old config files with `memory:` don't break on upgrade
- **Related areas that may need attention:**
  - None — this was the final cleanup story

## US-106: Update Telegram channel with typing indicator and streaming status
- **Date:** 2026-02-01T14:30:00Z
- **Additional test ideas:**
  - Test handle_text and handle_start handlers directly via aiogram test utilities
  - Test behavior when chat_stream raises an exception mid-stream (typing loop cleanup)
  - Test with very long responses that exceed Telegram's 4096 char message limit
- **Potential issues to watch:**
  - Telegram has a 4096 character limit per message — long agent responses will be truncated
  - show_tool_activity defaults to False — no config option to enable it yet
  - Typing loop swallows all exceptions silently — may hide connection issues
- **Suggestions for user:**
  - Consider splitting long responses into multiple Telegram messages (4096 char chunks)
  - Add config option for show_tool_activity per channel
  - Consider showing a "thinking..." message for very long agent runs instead of just typing indicator
- **Related areas that may need attention:**
  - handle_start still uses agent.chat() fallback when no greeting configured — should use streaming too (already updated)
  - US-107 should verify MemoryConfig cleanup doesn't break Telegram channel init
