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
