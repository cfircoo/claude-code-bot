# Ralph Test Log

## US-201: Add extra="ignore" to BotConfig
- **Date:** 2026-02-01
- **Tests created:**
  - `tests/test_config.py::test_bot_config_extra_fields_ignored` — verifies unknown YAML keys don't raise ValidationError
- **Tests modified:** None
- **Coverage notes:** All 8 config tests pass

## US-202: Add show_tool_activity config option
- **Date:** 2026-02-01
- **Tests created:**
  - `tests/test_telegram.py::test_show_tool_activity_default_false` — verifies default is False
  - `tests/test_telegram.py::test_show_tool_activity_set_from_settings` — verifies setting can be toggled
- **Tests modified:** None
- **Coverage notes:** All new tests pass; 3 pre-existing failures unchanged

## US-203: Add --api-key flag to CLI agent.py
- **Date:** 2026-02-01
- **Tests created:**
  - `tests/test_cli.py::TestSendStreaming::test_api_key_header_sent` — verifies X-API-Key header is passed to httpx.stream
- **Tests modified:** None
- **Coverage notes:** 12 of 14 CLI tests pass; 2 pre-existing failures
