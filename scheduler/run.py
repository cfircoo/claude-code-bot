#!/usr/bin/env python3
"""Scheduler — triggers bot on interval to execute scheduled tasks."""

from __future__ import annotations

import json
import os
import time

import httpx
import yaml

CONFIG_PATH = os.environ.get("CONFIG_PATH", "/app/config.yaml")
BOT_URL = os.environ.get("BOT_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("HTTP_API_KEY", "")
USER_ID = os.environ.get("USER_ID", "scheduler")


def load_config(path: str) -> dict:
    """Load scheduler config from main bot config file."""
    with open(path) as f:
        config = yaml.safe_load(f)
    return config.get("scheduler", {})


def send_to_bot(message: str) -> str:
    """POST to /chat/stream, collect text from SSE events, return response."""
    headers: dict[str, str] = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    payload = {"user_id": USER_ID, "message": message}
    parts: list[str] = []

    try:
        with httpx.stream(
            "POST",
            f"{BOT_URL}/chat/stream",
            json=payload,
            headers=headers,
            timeout=httpx.Timeout(connect=10, read=600, write=10, pool=10),
        ) as resp:
            if resp.status_code != 200:
                resp.read()
                print(f"  [error] HTTP {resp.status_code}: {resp.text}")
                return ""
            for line in resp.iter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    event = json.loads(line[6:])
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "text":
                    parts.append(event.get("content", ""))
                elif event.get("type") == "error":
                    print(f"  [bot-error] {event.get('content', '')}")
    except Exception as e:
        print(f"  [error] {e}")

    return "".join(parts)


def wait_for_bot() -> None:
    """Wait for bot health check."""
    print("Waiting for bot...", flush=True)
    for _ in range(60):
        try:
            r = httpx.get(f"{BOT_URL}/health", timeout=5)
            if r.status_code == 200:
                print("Bot is ready.")
                return
        except Exception:
            pass
        time.sleep(5)
    print("Warning: bot not reachable, continuing anyway.")


def main() -> None:
    config = load_config(CONFIG_PATH)

    if not config.get("enabled", True):
        print("Scheduler disabled in config (scheduler.enabled: false). Exiting.")
        return  # exit 0 — won't restart with on-failure policy

    interval_minutes = config.get("interval", 30)
    system_prompt = config.get("system_prompt", "").strip()
    message = config.get("message", "Scheduler trigger.")

    print(f"Scheduler starting — bot={BOT_URL}")
    print(f"Interval: {interval_minutes} minutes")

    wait_for_bot()

    full_message = f"{system_prompt}\n\n{message}" if system_prompt else message

    while True:
        print(f"[{time.strftime('%H:%M')}] Triggering bot...", flush=True)
        response = send_to_bot(full_message)
        if response:
            print(f"  Response: {response[:200]}...")
        else:
            print("  (no response)")

        time.sleep(interval_minutes * 60)


if __name__ == "__main__":
    main()
