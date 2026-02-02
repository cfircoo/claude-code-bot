"""Configuration models and YAML loader."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class PersonaConfig(BaseModel):
    """Bot persona configuration."""

    name: str = "Assistant"
    system_prompt: str = "You are a helpful assistant."
    tone: str = "friendly"
    constraints: list[str] = Field(default_factory=list)
    greeting: str | None = None
    fallback_message: str = "I'm having trouble thinking right now. Try again in a moment."


class ChannelConfig(BaseModel):
    """Channel configuration."""

    type: str  # "http" or "telegram"
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("settings", mode="before")
    @classmethod
    def _coerce_settings_none(cls, v: Any) -> dict[str, Any]:
        if v is None:
            return {}
        return dict(v)


class SubAgentConfig(BaseModel):
    """Sub-agent configuration."""

    import_path: str
    description: str = ""
    timeout: int = 30


class ApiKeysConfig(BaseModel):
    """API keys configuration."""

    anthropic_api_key: str = ""
    telegram_bot_token: str = ""


class UserRestrictions(BaseModel):
    """Shared tool and path restrictions for any channel."""

    allowed_tools: list[str] = Field(default_factory=list)
    writable_paths: list[str] = Field(default_factory=list)
    readable_paths: list[str] = Field(default_factory=list)


class AllowedUser(UserRestrictions):
    """An authorized Telegram user with per-user permissions."""

    user_id: int
    username: str


class TelegramSecurityConfig(BaseModel):
    """Telegram-specific security settings."""

    allowed_users: list[AllowedUser] = Field(default_factory=list)
    deny_message: str = "You are not authorized to use this bot."


class HttpSecurityConfig(BaseModel):
    """HTTP channel security settings."""

    default_restrictions: UserRestrictions | None = None
    deny_unauthenticated: bool = False


class SecurityConfig(BaseModel):
    """Security configuration."""

    telegram: TelegramSecurityConfig = Field(default_factory=TelegramSecurityConfig)
    http: HttpSecurityConfig = Field(default_factory=HttpSecurityConfig)


class HooksConfig(BaseModel):
    """Hook configuration for SDK hooks."""

    file_guards: list[str] = Field(default_factory=list)
    command_guards: list[str] = Field(default_factory=list)
    auto_approve: list[str] = Field(default_factory=list)
    audit_log: bool = False
    damage_control: bool = False
    damage_control_patterns: str = ""


class BotConfig(BaseModel):
    """Root bot configuration."""

    model_config = ConfigDict(extra="ignore")

    persona: PersonaConfig = Field(default_factory=PersonaConfig)
    channels: list[ChannelConfig] = Field(default_factory=list)
    agents: dict[str, SubAgentConfig] = Field(default_factory=dict)
    api_keys: ApiKeysConfig = Field(default_factory=ApiKeysConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    hooks: HooksConfig = Field(default_factory=HooksConfig)
    model: str = "claude-sonnet-4-20250514"
    max_turns: int = 10
    log_level: str = "INFO"
    port: int = 8000
    memory_path: str = "~/.claude-bot/memory"
    permission_mode: Literal["default", "acceptEdits", "plan", "bypassPermissions"] = "acceptEdits"
    allowed_tools: list[str] = Field(default_factory=list)
    disallowed_tools: list[str] = Field(default_factory=list)
    tools_requiring_approval: list[str] = Field(default_factory=lambda: ["Bash"])


def _apply_env_overrides(config: BotConfig) -> BotConfig:
    """Override config values from environment variables."""
    env_anthropic = os.environ.get("ANTHROPIC_API_KEY")
    if env_anthropic:
        config.api_keys.anthropic_api_key = env_anthropic

    env_telegram = os.environ.get("TELEGRAM_BOT_TOKEN")
    if env_telegram:
        config.api_keys.telegram_bot_token = env_telegram

    env_log_level = os.environ.get("LOG_LEVEL")
    if env_log_level:
        config.log_level = env_log_level

    env_http_key = os.environ.get("HTTP_API_KEY")
    if env_http_key:
        for ch in config.channels:
            if ch.type == "http":
                ch.settings["api_key"] = env_http_key
                break

    return config


def load_config(path: str = "config.yaml") -> BotConfig:
    """Load and validate configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        Validated BotConfig instance.

    Raises:
        FileNotFoundError: If the config file does not exist.
        pydantic.ValidationError: If the config is invalid.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    config = BotConfig(**raw)
    return _apply_env_overrides(config)
