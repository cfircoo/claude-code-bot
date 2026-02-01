"""Tests for configuration loading and validation."""

import os
import tempfile
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from claude_code_bot.config import BotConfig, PersonaConfig, load_config


@pytest.fixture
def valid_config_dict() -> dict:
    return {
        "persona": {
            "name": "TestBot",
            "system_prompt": "You are a test bot.",
            "tone": "formal",
        },
        "channels": [{"type": "http", "settings": {}}],
        "api_keys": {"anthropic_api_key": "sk-test"},
    }


@pytest.fixture
def config_file(valid_config_dict: dict, tmp_path: Path) -> Path:
    path = tmp_path / "config.yaml"
    with open(path, "w") as f:
        yaml.dump(valid_config_dict, f)
    return path


def test_load_valid_config(config_file: Path) -> None:
    config = load_config(str(config_file))
    assert config.persona.name == "TestBot"
    assert config.persona.system_prompt == "You are a test bot."
    assert config.persona.tone == "formal"
    assert len(config.channels) == 1
    assert config.channels[0].type == "http"


def test_load_config_missing_file() -> None:
    with pytest.raises(FileNotFoundError, match="Config file not found"):
        load_config("/nonexistent/config.yaml")


def test_load_config_defaults(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    with open(path, "w") as f:
        yaml.dump({}, f)
    config = load_config(str(path))
    assert config.persona.name == "Assistant"
    assert config.persona.fallback_message.startswith("I'm having trouble")
    assert config.port == 8000


def test_load_config_invalid_field(tmp_path: Path) -> None:
    path = tmp_path / "config.yaml"
    with open(path, "w") as f:
        yaml.dump({"port": "not_a_number"}, f)
    with pytest.raises(ValidationError):
        load_config(str(path))


def test_env_var_overrides(config_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-from-env")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "tg-from-env")
    config = load_config(str(config_file))
    assert config.api_keys.anthropic_api_key == "sk-from-env"
    assert config.api_keys.telegram_bot_token == "tg-from-env"


def test_persona_config_defaults() -> None:
    persona = PersonaConfig()
    assert persona.name == "Assistant"
    assert persona.constraints == []
    assert persona.greeting is None


def test_bot_config_extra_fields_ignored(tmp_path: Path) -> None:
    """Extra/unknown keys in config.yaml should not cause ValidationError."""
    path = tmp_path / "config.yaml"
    with open(path, "w") as f:
        yaml.dump({"memory": {"enabled": True}, "unknown_section": "value"}, f)
    config = load_config(str(path))
    assert config.persona.name == "Assistant"  # defaults still work


def test_bot_config_model_validation() -> None:
    config = BotConfig(
        persona=PersonaConfig(name="Test"),
        channels=[{"type": "telegram", "settings": {}}],
    )
    assert config.channels[0].type == "telegram"
