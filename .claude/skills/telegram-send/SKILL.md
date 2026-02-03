---
name: telegram-send
description: Send a message directly to Telegram using the Bot API. Use when you need to notify the user on Telegram.
---

<objective>
Send a message to the user's Telegram chat using the Telegram Bot API directly.
</objective>

<quick_start>
```bash
uv run telegram-send "Your message here"
```

Chat ID and bot token are loaded from `config.yaml` automatically.
</quick_start>

<usage>
**Basic message:**
```bash
uv run telegram-send "Task completed successfully!"
```

**Multi-line message:**
```bash
uv run telegram-send "Morning briefing:
- 3 tasks completed
- No pending notifications
- Markets stable"
```

**With explicit options (if needed):**
```bash
uv run telegram-send "Hello" --chat-id 992506757 --token "BOT_TOKEN"
```
</usage>

<options>
| Option | Description | Default |
|--------|-------------|---------|
| `message` | The message to send (required) | — |
| `--chat-id` | Telegram chat ID | `config.yaml` or `$TELEGRAM_CHAT_ID` |
| `--token` | Bot token | `config.yaml` or `$TELEGRAM_BOT_TOKEN` |
| `--config` | Config file path | `config.yaml` or `$CONFIG_PATH` |
</options>

<config_sources>
Priority order for chat_id and token:
1. CLI argument (`--chat-id`, `--token`)
2. Environment variable (`TELEGRAM_CHAT_ID`, `TELEGRAM_BOT_TOKEN`)
3. Config file (`channels.telegram.settings.chat_id`, `api_keys.telegram_bot_token`)
</config_sources>

<when_to_use>
- Notify the user about completed tasks
- Send proactive updates or alerts
- Forward important information to Telegram
- Send reminders or status updates
</when_to_use>

<success_criteria>
- Message appears in the user's Telegram chat
- CLI outputs "Sent to chat {chat_id}"
</success_criteria>
