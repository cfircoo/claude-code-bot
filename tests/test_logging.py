"""Tests for structured logging setup."""

from claude_code_bot.logging import setup_logging


def test_setup_logging_does_not_raise() -> None:
    setup_logging()


def test_setup_logging_custom_level() -> None:
    setup_logging(log_level="DEBUG")
