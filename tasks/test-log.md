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

## US-106: Update Telegram channel with typing indicator and streaming status
- **Date:** 2026-02-01T14:30:00Z
- **Tests created:**
  - `tests/test_telegram.py::test_process_with_streaming_sends_typing_and_result` — typing action sent + result message delivered
  - `tests/test_telegram.py::test_process_with_streaming_shows_tool_activity` — tool names in response when show_tool_activity=True
  - `tests/test_telegram.py::test_process_with_streaming_error_event` — error events displayed to user
  - `tests/test_telegram.py::test_process_with_streaming_conversation_switched` — conversation switch shown
  - `tests/test_telegram.py::test_process_with_streaming_no_response` — "No response." fallback
- **Coverage notes:** Handler integration (handle_text calling _process_with_streaming) not directly tested — would require simulating aiogram dispatch.
