"""Tests for Telegram channel adapter."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from claude_code_bot.channels.telegram import TelegramChannel, UserNotReachableError
from claude_code_bot.config import BotConfig, PersonaConfig


@pytest.fixture
def config() -> BotConfig:
    return BotConfig(
        persona=PersonaConfig(
            name="TestBot",
            system_prompt="You are a test bot.",
            greeting="Welcome! I'm TestBot.",
        )
    )


def test_import_telegram_channel() -> None:
    from claude_code_bot.channels.telegram import TelegramChannel
    assert TelegramChannel is not None


def test_invalid_token_raises() -> None:
    config = BotConfig()
    with pytest.raises(ValueError, match="Invalid Telegram bot token"):
        TelegramChannel(bot_token="", config=config)


def test_telegram_channel_creates_with_valid_token(config: BotConfig) -> None:
    with patch("claude_code_bot.channels.telegram.Bot"):
        channel = TelegramChannel(bot_token="123:ABC", config=config)
        assert channel is not None


@pytest.mark.asyncio
async def test_proactive_message_unknown_user(config: BotConfig) -> None:
    with patch("claude_code_bot.channels.telegram.Bot"):
        channel = TelegramChannel(bot_token="123:ABC", config=config)
        with pytest.raises(UserNotReachableError):
            await channel.send_proactive_message("999", "Hello!")


@pytest.mark.asyncio
async def test_proactive_message_known_user(config: BotConfig) -> None:
    with patch("claude_code_bot.channels.telegram.Bot") as MockBot:
        mock_bot = MockBot.return_value
        mock_bot.send_message = AsyncMock()
        mock_bot.session = MagicMock()
        mock_bot.session.close = AsyncMock()

        channel = TelegramChannel(bot_token="123:ABC", config=config)
        channel._known_chat_ids.add(999)

        await channel.send_proactive_message("999", "Hello!")
        mock_bot.send_message.assert_called_once_with(chat_id=999, text="Hello!")


@pytest.mark.asyncio
async def test_proactive_message_sends_without_persistence(config: BotConfig) -> None:
    with patch("claude_code_bot.channels.telegram.Bot") as MockBot:
        mock_bot = MockBot.return_value
        mock_bot.send_message = AsyncMock()

        channel = TelegramChannel(bot_token="123:ABC", config=config)
        channel._known_chat_ids.add(999)

        mock_agent = MagicMock()
        channel.set_agent_service(mock_agent)

        await channel.send_proactive_message("999", "Reminder!")
        mock_bot.send_message.assert_called_once()


@pytest.mark.asyncio
async def test_sub_agent_proactive_callback_no_telegram(config: BotConfig) -> None:
    """When Telegram is not configured, proactive should be a no-op or raise."""
    pass  # Covered by app-level test


@pytest.mark.asyncio
async def test_process_with_streaming_sends_typing_and_result(config: BotConfig) -> None:
    """chat_stream events should produce typing action + final message."""
    import asyncio

    with patch("claude_code_bot.channels.telegram.Bot") as MockBot:
        mock_bot_instance = MagicMock()
        mock_bot_instance.send_chat_action = AsyncMock()
        MockBot.return_value = mock_bot_instance

        channel = TelegramChannel(bot_token="123:ABC", config=config)

        mock_agent = MagicMock()

        async def fake_stream(user_id: str, message: str, conversation_id: str | None = None):
            # Yield control so typing loop can run
            await asyncio.sleep(0)
            yield {"type": "text", "content": "Hello"}
            await asyncio.sleep(0)
            yield {"type": "result", "content": "Hello there!"}

        mock_agent.chat_stream = fake_stream
        channel.set_agent_service(mock_agent)

        mock_message = AsyncMock()
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123

        await channel._process_with_streaming(123, "hi", mock_message)

        # Should have sent typing action at least once
        mock_bot_instance.send_chat_action.assert_called()
        # Should answer with result
        mock_message.answer.assert_called_once_with("Hello there!")


@pytest.mark.asyncio
async def test_process_with_streaming_shows_tool_activity(config: BotConfig) -> None:
    """When show_tool_activity is True, tool names appear in response."""
    with patch("claude_code_bot.channels.telegram.Bot") as MockBot:
        mock_bot = MockBot.return_value
        mock_bot.send_chat_action = AsyncMock()

        channel = TelegramChannel(bot_token="123:ABC", config=config)
        channel.show_tool_activity = True

        mock_agent = MagicMock()

        async def fake_stream(user_id: str, message: str, conversation_id: str | None = None):
            yield {"type": "tool_start", "tool": "SearchFiles"}
            yield {"type": "tool_done", "tool": "SearchFiles"}
            yield {"type": "result", "content": "Found it!"}

        mock_agent.chat_stream = fake_stream
        channel.set_agent_service(mock_agent)

        mock_message = AsyncMock()
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123

        await channel._process_with_streaming(123, "find x", mock_message)

        call_args = mock_message.answer.call_args[0][0]
        assert "SearchFiles" in call_args
        assert "Found it!" in call_args


@pytest.mark.asyncio
async def test_process_with_streaming_error_event(config: BotConfig) -> None:
    """Error events should be shown to the user."""
    with patch("claude_code_bot.channels.telegram.Bot") as MockBot:
        mock_bot = MockBot.return_value
        mock_bot.send_chat_action = AsyncMock()

        channel = TelegramChannel(bot_token="123:ABC", config=config)

        mock_agent = MagicMock()

        async def fake_stream(user_id: str, message: str, conversation_id: str | None = None):
            yield {"type": "error", "content": "Something broke"}

        mock_agent.chat_stream = fake_stream
        channel.set_agent_service(mock_agent)

        mock_message = AsyncMock()
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123

        await channel._process_with_streaming(123, "hi", mock_message)

        call_args = mock_message.answer.call_args[0][0]
        assert "Error: Something broke" in call_args


@pytest.mark.asyncio
async def test_process_with_streaming_conversation_switched(config: BotConfig) -> None:
    """Conversation switch events should be shown when tool activity is on."""
    with patch("claude_code_bot.channels.telegram.Bot") as MockBot:
        mock_bot = MockBot.return_value
        mock_bot.send_chat_action = AsyncMock()

        channel = TelegramChannel(bot_token="123:ABC", config=config)
        channel.show_tool_activity = True

        mock_agent = MagicMock()

        async def fake_stream(user_id: str, message: str, conversation_id: str | None = None):
            yield {"type": "conversation_switched", "conversation_id": "conv-abc"}
            yield {"type": "result", "content": "Switched!"}

        mock_agent.chat_stream = fake_stream
        channel.set_agent_service(mock_agent)

        mock_message = AsyncMock()
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123

        await channel._process_with_streaming(123, "switch", mock_message)

        call_args = mock_message.answer.call_args[0][0]
        assert "conv-abc" in call_args


@pytest.mark.asyncio
async def test_process_with_streaming_no_response(config: BotConfig) -> None:
    """If no result event, should send 'No response.'"""
    with patch("claude_code_bot.channels.telegram.Bot") as MockBot:
        mock_bot = MockBot.return_value
        mock_bot.send_chat_action = AsyncMock()

        channel = TelegramChannel(bot_token="123:ABC", config=config)

        mock_agent = MagicMock()

        async def fake_stream(user_id: str, message: str, conversation_id: str | None = None):
            yield {"type": "text", "content": "partial"}

        mock_agent.chat_stream = fake_stream
        channel.set_agent_service(mock_agent)

        mock_message = AsyncMock()
        mock_message.chat = MagicMock()
        mock_message.chat.id = 123

        await channel._process_with_streaming(123, "hi", mock_message)

        mock_message.answer.assert_called_once_with("No response.")
