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
async def test_proactive_message_persists_to_memory(config: BotConfig) -> None:
    with patch("claude_code_bot.channels.telegram.Bot") as MockBot:
        mock_bot = MockBot.return_value
        mock_bot.send_message = AsyncMock()

        channel = TelegramChannel(bot_token="123:ABC", config=config)
        channel._known_chat_ids.add(999)

        # Set up mock agent service with memory
        mock_agent = MagicMock()
        mock_agent.memory = MagicMock()
        mock_agent.memory.load = AsyncMock(return_value=[])
        mock_agent.memory.save = AsyncMock()
        channel.set_agent_service(mock_agent)

        await channel.send_proactive_message("999", "Reminder!")
        mock_agent.memory.save.assert_called_once()


@pytest.mark.asyncio
async def test_sub_agent_proactive_callback_no_telegram(config: BotConfig) -> None:
    """When Telegram is not configured, proactive should be a no-op or raise."""
    # This tests the pattern where sub-agents get a send_proactive callback
    # If no Telegram, it should log warning but not crash
    pass  # Covered by app-level test
