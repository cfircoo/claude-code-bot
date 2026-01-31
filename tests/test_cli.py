"""Tests for agent.py CLI tool."""

from __future__ import annotations

import json
import subprocess
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

# Import the CLI module
sys.path.insert(0, ".")
import agent as cli_module


class FakeStreamResponse:
    """Fake httpx streaming response for testing."""

    def __init__(self, events: list[dict], status_code: int = 200):
        self.status_code = status_code
        self._events = events
        self._text = ""

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def read(self):
        self._text = "error"

    @property
    def text(self):
        return self._text

    def iter_lines(self):
        for event in self._events:
            yield f"data: {json.dumps(event)}"


def _capture_send(events, debug=False, conversation_id=None):
    """Helper to capture stdout from send_streaming."""
    buf = StringIO()
    with patch("sys.stdout", buf):
        with patch("httpx.stream", return_value=FakeStreamResponse(events)):
            cli_module.send_streaming(
                "http://localhost:8010", "test-user", "hello", conversation_id, debug
            )
    return buf.getvalue()


class TestSendStreaming:
    def test_text_tokens_printed_incrementally(self):
        events = [
            {"type": "text", "content": "Hello"},
            {"type": "text", "content": " world"},
            {"type": "result", "content": "Hello world"},
        ]
        output = _capture_send(events)
        assert "Hello world" in output
        assert "Bot: Hello world" in output

    def test_tool_start_and_done(self):
        events = [
            {"type": "tool_start", "tool": "SearchFiles"},
            {"type": "tool_done", "tool": "SearchFiles"},
            {"type": "result", "content": "Done"},
        ]
        output = _capture_send(events)
        assert "[Using SearchFiles...]" in output
        assert "done" in output

    def test_subagent_activity_indented(self):
        events = [
            {"type": "tool_start", "tool": "SubTask", "parent_tool_use_id": "abc123"},
            {"type": "tool_done", "tool": "SubTask"},
            {"type": "result", "content": "Done"},
        ]
        output = _capture_send(events)
        assert "↳" in output
        assert "[Using SubTask...]" in output

    def test_error_event(self):
        events = [
            {"type": "error", "content": "Something broke"},
        ]
        output = _capture_send(events)
        assert "Error: Something broke" in output

    def test_conversation_switched_event(self):
        events = [
            {"type": "conversation_switched", "conversation_id": "conv-123"},
            {"type": "result", "content": "Switched"},
        ]
        output = _capture_send(events)
        assert "conv-123" in output
        assert "Switched to conversation" in output

    def test_debug_mode_shows_raw_events(self):
        events = [
            {"type": "text", "content": "Hi"},
            {"type": "result", "content": "Hi"},
        ]
        output = _capture_send(events, debug=True)
        assert "[event]" in output
        assert "[request]" in output

    def test_http_error_status(self):
        buf = StringIO()
        resp = FakeStreamResponse([], status_code=400)
        with patch("sys.stdout", buf):
            with patch("httpx.stream", return_value=resp):
                cli_module.send_streaming(
                    "http://localhost:8010", "test-user", "hello", None, False
                )
        assert "Error (400)" in buf.getvalue()

    def test_connection_error(self):
        buf = StringIO()
        with patch("sys.stdout", buf):
            with patch("httpx.stream", side_effect=httpx_connect_error()):
                cli_module.send_streaming(
                    "http://localhost:8010", "test-user", "hello", None, False
                )
        assert "Connection lost" in buf.getvalue()

    def test_conversation_id_passed_in_payload(self):
        """Verify conversation_id is included in the request payload."""
        events = [{"type": "result", "content": "ok"}]
        calls = []

        original_stream = FakeStreamResponse(events)

        class CapturingStream:
            def __init__(self, method, url, **kwargs):
                calls.append(kwargs.get("json", {}))
                self._inner = original_stream

            def __enter__(self):
                return self._inner

            def __exit__(self, *args):
                pass

        with patch("sys.stdout", StringIO()):
            with patch("httpx.stream", CapturingStream):
                cli_module.send_streaming(
                    "http://localhost:8010", "test-user", "hello", "conv-abc", False
                )

        assert len(calls) == 1
        assert calls[0]["conversation_id"] == "conv-abc"

    def test_bad_json_in_sse_stream(self):
        """Malformed JSON in SSE stream should be skipped gracefully."""
        class BadJsonResponse(FakeStreamResponse):
            def iter_lines(self):
                yield "data: not-json"
                yield f"data: {json.dumps({'type': 'result', 'content': 'ok'})}"

        buf = StringIO()
        with patch("sys.stdout", buf):
            with patch("httpx.stream", return_value=BadJsonResponse([])):
                cli_module.send_streaming(
                    "http://localhost:8010", "test-user", "hello", None, False
                )
        assert "Bot: ok" in buf.getvalue()


class TestMainArgparse:
    def test_help_output(self):
        """--help should mention --conversation flag."""
        result = subprocess.run(
            [sys.executable, "agent.py", "--help"],
            capture_output=True, text=True,
        )
        assert result.returncode == 0
        assert "--conversation" in result.stdout

    def test_debug_flag_in_help(self):
        result = subprocess.run(
            [sys.executable, "agent.py", "--help"],
            capture_output=True, text=True,
        )
        assert "--debug" in result.stdout

    def test_interactive_flag_in_help(self):
        result = subprocess.run(
            [sys.executable, "agent.py", "--help"],
            capture_output=True, text=True,
        )
        assert "--interactive" in result.stdout


def httpx_connect_error():
    """Create an httpx.ConnectError for testing."""
    import httpx
    return httpx.ConnectError("Connection refused")
