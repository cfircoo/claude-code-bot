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

## US-204: Add ANSI color formatting to CLI
- **Date:** 2026-02-01
- **Tests created:**
  - `tests/test_cli.py::TestAnsiColors::test_no_ansi_codes_when_not_tty` — verifies color constants are empty
  - `tests/test_cli.py::TestAnsiColors::test_tool_indicator_no_ansi_in_output` — no escape codes in tool output
  - `tests/test_cli.py::TestAnsiColors::test_error_no_ansi_in_output` — no escape codes in error output
- **Tests modified:** None
- **Coverage notes:** 16 of 18 tests pass; 2 pre-existing failures

## US-205: Persist conversation_id in CLI interactive mode
- **Date:** 2026-02-01
- **Tests created:**
  - `tests/test_cli.py::TestSendStreaming::test_send_streaming_returns_conversation_id`
  - `tests/test_cli.py::TestSendStreaming::test_send_streaming_returns_none_without_conversation_id`
- **Tests modified:** None
- **Coverage notes:** 18 of 20 tests pass; 2 pre-existing failures

## US-206: Split long Telegram responses
- **Date:** 2026-02-01
- **Tests created:**
  - `tests/test_telegram.py::TestSplitMessage::test_short_message_not_split`
  - `tests/test_telegram.py::TestSplitMessage::test_exact_limit_not_split`
  - `tests/test_telegram.py::TestSplitMessage::test_split_at_paragraph_boundary`
  - `tests/test_telegram.py::TestSplitMessage::test_split_at_newline`
  - `tests/test_telegram.py::TestSplitMessage::test_split_at_space`
  - `tests/test_telegram.py::TestSplitMessage::test_hard_cut_no_boundary`
  - `tests/test_telegram.py::TestSplitMessage::test_each_chunk_within_limit`
- **Coverage notes:** 18 of 21 telegram tests pass; 3 pre-existing failures

## US-207: Add retry on connection drop during CLI streaming
- **Date:** 2026-02-01
- **Tests created:**
  - `tests/test_cli.py::TestSendStreaming::test_retry_on_read_error` — verifies retry on ReadError with Reconnecting indicator
  - `tests/test_cli.py::TestSendStreaming::test_retry_exhausted` — verifies error after max retries
- **Coverage notes:** 20 of 22 CLI tests pass; 2 pre-existing failures

## US-208: Add thinking indicator for long Telegram runs
- **Date:** 2026-02-01
- **Tests created:**
  - `tests/test_telegram.py::test_thinking_threshold_default`
  - `tests/test_telegram.py::test_thinking_threshold_configurable`
  - `tests/test_telegram.py::test_fast_response_no_thinking_message`
- **Coverage notes:** 21 of 24 telegram tests pass; 3 pre-existing failures

## US-209: Add persistent memory system
- **Date:** 2026-02-01
- **Tests created:**
  - `tests/test_memory_store.py` — 13 tests covering auto-create, write, delete, core protection, path traversal, load, list
- **Coverage notes:** All 13 tests pass

## US-212: Add permission_mode and allowed_tools to config
- **Date:** 2026-02-01
- **Tests created:**
  - `tests/test_config.py::test_permission_mode_defaults`
  - `tests/test_config.py::test_permission_mode_valid_values`
  - `tests/test_config.py::test_permission_mode_invalid`
  - `tests/test_config.py::test_allowed_tools_from_config`
- **Coverage notes:** 12 config tests pass

## US-213: Add interactive tool permission via can_use_tool
- **Date:** 2026-02-01
- **Tests created:**
  - `tests/test_permissions.py` — 12 tests covering summarize, approval flows, timeout, deny, no notifier
- **Coverage notes:** All 12 permission tests pass
