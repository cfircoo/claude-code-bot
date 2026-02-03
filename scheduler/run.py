#!/usr/bin/env python3
"""Scheduler — sends tasks to the bot on configurable schedules."""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import yaml

TASKS_PATH = os.environ.get("TASKS_PATH", "/app/tasks.yaml")
STATE_PATH = os.environ.get("STATE_PATH", "/app/state.json")
BOT_URL = os.environ.get("BOT_URL", "http://localhost:8000").rstrip("/")
API_KEY = os.environ.get("HTTP_API_KEY", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def load_tasks(path: str) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def load_state(path: str) -> dict[str, str]:
    """Load last-run timestamps from state file."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(path: str, state: dict[str, str]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(state, f, indent=2)


def is_due(schedule: str, now: datetime, last_run: datetime | None) -> bool:
    """Check if a task is due based on its schedule string."""
    # "daily" — once at 00:00
    if schedule == "daily":
        if last_run and last_run.date() == now.date():
            return False
        return now.hour == 0 and now.minute < 2

    # "hourly" — every hour at :00
    if schedule == "hourly":
        if last_run and (now - last_run) < timedelta(minutes=55):
            return False
        return now.minute < 2

    # "every Nh" or "every Nm"
    m = re.match(r"every\s+(\d+)\s*([hm])", schedule)
    if m:
        value, unit = int(m.group(1)), m.group(2)
        interval = timedelta(hours=value) if unit == "h" else timedelta(minutes=value)
        if last_run is None:
            return True
        return (now - last_run) >= interval

    # "HH:MM" — specific time daily
    m = re.match(r"^(\d{1,2}):(\d{2})$", schedule)
    if m:
        hour, minute = int(m.group(1)), int(m.group(2))
        if last_run and last_run.date() == now.date():
            return False
        return now.hour == hour and abs(now.minute - minute) < 2

    # "cron: ..." — full cron expression
    if schedule.startswith("cron:"):
        try:
            from croniter import croniter
            expr = schedule[5:].strip()
            if last_run is None:
                last_run = now - timedelta(days=1)
            cron = croniter(expr, last_run)
            next_time = cron.get_next(datetime)
            return now >= next_time
        except Exception:
            return False

    return False


def send_to_bot(user_id: str, message: str) -> str:
    """POST to /chat/stream, collect text from SSE events, return response."""
    headers: dict[str, str] = {}
    if API_KEY:
        headers["X-API-Key"] = API_KEY

    payload = {"user_id": user_id, "message": message}
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


def notify_telegram(chat_id: str, message: str) -> None:
    """Forward response to Telegram via /proactive endpoint."""
    if not chat_id or not message:
        return
    try:
        resp = httpx.post(
            f"{BOT_URL}/proactive",
            params={"user_id": chat_id, "message": message},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"  [telegram-error] HTTP {resp.status_code}: {resp.text}")
    except Exception as e:
        print(f"  [telegram-error] {e}")


def main() -> None:
    print(f"Scheduler starting — bot={BOT_URL}, tasks={TASKS_PATH}")
    config = load_tasks(TASKS_PATH)
    tz_name = config.get("timezone", os.environ.get("TZ", "UTC"))
    tz = ZoneInfo(tz_name)
    user_id = config.get("user_id", "scheduler")
    chat_id = TELEGRAM_CHAT_ID or config.get("telegram_chat_id", "")
    tasks = config.get("tasks", [])
    check_interval_raw = config.get("check_interval", 60)
    # Parse interval: "30m" = 30 minutes, "30s" or 30 = 30 seconds
    if isinstance(check_interval_raw, str):
        if check_interval_raw.endswith("m"):
            check_interval = int(check_interval_raw[:-1]) * 60
        elif check_interval_raw.endswith("s"):
            check_interval = int(check_interval_raw[:-1])
        else:
            check_interval = int(check_interval_raw)
    else:
        check_interval = int(check_interval_raw)
    system_context = config.get("system_context", "").strip()

    print(f"Timezone: {tz_name}, user_id: {user_id}, chat_id: {chat_id or '(none)'}")
    print(f"Check interval: {check_interval}s")
    print(f"Loaded {len(tasks)} tasks: {[t['name'] for t in tasks]}")

    state = load_state(STATE_PATH)

    # Wait for bot to be ready
    print("Waiting for bot health check...", flush=True)
    for _ in range(60):
        try:
            r = httpx.get(f"{BOT_URL}/health", timeout=5)
            if r.status_code == 200:
                print("Bot is ready.")
                break
        except Exception:
            pass
        time.sleep(5)
    else:
        print("Warning: bot not reachable, continuing anyway.")

    while True:
        now = datetime.now(tz)

        for task in tasks:
            name = task["name"]
            schedule = task["schedule"]
            message = task["message"]

            last_str = state.get(name)
            last_run = datetime.fromisoformat(last_str).replace(tzinfo=tz) if last_str else None

            if is_due(schedule, now, last_run):
                print(f"[{now.strftime('%H:%M')}] Running: {name}", flush=True)
                full_message = f"{system_context}\n\n{message}" if system_context else message
                response = send_to_bot(user_id, full_message)
                if response:
                    print(f"  Response: {response[:100]}...")
                    notify_telegram(chat_id, response)
                else:
                    print("  (no response)")
                state[name] = now.isoformat()
                save_state(STATE_PATH, state)

        time.sleep(check_interval)


if __name__ == "__main__":
    main()
