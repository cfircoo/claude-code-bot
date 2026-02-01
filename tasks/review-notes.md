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
