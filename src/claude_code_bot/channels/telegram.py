"""Telegram channel adapter using aiogram."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

import structlog
from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatAction

from aiogram.types import BotCommand, CallbackQuery, Message as TelegramMessage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

if TYPE_CHECKING:
    from claude_code_bot.agent import AgentService
    from claude_code_bot.config import BotConfig
    from claude_code_bot.hooks import HookManager
    from claude_code_bot.hooks.telegram_auth import TelegramAuthGuard
    from claude_code_bot.permissions import PermissionManager

logger = structlog.get_logger()

TYPING_INTERVAL = 4.0  # seconds between typing indicator refreshes
TELEGRAM_MAX_MESSAGE_LENGTH = 4096
SPLIT_DELAY = 0.3  # seconds between split messages

# Bot-level commands handled locally (never reach the SDK)
BOT_COMMANDS = {
    "/start": "Start the bot",
    "/info": "Show bot info and usage stats",
    "/status": "Alias for /info",
    "/commands": "Show all available commands",
    "/cost": "Show API usage costs",
    "/model": "Switch AI model",
    "/skills": "List available API skills",
    "/hooks": "List active SDK hooks",
}

# SDK built-in commands (forwarded to SDK as prompt)
SDK_COMMANDS = {
    "/compact": "Summarize history to save tokens",
    "/clear": "Reset conversation and clear context",
}

DEFAULT_MODELS = {
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
    "haiku": "claude-haiku-3-5-20241022",
    "sonnet-3.5": "claude-3-5-sonnet-20241022",
}



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

    def __init__(
        self,
        bot_token: str,
        config: BotConfig,
        hook_manager: HookManager | None = None,
    ) -> None:
        if not bot_token:
            raise ValueError("Invalid Telegram bot token")
        self.bot = Bot(token=bot_token)
        self.dp = Dispatcher()
        self.config = config
        self._agent_service: AgentService | None = None
        self._known_chat_ids: set[int] = set()
        self._greeted_users: set[int] = set()
        self._start_time: float = __import__("time").time()
        self.show_tool_activity: bool = False
        self.thinking_threshold: float = 10.0
        self._permission_manager: PermissionManager | None = None
        self._hook_manager: HookManager | None = hook_manager
        self._auth_guard: TelegramAuthGuard | None = None

        self._register_handlers()

    def set_agent_service(self, agent_service: AgentService) -> None:
        """Set the agent service for processing messages."""
        self._agent_service = agent_service

    def set_auth_guard(self, guard: TelegramAuthGuard) -> None:
        """Set the auth guard for user authorization."""
        self._auth_guard = guard

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

    @staticmethod
    def _extract_metadata(message: TelegramMessage) -> dict:
        """Extract user and chat metadata from a Telegram message."""
        meta: dict = {
            "channel": "telegram",
            "chat_id": message.chat.id if message.chat else None,
            "chat_type": message.chat.type if message.chat else None,
        }
        if message.from_user:
            meta["user_id"] = message.from_user.id
            meta["username"] = message.from_user.username
            meta["first_name"] = message.from_user.first_name
            meta["last_name"] = message.from_user.last_name
            meta["language_code"] = message.from_user.language_code
            meta["is_bot"] = message.from_user.is_bot
        return meta

    async def _process_with_streaming(
        self, chat_id: int, user_message: str, message: TelegramMessage
    ) -> None:
        """Process a message using chat_stream with typing indicators."""
        assert self._agent_service is not None

        stop_typing = asyncio.Event()
        typing_task = asyncio.create_task(self._send_typing_loop(chat_id, stop_typing))

        text_parts: list[str] = []
        tool_activities: list[str] = []
        usage_info: dict = {}
        thinking_msg: TelegramMessage | None = None

        async def _send_thinking() -> None:
            nonlocal thinking_msg
            await asyncio.sleep(self.thinking_threshold)
            try:
                thinking_msg = await message.answer("Thinking...")
            except Exception:
                pass

        thinking_task = asyncio.create_task(_send_thinking())

        metadata = self._extract_metadata(message)
        logger.debug("telegram_message_received", user_message=user_message, **metadata)

        try:
            async for event in self._agent_service.chat_stream(
                user_id=str(chat_id), message=user_message, metadata=metadata
            ):
                event_type = event.get("type", "")

                if event_type == "text":
                    text_parts.append(event.get("content", ""))
                elif event_type == "error":
                    text_parts.append(f"Error: {event.get('content', 'unknown error')}")
                elif event_type == "tool_start" and self.show_tool_activity:
                    tool_activities.append(event.get("tool", ""))
                elif event_type == "result":
                    usage_info = event.get("usage", {})
                    usage_info["conversation_id"] = event.get("conversation_id", "")
                elif event_type == "conversation_switched":
                    cid = event.get("conversation_id", "")
                    tool_activities.append(f"Switched to conversation {cid}")
        finally:
            thinking_task.cancel()
            stop_typing.set()
            await typing_task

        logger.debug("telegram_usage_info", chat_id=chat_id, usage_info=usage_info)

        # Build response
        response_parts: list[str] = []
        if self.show_tool_activity and tool_activities:
            status_line = "Used: " + ", ".join(tool_activities)
            response_parts.append(status_line)
        result_text = "".join(text_parts)
        if result_text:
            response_parts.append(result_text)

        # Add usage footer
        if usage_info:
            parts = []
            inp = usage_info.get("input_tokens", 0)
            out = usage_info.get("output_tokens", 0)
            if inp or out:
                def _fmt(n: int) -> str:
                    return f"{n/1000:.1f}k" if n >= 1000 else str(n)
                parts.append(f"tokens: {_fmt(inp)}↑ {_fmt(out)}↓")
            cost = usage_info.get("cost_usd")
            if cost:
                parts.append(f"${cost:.4f}")
            duration = usage_info.get("duration_ms")
            if duration:
                parts.append(f"{duration/1000:.1f}s")
            conv_id = usage_info.get("conversation_id", "")
            if conv_id:
                parts.append(f"conv: {conv_id[:8]}")
            if parts:
                response_parts.append("─ " + " · ".join(parts))

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

        @self.dp.message(F.text)
        async def handle_text(message: TelegramMessage) -> None:
            if message.chat is None or message.text is None:
                return

            # Auth check — block unauthorized users
            if self._auth_guard and message.from_user:
                if not self._auth_guard.is_authorized(
                    message.from_user.id, message.from_user.username
                ):
                    logger.warning(
                        "telegram_unauthorized",
                        user_id=message.from_user.id,
                        username=message.from_user.username,
                    )
                    await message.answer(self._auth_guard.deny_message)
                    return

            chat_id = message.chat.id
            self._known_chat_ids.add(chat_id)

            text = message.text.strip()

            # Handle commands
            if text.startswith("/"):
                cmd = text.split()[0].split("@")[0].lower()  # strip @botname

                # Bot commands — handled locally
                if cmd == "/start":
                    await self._handle_start(message)
                    return
                if cmd in ("/info", "/status"):
                    await self._handle_status(message)
                    return
                if cmd == "/commands":
                    await self._handle_help(message)
                    return
                if cmd == "/cost":
                    await self._handle_cost(message)
                    return
                if cmd in ("/model", "/models"):
                    await self._handle_model(message)
                    return
                if cmd == "/skills":
                    await self._handle_skills(message)
                    return
                if cmd == "/hooks":
                    await self._handle_hooks(message)
                    return

                # SDK commands — forward to agent as-is
                if cmd in SDK_COMMANDS:
                    if self._agent_service is None:
                        await message.answer("Bot is still starting up...")
                        return
                    await self._process_with_streaming(chat_id, text, message)
                    return

                # Custom slash commands — forward to agent as-is
                if self._agent_service is None:
                    await message.answer("Bot is still starting up...")
                    return
                await self._process_with_streaming(chat_id, text, message)
                return

            if self._agent_service is None:
                await message.answer("Bot is still starting up...")
                return

            await self._process_with_streaming(chat_id, text, message)

        def _check_callback_auth(callback: CallbackQuery) -> bool:
            """Return True if user is authorized (or no guard set)."""
            if not self._auth_guard:
                return True
            if callback.from_user:
                return self._auth_guard.is_authorized(
                    callback.from_user.id, callback.from_user.username
                )
            return False

        @self.dp.callback_query(F.data.startswith("model:"))
        async def handle_model_callback(callback: CallbackQuery) -> None:
            if callback.data is None or not _check_callback_auth(callback):
                return
            model_id = callback.data.split(":", 1)[1]
            self.config.model = model_id
            await callback.answer(f"Switched to {model_id}")
            if callback.message:
                try:
                    await callback.message.edit_text(  # type: ignore[union-attr]
                        f"Model switched to `{model_id}`",
                        parse_mode="Markdown",
                    )
                except Exception:
                    pass

        @self.dp.callback_query(F.data.startswith("skill:"))
        async def handle_skill_callback(callback: CallbackQuery) -> None:
            if callback.data is None or not _check_callback_auth(callback):
                return
            skill_id = callback.data.split(":", 1)[1]
            await callback.answer("Loading skill details...")
            skill = await self._fetch_skill(skill_id)
            if not skill:
                if callback.message:
                    try:
                        await callback.message.answer("Could not fetch skill details.")  # type: ignore[union-attr]
                    except Exception:
                        pass
                return
            title = skill.get("display_title", skill.get("id", "?"))
            source = skill.get("source", "unknown")
            version = skill.get("latest_version", "—")
            created = skill.get("created_at", "—")
            updated = skill.get("updated_at", "—")
            # Format timestamps (trim to date)
            if created and "T" in created:
                created = created.split("T")[0]
            if updated and "T" in updated:
                updated = updated.split("T")[0]
            lines = [
                f"🛠 *{title}*",
                "",
                f"*ID:* `{skill.get('id', '—')}`",
                f"*Source:* {source}",
                f"*Version:* `{version}`",
                f"*Created:* {created}",
                f"*Updated:* {updated}",
            ]
            if callback.message:
                try:
                    await callback.message.answer(  # type: ignore[union-attr]
                        "\n".join(lines), parse_mode="Markdown"
                    )
                except Exception:
                    pass

        @self.dp.callback_query(F.data.startswith("hook:"))
        async def handle_hook_callback(callback: CallbackQuery) -> None:
            if callback.data is None or not _check_callback_auth(callback):
                return
            idx_str = callback.data.split(":", 1)[1]
            try:
                idx = int(idx_str)
            except ValueError:
                return
            await callback.answer("Loading hook details...")
            if not self._hook_manager:
                return
            hooks = self._hook_manager.list_hooks()
            if idx < 0 or idx >= len(hooks):
                return
            h = hooks[idx]
            lines = [
                f"🪝 *Hook #{idx + 1}*",
                "",
                f"*Event:* `{h['event']}`",
                f"*Matcher:* `{h['matcher']}`",
                f"*Name:* `{h['name']}`",
                f"*Timeout:* {h['timeout']}s",
            ]
            if callback.message:
                try:
                    await callback.message.answer(  # type: ignore[union-attr]
                        "\n".join(lines), parse_mode="Markdown"
                    )
                except Exception:
                    pass

        @self.dp.callback_query(F.data.startswith("perm:"))
        async def handle_permission_callback(callback: CallbackQuery) -> None:
            if callback.data is None or not _check_callback_auth(callback):
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



    async def _fetch_models(self) -> dict[str, str]:
        """Fetch available models from Anthropic API. Falls back to defaults."""
        import httpx

        api_key = (
            self.config.api_keys.anthropic_api_key
            or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        if not api_key:
            return DEFAULT_MODELS

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/models",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                    },
                    params={"limit": 50},
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                # Build alias -> id mapping
                models: dict[str, str] = {}
                for m in data:
                    model_id = m["id"]
                    display = m.get("display_name", model_id)
                    # Create short alias from display name
                    alias = display.lower().replace(" ", "-")
                    models[alias] = model_id
                return models if models else DEFAULT_MODELS
        except Exception:
            logger.debug("models_api_fetch_failed", exc_info=True)
            return DEFAULT_MODELS

    async def _handle_model(self, message: TelegramMessage) -> None:
        """Handle /model — show buttons or switch model."""
        if message.text is None:
            return
        parts = message.text.strip().split(maxsplit=1)

        if len(parts) == 1:
            # No argument — fetch models and show inline keyboard
            models = await self._fetch_models()
            current = self.config.model
            buttons = []
            for alias, model_id in models.items():
                check = "✓ " if model_id == current else ""
                label = f"{check}{alias}"
                # callback_data max 64 bytes, use model_id directly
                cb_data = f"model:{model_id}"
                if len(cb_data) <= 64:
                    buttons.append(InlineKeyboardButton(text=label, callback_data=cb_data))
            # 2 buttons per row
            rows = [buttons[i:i+2] for i in range(0, len(buttons), 2)]
            keyboard = InlineKeyboardMarkup(inline_keyboard=rows)
            await message.answer(
                f"*Current model:* `{current}`\nSelect a model:",
                parse_mode="Markdown",
                reply_markup=keyboard,
            )
            return

        choice = parts[1].strip().lower()
        # Try as alias first, then as direct model ID
        models = await self._fetch_models()
        model_id = models.get(choice, DEFAULT_MODELS.get(choice, choice))
        self.config.model = model_id
        await message.answer(f"Model switched to `{model_id}`", parse_mode="Markdown")

    async def _fetch_skills(self) -> list[dict]:
        """Fetch available skills from Anthropic API."""
        import httpx

        api_key = (
            self.config.api_keys.anthropic_api_key
            or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        if not api_key:
            return []

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.anthropic.com/v1/skills",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "anthropic-beta": "skills-2025-10-02",
                    },
                    params={"limit": 100},
                    timeout=10,
                )
                resp.raise_for_status()
                return resp.json().get("data", [])
        except Exception:
            logger.debug("skills_api_fetch_failed", exc_info=True)
            return []

    async def _fetch_skill(self, skill_id: str) -> dict | None:
        """Fetch a single skill by ID from the Anthropic API."""
        import httpx

        api_key = (
            self.config.api_keys.anthropic_api_key
            or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        if not api_key:
            return None

        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.anthropic.com/v1/skills/{skill_id}",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "anthropic-beta": "skills-2025-10-02",
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                return resp.json()
        except Exception:
            logger.debug("skill_api_fetch_failed", skill_id=skill_id, exc_info=True)
            return None

    async def _handle_skills(self, message: TelegramMessage) -> None:
        """Handle /skills — list available API skills with detail buttons."""
        skills = await self._fetch_skills()
        if not skills:
            await message.answer("No skills found (API key may be missing or no skills available).")
            return

        lines = ["🛠 *Available Skills*", ""]
        buttons = []
        for s in skills:
            title = s.get("display_title", s.get("id", "?"))
            source = s.get("source", "")
            tag = f" ({source})" if source else ""
            lines.append(f"• *{title}*{tag}")
            skill_id = s.get("id", "")
            cb_data = f"skill:{skill_id}"
            if skill_id and len(cb_data) <= 64:
                buttons.append(InlineKeyboardButton(text=f"ℹ️ {title}", callback_data=cb_data))

        # 2 buttons per row
        rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=keyboard)

    async def _handle_hooks(self, message: TelegramMessage) -> None:
        """Handle /hooks — list active SDK hooks with detail buttons."""
        if not self._hook_manager:
            await message.answer("No hooks configured.")
            return

        hooks = self._hook_manager.list_hooks()
        if not hooks:
            await message.answer("No hooks configured.")
            return

        lines = ["🪝 *Active Hooks*", ""]
        buttons = []
        for i, h in enumerate(hooks):
            lines.append(f"• *{h['name']}* — `{h['event']}` ({h['matcher']})")
            cb_data = f"hook:{i}"
            buttons.append(
                InlineKeyboardButton(text=f"ℹ️ {h['name'][:20]}", callback_data=cb_data)
            )

        rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
        keyboard = InlineKeyboardMarkup(inline_keyboard=rows) if rows else None
        await message.answer("\n".join(lines), parse_mode="Markdown", reply_markup=keyboard)

    async def _handle_cost(self, message: TelegramMessage) -> None:
        """Handle /cost — show usage costs."""
        if message.chat is None or self._agent_service is None:
            await message.answer("Bot not ready.")  # type: ignore[union-attr]
            return

        store = self._agent_service.store
        all_convos = store.list(str(message.chat.id))

        def _fmt(n: int) -> str:
            return f"{n/1000:.1f}k" if n >= 1000 else str(n)

        total_cost = sum(c.total_cost_usd for c in all_convos)
        total_msgs = sum(c.message_count for c in all_convos)
        total_in = sum(c.total_input_tokens for c in all_convos)
        total_out = sum(c.total_output_tokens for c in all_convos)

        lines = [
            f"💰 *Usage Costs*",
            "",
            f"*Total cost:* ${total_cost:.4f}",
            f"*Messages:* {total_msgs}",
            f"*Tokens:* {_fmt(total_in)} in / {_fmt(total_out)} out",
            f"*Avg per message:* ${total_cost / total_msgs:.4f}" if total_msgs > 0 else "",
            "",
        ]

        # Per-conversation breakdown
        if len(all_convos) > 1:
            lines.append("*Per conversation:*")
            for c in sorted(all_convos, key=lambda x: x.total_cost_usd, reverse=True):
                if c.total_cost_usd > 0:
                    lines.append(
                        f"  {c.name}: ${c.total_cost_usd:.4f} ({c.message_count} msgs)"
                    )

        await message.answer("\n".join(lines), parse_mode="Markdown")

    async def _handle_help(self, message: TelegramMessage) -> None:
        """Handle /help — list all available commands."""
        lines = ["*Available Commands*", ""]

        lines.append("*System:*")
        for cmd, desc in BOT_COMMANDS.items():
            if cmd == "/status":
                continue  # skip alias
            lines.append(f"  {cmd} — {desc}")

        lines.append("")
        lines.append("*SDK:*")
        for cmd, desc in SDK_COMMANDS.items():
            lines.append(f"  {cmd} — {desc}")

        # List custom slash commands from .claude/commands/
        from pathlib import Path
        custom_cmds: list[str] = []
        for commands_dir in [Path(".claude/commands"), Path.home() / ".claude/commands"]:
            if commands_dir.is_dir():
                for f in sorted(commands_dir.rglob("*.md")):
                    name = "/" + f.stem
                    if name not in BOT_COMMANDS and name not in SDK_COMMANDS:
                        custom_cmds.append(name)
        if custom_cmds:
            lines.append("")
            lines.append("*Custom:*")
            for cmd in custom_cmds:
                lines.append(f"  {cmd}")

        await message.answer("\n".join(lines), parse_mode="Markdown")

    async def _handle_start(self, message: TelegramMessage) -> None:
        """Handle /start command."""
        if message.chat is None:
            return
        chat_id = message.chat.id
        if chat_id not in self._greeted_users:
            self._greeted_users.add(chat_id)
            greeting = self.config.persona.greeting
            if greeting:
                await message.answer(greeting)
            elif self._agent_service:
                await self._process_with_streaming(chat_id, "/start", message)
            else:
                await message.answer(f"Hello! I'm {self.config.persona.name}.")

    async def _handle_status(self, message: TelegramMessage) -> None:
        """Handle /status command."""
        import time

        uptime = time.time() - self._start_time
        h, rem = divmod(int(uptime), 3600)
        m, s = divmod(rem, 60)

        lines = [
            f"🤖 *{self.config.persona.name} Status*",
            "",
            f"*Uptime:* {h}h {m}m {s}s",
            f"*Model:* `{self.config.model}`",
            f"*Max turns:* {self.config.max_turns}",
            f"*Permission mode:* {self.config.permission_mode}",
            f"*Active chats:* {len(self._known_chat_ids)}",
        ]
        if self._agent_service and message.chat:
            store = self._agent_service.store
            all_convos = store.list(str(message.chat.id))
            total_cost = sum(c.total_cost_usd for c in all_convos)
            total_msgs = sum(c.message_count for c in all_convos)
            total_in = sum(c.total_input_tokens for c in all_convos)
            total_out = sum(c.total_output_tokens for c in all_convos)

            def _fmt(n: int) -> str:
                return f"{n/1000:.1f}k" if n >= 1000 else str(n)

            lines.append(f"*Conversations:* {len(all_convos)}")
            lines.append(f"*Messages:* {total_msgs}")
            lines.append(f"*Total cost:* ${total_cost:.4f}")
            lines.append(f"*Tokens:* {_fmt(total_in)} in / {_fmt(total_out)} out")

        await message.answer("\n".join(lines), parse_mode="Markdown")

    async def _set_bot_commands(self) -> None:
        """Register bot commands for Telegram menu/autocomplete."""
        commands = [
            BotCommand(command="start", description="Start the bot"),
            BotCommand(command="info", description="Bot info and usage stats"),
            BotCommand(command="commands", description="Show all available commands"),
            BotCommand(command="compact", description="Summarize history to save tokens"),
            BotCommand(command="clear", description="Reset conversation"),
            BotCommand(command="cost", description="Show API usage costs"),
            BotCommand(command="model", description="Switch AI model"),
            BotCommand(command="skills", description="List available API skills"),
            BotCommand(command="hooks", description="List active SDK hooks"),
        ]
        await self.bot.set_my_commands(commands)

    async def start_polling(self) -> None:
        """Start long-polling for Telegram updates."""
        logger.info("telegram_polling_started")
        await self._set_bot_commands()
        await self.dp.start_polling(self.bot)

    async def stop(self) -> None:
        """Stop the Telegram bot."""
        await self.bot.session.close()
