"""FastAPI application with chat and health endpoints."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import structlog
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel

from claude_code_bot.agent import AgentService
from claude_code_bot.agents import SubAgentRegistry, load_sub_agents_from_config
from claude_code_bot.channels.telegram import TelegramChannel
from claude_code_bot.config import BotConfig, load_config
from claude_code_bot.logging import setup_logging
from claude_code_bot.memory import create_memory_backend

logger = structlog.get_logger()

# Runtime state
_agent_service: AgentService | None = None
_config: BotConfig | None = None
_telegram: TelegramChannel | None = None


class ChatRequest(BaseModel):
    user_id: str
    message: str


class ChatResponse(BaseModel):
    response: str


def _get_http_api_key() -> str | None:
    if _config is None:
        return None
    for ch in _config.channels:
        if ch.type == "http":
            return ch.settings.get("api_key")
    return None


def _has_channel(channel_type: str) -> bool:
    if _config is None:
        return False
    return any(ch.type == channel_type for ch in _config.channels)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup and shutdown."""
    global _agent_service, _config, _telegram

    import os

    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    try:
        _config = load_config(config_path)
    except FileNotFoundError:
        _config = BotConfig()

    setup_logging(_config.log_level)

    memory = create_memory_backend(_config.memory.backend, _config.memory.path)

    try:
        registry = load_sub_agents_from_config(
            {name: conf for name, conf in _config.agents.items()}
        )
    except ImportError:
        registry = SubAgentRegistry()

    _agent_service = AgentService(config=_config, memory=memory, registry=registry)

    # Start Telegram if configured
    telegram_task: asyncio.Task[Any] | None = None
    if _has_channel("telegram") and _config.api_keys.telegram_bot_token:
        _telegram = TelegramChannel(
            bot_token=_config.api_keys.telegram_bot_token,
            config=_config,
        )
        _telegram.set_agent_service(_agent_service)
        telegram_task = asyncio.create_task(_telegram.start_polling())

    logger.info(
        "bot_started",
        config_path=config_path,
        persona_name=_config.persona.name,
        channels=[ch.type for ch in _config.channels],
    )

    yield

    # Shutdown
    if _telegram:
        await _telegram.stop()
    if telegram_task:
        telegram_task.cancel()


app = FastAPI(title="Claude Code Bot", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest) -> ChatResponse:
    api_key = _get_http_api_key()
    if api_key:
        provided_key = request.headers.get("X-API-Key", "")
        if provided_key != api_key:
            raise HTTPException(status_code=401, detail="Unauthorized")

    if not body.message.strip():
        return ChatResponse(response="I didn't catch that. Could you try again?")

    if _agent_service is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    response_text = await _agent_service.chat(
        user_id=body.user_id,
        message=body.message,
        channel="http",
    )
    return ChatResponse(response=response_text)


@app.post("/proactive")
async def send_proactive(user_id: str, message: str) -> dict[str, str]:
    """Send a proactive message to a user via Telegram."""
    if _telegram is None:
        raise HTTPException(status_code=400, detail="Telegram channel not configured")
    await _telegram.send_proactive_message(user_id, message)
    return {"status": "sent"}
