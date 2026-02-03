#!/usr/bin/env python3
"""CLI tool to send messages directly to Telegram using the Bot API."""

from __future__ import annotations

import argparse
import os
import sys

import httpx


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Send a message directly to Telegram",
        prog="telegram-send",
    )
    parser.add_argument("message", help="Message to send")
    parser.add_argument(
        "--chat-id",
        default=None,
        help="Telegram chat ID (default: from config or TELEGRAM_CHAT_ID env)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Telegram bot token (default: from config or TELEGRAM_BOT_TOKEN env)",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Config file path (default: config.yaml or CONFIG_PATH env)",
    )
    args = parser.parse_args()

    # Load config
    config = None
    try:
        from claude_code_bot.config import load_config
        config_path = args.config or os.environ.get("CONFIG_PATH", "config.yaml")
        config = load_config(config_path)
    except Exception:
        pass

    # Resolve chat_id: CLI > env > config
    chat_id = args.chat_id or os.environ.get("TELEGRAM_CHAT_ID")
    if not chat_id and config:
        for ch in config.channels:
            if ch.type == "telegram":
                chat_id = ch.settings.get("chat_id")
                break

    # Resolve token: CLI > env > config
    token = args.token or os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token and config:
        token = config.api_keys.telegram_bot_token

    if not chat_id:
        print("Error: --chat-id required, or set TELEGRAM_CHAT_ID env, or add channels.telegram.settings.chat_id to config", file=sys.stderr)
        sys.exit(1)

    if not token:
        print("Error: --token required, or set TELEGRAM_BOT_TOKEN env, or add api_keys.telegram_bot_token to config", file=sys.stderr)
        sys.exit(1)

    # Send directly via Telegram Bot API
    try:
        resp = httpx.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": args.message},
            timeout=10,
        )
        data = resp.json()
        if data.get("ok"):
            print(f"Sent to chat {chat_id}")
        else:
            print(f"Error: {data.get('description', 'Unknown error')}", file=sys.stderr)
            sys.exit(1)
    except httpx.ConnectError:
        print("Error: Cannot connect to Telegram API", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
