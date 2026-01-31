"""Telegram channel adapter using aiogram."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.types import Message as TelegramMessage

if TYPE_CHECKING:
    from claude_code_bot.agent import AgentService
    from claude_code_bot.config import BotConfig

logger = structlog.get_logger()

TYPING_INTERVAL = 4.0  # seconds between typing indicator refreshes


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
        self.show_tool_activity: bool = False

        self._register_handlers()

    def set_agent_service(self, agent_service: AgentService) -> None:
        """Set the agent service for processing messages."""
        self._agent_service = agent_service

    async def _send_typing_loop(self, chat_id: int, stop_event: asyncio.Event) -> None:
        """Send typing action periodically until stop_event is set."""
        while not stop_event.is_set():
            try:
                await self.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=TYPING_INTERVAL)
                break
            except asyncio.TimeoutError:
                pass

    async def _process_with_streaming(
        self, chat_id: int, user_message: str, message: TelegramMessage
    ) -> None:
        """Process a message using chat_stream with typing indicators."""
        assert self._agent_service is not None

        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(self._send_typing_loop(chat_id, stop_typing))

        text_parts: list[str] = []
        tool_activities: list[str] = []

        try:
            async for event in self._agent_service.chat_stream(
                user_id=str(chat_id), message=user_message
            ):
                event_type = event.get("type", "")

                if event_type == "text":
                    text_parts.append(event.get("content", ""))
                elif event_type == "error":
                    text_parts.append(f"Error: {event.get('content', 'unknown error')}")
                elif event_type == "tool_start" and self.show_tool_activity:
                    tool_activities.append(event.get("tool", ""))
                elif event_type == "conversation_switched":
                    cid = event.get("conversation_id", "")
                    tool_activities.append(f"Switched to conversation {cid}")
        finally:
            stop_typing.set()
            await typing_task

        # Build response
        response_parts: list[str] = []
        if self.show_tool_activity and tool_activities:
            status_line = "Used: " + ", ".join(tool_activities)
            response_parts.append(status_line)
        result_text = "".join(text_parts)
        if result_text:
            response_parts.append(result_text)

        final = "\n\n".join(response_parts) if response_parts else "No response."
        await message.answer(final)

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
                    await self._process_with_streaming(chat_id, "/start", message)
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

            await self._process_with_streaming(chat_id, message.text, message)

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



    async def start_polling(self) -> None:
        """Start long-polling for Telegram updates."""
        logger.info("telegram_polling_started")
        await self.dp.start_polling(self.bot)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        await self.bot.session.close()
