"""Telegram channel adapter using aiogram."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message as TelegramMessage

if TYPE_CHECKING:
    from claude_code_bot.agent import AgentService
    from claude_code_bot.config import BotConfig

logger = structlog.get_logger()


class UserNotReachableError(Exception):
    """Raised when attempting to send a proactive message to an unknown user."""


class TelegramChannel:
    """Telegram bot adapter."""

    def __init__(self, bot_token: str, config: BotConfig) -> None:
        if not bot_token:
            raise ValueError("Invalid Telegram bot token")
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.config = config
        self._agent_service: AgentService | None = None
        self._known_chat_ids: set[int] = set()
        self._greeted_users: set[int] = set()

        self._register_handlers()

    def set_agent_service(self, agent_service: AgentService) -> None:
        """Set the agent service for processing messages."""
        self._agent_service = agent_service

    def _register_handlers(self) -> None:
        """Register message handlers."""

        @self.dp.message(Command("start"))
        async def handle_start(message: TelegramMessage) -> None:
            if message.chat is None or message.from_user is None:
                return
            chat_id = message.chat.id
            self._known_chat_ids.add(chat_id)

            if chat_id not in self._greeted_users:
                self._greeted_users.add(chat_id)
                greeting = self.config.persona.greeting
                if greeting:
                    await message.answer(greeting)
                elif self._agent_service:
                    response = await self._agent_service.chat(
                        user_id=str(chat_id),
                        message="/start",
                        channel="telegram",
                    )
                    await message.answer(response)
                else:
                    await message.answer(
                        f"Hello! I'm {self.config.persona.name}."
                    )

        @self.dp.message(F.text)
        async def handle_text(message: TelegramMessage) -> None:
            if message.chat is None or message.text is None:
                return
            chat_id = message.chat.id
            self._known_chat_ids.add(chat_id)

            if self._agent_service is None:
                await message.answer("Bot is still starting up...")
                return

            response = await self._agent_service.chat(
                user_id=str(chat_id),
                message=message.text,
                channel="telegram",
            )
            await message.answer(response)

    async def send_proactive_message(self, user_id: str, text: str) -> None:
        """Send a message to a user without a prior trigger.

        Args:
            user_id: The Telegram chat ID as a string.
            text: The message text to send.

        Raises:
            UserNotReachableError: If the user has never interacted with the bot.
        """
        chat_id = int(user_id)
        if chat_id not in self._known_chat_ids:
            logger.warning("proactive_message_user_not_reachable", user_id=user_id)
            raise UserNotReachableError(
                f"User {user_id} has never interacted with the bot"
            )

        await self.bot.send_message(chat_id=chat_id, text=text)
        logger.info("proactive_message_sent", user_id=user_id)

        # Note: conversation persistence will be handled via ConversationStore in US-106

    async def start_polling(self) -> None:
        """Start long-polling for Telegram updates."""
        logger.info("telegram_polling_started")
        await self.dp.start_polling(self.bot)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        await self.bot.session.close()
