# Ralph Test Log

## US-105: Update CLI agent.py with streaming display
- **Date:** 2026-02-01T14:00:00Z
- **Tests created:**
  - `tests/test_cli.py::TestSendStreaming::test_text_tokens_printed_incrementally` — text tokens arrive and print without buffering
  - `tests/test_cli.py::TestSendStreaming::test_tool_start_and_done` — tool use indicators shown correctly
  - `tests/test_cli.py::TestSendStreaming::test_subagent_activity_indented` — subagent activity with ↳ prefix
  - `tests/test_cli.py::TestSendStreaming::test_error_event` — error events displayed
  - `tests/test_cli.py::TestSendStreaming::test_conversation_switched_event` — conversation switch notification
  - `tests/test_cli.py::TestSendStreaming::test_debug_mode_shows_raw_events` — debug flag shows raw SSE
  - `tests/test_cli.py::TestSendStreaming::test_http_error_status` — HTTP error handling
  - `tests/test_cli.py::TestSendStreaming::test_connection_error` — connection error handling
  - `tests/test_cli.py::TestSendStreaming::test_conversation_id_passed_in_payload` — conversation_id in request
  - `tests/test_cli.py::TestSendStreaming::test_bad_json_in_sse_stream` — malformed JSON gracefully skipped
  - `tests/test_cli.py::TestMainArgparse::test_help_output` — --conversation in help
  - `tests/test_cli.py::TestMainArgparse::test_debug_flag_in_help` — --debug in help
  - `tests/test_cli.py::TestMainArgparse::test_interactive_flag_in_help` — -i in help
- **Coverage notes:** All event types covered. Interactive mode not tested (requires stdin mocking).
