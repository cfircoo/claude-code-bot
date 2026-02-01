# Ralph Review Notes

## US-201: Add extra="ignore" to BotConfig
- **Date:** 2026-02-01
- **Additional test ideas:**
  - Could test that extra fields are truly discarded (not accessible via `config.__dict__`)
- **Potential issues to watch:**
  - `extra="ignore"` silently drops misspelled config keys — user won't know about typos
- **Suggestions for user:**
  - Consider logging a warning when extra fields are found, so users know about typos
- **Related areas that may need attention:**
  - Pre-existing: `tests/test_agent.py` has broken import (`CONVERSATION_INSTRUCTION` removed from agent.py)
  - Pre-existing: 5 test failures in test_cli.py and test_telegram.py related to streaming changes

## US-202: Add show_tool_activity config option
- **Date:** 2026-02-01
- **Additional test ideas:**
  - Integration test verifying app.py lifespan actually sets the value on TelegramChannel
- **Potential issues to watch:**
  - The setting is set after construction via attribute assignment — a constructor param would be cleaner
- **Suggestions for user:**
  - Consider validating channel settings keys to catch typos (e.g. `show_tool_activty`)

## US-203: Add --api-key flag to CLI agent.py
- **Date:** 2026-02-01
- **Additional test ideas:**
  - Test that health check also receives the header
  - Test interactive mode passes headers through
- **Potential issues to watch:**
  - API key is visible in process list (`ps aux`) — consider reading from env var as alternative
- **Suggestions for user:**
  - Consider also supporting `CLAUDE_BOT_API_KEY` env var as alternative to CLI flag

## US-204: Add ANSI color formatting to CLI
- **Date:** 2026-02-01
- **Additional test ideas:**
  - Test with mocked isatty() returning True to verify ANSI codes are present
- **Potential issues to watch:**
  - BOLD constant defined but not used yet — could apply to bot name in interactive mode
- **Suggestions for user:**
  - Consider a `--no-color` flag for users who want to force-disable colors on a TTY

## US-205: Persist conversation_id in CLI interactive mode
- **Date:** 2026-02-01
- **Additional test ideas:**
  - Integration test of interactive loop with mocked input/output
  - Test that --conversation flag takes precedence over auto-detected ID
- **Potential issues to watch:**
  - If server errors on first message, conversation_id stays None — subsequent messages create new conversations each time
- **Suggestions for user:**
  - Consider showing conversation name alongside ID

## US-206: Split long Telegram responses
- **Date:** 2026-02-01
- **Additional test ideas:**
  - Test with Markdown formatting to ensure splits don't break code blocks
  - Test with exactly 4096 * 2 + 1 characters
- **Potential issues to watch:**
  - Splitting inside a Markdown code block could break formatting
  - 0.3s delay between chunks means 10 chunks = 3s total delay
- **Suggestions for user:**
  - Consider Markdown-aware splitting that doesn't break code fences

## US-207: Add retry on connection drop during CLI streaming
- **Date:** 2026-02-01
- **Additional test ideas:**
  - Test RemoteProtocolError specifically (currently only tests ReadError)
- **Potential issues to watch:**
  - On retry, server starts fresh — may produce duplicate content since partial text was already displayed
  - No backoff delay between retries
- **Suggestions for user:**
  - Consider adding a small delay (e.g., 1s) between retries
