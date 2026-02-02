#!/usr/bin/env python3
"""Interactive installer for Claude Code Bot."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import yaml


def ask(prompt: str, default: str = "") -> str:
    """Prompt user for input with optional default."""
    suffix = f" [{default}]" if default else ""
    value = input(f"{prompt}{suffix}: ").strip()
    return value or default


def ask_yn(prompt: str, default: bool = True) -> bool:
    """Prompt user for yes/no."""
    hint = "Y/n" if default else "y/N"
    value = input(f"{prompt} ({hint}): ").strip().lower()
    if not value:
        return default
    return value in ("y", "yes")


def ask_choice(prompt: str, choices: list[str], default: str) -> str:
    """Prompt user to pick from a list."""
    print(f"\n{prompt}")
    for i, c in enumerate(choices, 1):
        marker = " (default)" if c == default else ""
        print(f"  {i}. {c}{marker}")
    value = input(f"Choice [default: {default}]: ").strip()
    if not value:
        return default
    try:
        idx = int(value) - 1
        if 0 <= idx < len(choices):
            return choices[idx]
    except ValueError:
        if value in choices:
            return value
    print(f"  Invalid choice, using default: {default}")
    return default


def banner() -> None:
    print()
    print("=" * 50)
    print("  Claude Code Bot - First Time Setup")
    print("=" * 50)
    print()


def setup_persona() -> dict:
    print("--- Persona ---")
    name = ask("Bot name", "MyBot")
    system_prompt = ask(
        "System prompt (press Enter for default)",
        f"You are a helpful assistant named {name}.",
    )
    # Append memory system instructions
    system_prompt += """

## Memory System
You have a persistent memory system. Your memory contents are automatically loaded into this conversation.

Memory zones:
- core/ - Read-only. Curated by your owner. Contains personality, preferences, and guidelines you should always follow.
- to_improve/ - Write self-improvement suggestions here when you notice patterns that could make you better.
- Everything else - Your personal notes. Organize freely with meaningful folder/file names.

Guidelines:
- Review your memory content at the start of each conversation for relevant context.
- Proactively save important context: user preferences, recurring topics, useful patterns.
- Organize notes with descriptive paths (e.g., users/alice/preferences.md, topics/cooking/recipes.md).
- Write to to_improve/ when you notice areas for improvement."""

    tone = ask("Tone", "friendly")
    greeting = ask("Greeting message", f"Hello! I'm {name}. How can I help you today?")
    fallback = ask(
        "Fallback message",
        "I'm having trouble thinking right now. Try again in a moment.",
    )
    return {
        "name": name,
        "system_prompt": system_prompt,
        "tone": tone,
        "constraints": ["Be concise", "Stay on topic"],
        "greeting": greeting,
        "fallback_message": fallback,
    }


def setup_channels() -> list[dict]:
    print("\n--- Channels ---")
    channels = []
    if ask_yn("Enable HTTP channel?", default=True):
        channels.append({"type": "http", "settings": {}})
    if ask_yn("Enable Telegram channel?", default=False):
        channels.append({"type": "telegram", "settings": {}})
    if not channels:
        print("  At least HTTP is needed, enabling it.")
        channels.append({"type": "http", "settings": {}})
    return channels


def setup_env(has_telegram: bool) -> dict[str, str]:
    print("\n--- API Keys ---")
    env = {}
    key = ask("ANTHROPIC_API_KEY (required)")
    while not key:
        print("  This key is required.")
        key = ask("ANTHROPIC_API_KEY")
    env["ANTHROPIC_API_KEY"] = key

    if has_telegram:
        token = ask("TELEGRAM_BOT_TOKEN")
        if token:
            env["TELEGRAM_BOT_TOKEN"] = token

    return env


def setup_settings() -> dict:
    print("\n--- Settings ---")
    port = int(ask("HTTP port", "8000"))
    max_turns = int(ask("Max turns per message", "10"))
    permission_mode = ask_choice(
        "Permission mode:",
        ["default", "acceptEdits", "bypassPermissions"],
        "acceptEdits",
    )
    allowed_tools_str = ask(
        "Allowed tools (comma-separated, empty=no restriction)",
        "WebSearch,WebFetch,Read,Write,Edit,Bash",
    )
    allowed_tools = [t.strip() for t in allowed_tools_str.split(",") if t.strip()] if allowed_tools_str else []
    memory_path = ask("Memory path", "~/.claude-bot/memory")
    log_level = ask_choice("Log level:", ["DEBUG", "INFO", "WARNING", "ERROR"], "INFO")

    return {
        "port": port,
        "max_turns": max_turns,
        "permission_mode": permission_mode,
        "allowed_tools": allowed_tools,
        "memory_path": memory_path,
        "log_level": log_level,
    }


def create_folders(memory_path: str) -> None:
    print("\n--- Creating folders ---")
    expanded = Path(memory_path).expanduser().resolve()
    dirs = [
        expanded / "core",
        expanded / "to_improve",
        Path("data"),
        Path("memory"),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        print(f"  Created: {d}")


def write_env(env: dict[str, str]) -> None:
    path = Path(".env")
    if path.exists():
        if not ask_yn(f"  {path} already exists. Overwrite?", default=False):
            print("  Skipping .env")
            return
    lines = [f"{k}={v}" for k, v in env.items()]
    path.write_text("\n".join(lines) + "\n")
    print(f"  Wrote {path}")


def write_config(persona: dict, channels: list, settings: dict) -> None:
    path = Path("config.yaml")
    if path.exists():
        if not ask_yn(f"  {path} already exists. Overwrite?", default=False):
            print("  Skipping config.yaml")
            return

    config = {
        "persona": persona,
        "channels": channels,
        "agents": {},
        "api_keys": {
            "anthropic_api_key": "",
            "telegram_bot_token": "",
        },
        "max_turns": settings["max_turns"],
        "permission_mode": settings["permission_mode"],
        "log_level": settings["log_level"],
        "port": settings["port"],
        "memory_path": settings["memory_path"],
    }
    if settings["allowed_tools"]:
        config["allowed_tools"] = settings["allowed_tools"]

    path.write_text(yaml.dump(config, default_flow_style=False, sort_keys=False, allow_unicode=True))
    print(f"  Wrote {path}")


def docker_build() -> None:
    print()
    if not ask_yn("Build Docker image now?", default=False):
        return
    print("  Building...")
    try:
        subprocess.run(["docker", "compose", "build"], check=True)
        print("  Build complete!")
    except FileNotFoundError:
        print("  docker compose not found. Skipping.")
    except subprocess.CalledProcessError as e:
        print(f"  Build failed: {e}")


def main() -> None:
    banner()

    if Path("config.yaml").exists() and Path(".env").exists():
        if not ask_yn("Setup was already completed. Run again?", default=False):
            print("  Nothing to do. Exiting.")
            return

    persona = setup_persona()
    channels = setup_channels()
    has_telegram = any(c["type"] == "telegram" for c in channels)
    env = setup_env(has_telegram)
    settings = setup_settings()

    print("\n--- Writing files ---")
    create_folders(settings["memory_path"])
    write_env(env)
    write_config(persona, channels, settings)

    docker_build()

    print()
    print("=" * 50)
    print("  Setup complete!")
    print()
    print("  Start with:  docker compose up -d --build")
    print("  Or locally:  uv run python -m claude_code_bot")
    print("=" * 50)
    print()


if __name__ == "__main__":
    main()
