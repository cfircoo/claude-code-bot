"""FastAPI application with SSE streaming, conversation CRUD, and health endpoints."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, AsyncGenerator

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from claude_code_bot.agent import AgentService
from claude_code_bot.agents import SubAgentRegistry, load_sub_agents_from_config
from claude_code_bot.channels.telegram import TelegramChannel
from claude_code_bot.config import BotConfig, load_config
from claude_code_bot.logging import setup_logging
from claude_code_bot.memory import ConversationStore
from claude_code_bot.memory_store import MemoryStore
from claude_code_bot.permissions import PermissionManager

logger = structlog.get_logger()

# Runtime state
_agent_service: AgentService | None = None
_config: BotConfig | None = None
_telegram: TelegramChannel | None = None
_store: ConversationStore | None = None
_permission_manager: PermissionManager | None = None


class ChatStreamRequest(BaseModel):
    user_id: str
    message: str
    conversation_id: str | None = None


class ConversationCreateRequest(BaseModel):
    name: str | None = None


class ConversationResponse(BaseModel):
    conversation_id: str
    name: str
    created_at: float
    last_active: float


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
    global _agent_service, _config, _telegram, _store

    import os

    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    try:
        _config = load_config(config_path)
    except FileNotFoundError:
        _config = BotConfig()

    setup_logging(_config.log_level)

    _store = ConversationStore()

    try:
        registry = load_sub_agents_from_config(
            {name: conf for name, conf in _config.agents.items()}
        )
    except ImportError:
        registry = SubAgentRegistry()

    _memory_store = MemoryStore(memory_path=_config.memory_path)
    global _permission_manager
    _permission_manager = PermissionManager(
        tools_requiring_approval=_config.tools_requiring_approval,
    )
    _agent_service = AgentService(
        config=_config,
        store=_store,
        registry=registry,
        memory_store=_memory_store,
        permission_manager=_permission_manager,
    )

    # Start Telegram if configured
    telegram_task: asyncio.Task[Any] | None = None
    if _has_channel("telegram") and _config.api_keys.telegram_bot_token:
        tg_settings: dict[str, Any] = {}
        for ch in _config.channels:
            if ch.type == "telegram":
                tg_settings = ch.settings
                break
        _telegram = TelegramChannel(
            bot_token=_config.api_keys.telegram_bot_token,
            config=_config,
        )
        _telegram.show_tool_activity = tg_settings.get("show_tool_activity", False)
        _telegram.thinking_threshold = float(tg_settings.get("thinking_threshold", 10.0))
        if _permission_manager:
            _telegram.set_permission_manager(_permission_manager)
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


@app.post("/chat/stream")
async def chat_stream(request: Request, body: ChatStreamRequest) -> StreamingResponse:
    """SSE endpoint that streams events from chat_stream()."""
    api_key = _get_http_api_key()
    if api_key:
        provided_key = request.headers.get("X-API-Key", "")
        if provided_key != api_key:
            raise HTTPException(status_code=401, detail="Unauthorized")

    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if _agent_service is None:
        raise HTTPException(status_code=503, detail="Bot not initialized")

    async def event_generator() -> AsyncGenerator[str, None]:
        async for event in _agent_service.chat_stream(
            user_id=body.user_id,
            message=body.message,
            conversation_id=body.conversation_id,
        ):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/conversations/{user_id}", response_model=list[ConversationResponse])
async def list_conversations(user_id: str) -> list[ConversationResponse]:
    """List all conversations for a user."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")
    convos = _store.list(user_id)
    return [
        ConversationResponse(
            conversation_id=c.conversation_id,
            name=c.name,
            created_at=c.created_at,
            last_active=c.last_active,
        )
        for c in convos
    ]


@app.post("/conversations/{user_id}", response_model=ConversationResponse, status_code=201)
async def create_conversation(
    user_id: str, body: ConversationCreateRequest | None = None
) -> ConversationResponse:
    """Create a new conversation for a user."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")
    name = body.name if body else None
    meta = _store.create(user_id, name=name)
    return ConversationResponse(
        conversation_id=meta.conversation_id,
        name=meta.name,
        created_at=meta.created_at,
        last_active=meta.last_active,
    )


@app.delete("/conversations/{user_id}/{conversation_id}")
async def delete_conversation(user_id: str, conversation_id: str) -> dict[str, str]:
    """Delete a conversation."""
    if _store is None:
        raise HTTPException(status_code=503, detail="Store not initialized")
    try:
        _store.delete(user_id, conversation_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {"status": "deleted"}


class PermissionResponse(BaseModel):
    approved: bool


@app.post("/permissions/{request_id}")
async def resolve_permission(request_id: str, body: PermissionResponse) -> dict[str, str]:
    """Resolve a pending tool permission request."""
    if _permission_manager is None:
        raise HTTPException(status_code=503, detail="Permission manager not initialized")
    if not _permission_manager.resolve(request_id, body.approved):
        raise HTTPException(status_code=404, detail="Permission request not found")
    return {"status": "resolved"}


@app.post("/proactive")
async def send_proactive(user_id: str, message: str) -> dict[str, str]:
    """Send a proactive message to a user via Telegram."""
    if _telegram is None:
        raise HTTPException(status_code=400, detail="Telegram channel not configured")
    await _telegram.send_proactive_message(user_id, message)
    return {"status": "sent"}
