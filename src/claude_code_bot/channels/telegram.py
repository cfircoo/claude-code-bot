"""Telegram channel adapter using aiogram."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import structlog
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message as TelegramMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from claude_code_bot.agent import AgentService
    from claude_code_bot.config import BotConfig
    from claude_code_bot.permissions import PermissionManager

logger = structlog.get_logger()

TYPING_INTERVAL = 4.0  # seconds between typing indicator refreshes
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
SPLIT_DELAY = 0.3  # seconds between split messages


def split_message(text: str, max_len: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> list[str]:
    """Split text into chunks of at most max_len characters.

    Prefers splitting at paragraph boundaries (double newline), then single
    newline, then space. Falls back to hard cut if no boundary found.
    """
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    while text:
        if len(text) <= max_len:
            chunks.append(text)
            break

        # Try split boundaries in preference order
        cut = -1
        for sep in ("\n\n", "\n", " "):
            idx = text.rfind(sep, 0, max_len)
            if idx > 0:
                cut = idx + len(sep)
                break

        if cut <= 0:
            cut = max_len

        chunks.append(text[:cut])
        text = text[cut:]

    return chunks


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
        self.thinking_threshold: float = 10.0
        self._permission_manager: PermissionManager | None = None

        self._register_handlers()

    def set_agent_service(self, agent_service: AgentService) -> None:
        """Set the agent service for processing messages."""
        self._agent_service = agent_service

    def set_permission_manager(self, manager: PermissionManager) -> None:
        """Set the permission manager and register as notifier."""
        self._permission_manager = manager
        manager.set_notifier(self._send_permission_prompt)

    async def _send_permission_prompt(
        self, request_id: str, tool_name: str, summary: str
    ) -> None:
        """Send an inline keyboard permission prompt to all known chats."""
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="✅ Yes", callback_data=f"perm:yes:{request_id}"
                    ),
                    InlineKeyboardButton(
                        text="❌ No", callback_data=f"perm:no:{request_id}"
                    ),
                ]
            ]
        )
        text = f"Allow {tool_name}?\n{summary}"
        for chat_id in self._known_chat_ids:
            try:
                await self.bot.send_message(
                    chat_id=chat_id, text=text, reply_markup=keyboard
                )
            except Exception:
                pass

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
        thinking_msg: TelegramMessage | None = None

        async def _send_thinking() -> None:
            nonlocal thinking_msg
            await asyncio.sleep(self.thinking_threshold)
            try:
                thinking_msg = await message.answer("Thinking...")
            except Exception:
                pass

        thinking_task = asyncio.create_task(_send_thinking())

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
            thinking_task.cancel()
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
        chunks = split_message(final)

        for i, chunk in enumerate(chunks):
            if i == 0 and thinking_msg is not None:
                # Edit the thinking message with the first chunk
                try:
                    await thinking_msg.edit_text(chunk)
                except Exception:
                    await message.answer(chunk)
            else:
                await message.answer(chunk)
            if i < len(chunks) - 1:
                await asyncio.sleep(SPLIT_DELAY)

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

        @self.dp.callback_query(F.data.startswith("perm:"))
        async def handle_permission_callback(callback: CallbackQuery) -> None:
            if callback.data is None:
                return
            parts = callback.data.split(":", 2)
            if len(parts) != 3:
                return
            _, decision, request_id = parts
            approved = decision == "yes"
            if self._permission_manager:
                self._permission_manager.resolve(request_id, approved)
            status = "Approved" if approved else "Denied"
            await callback.answer(status)
            if callback.message:
                try:
                    await callback.message.edit_text(  # type: ignore[union-attr]
                        f"{callback.message.text}\n\n→ {status}"  # type: ignore[union-attr]
                    )
                except Exception:
                    pass

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
