# Claude Code Bot

A Python framework for building AI-powered conversational bots using [claude-agent-sdk](https://platform.claude.com/docs/en/agent-sdk/python). Supports HTTP (SSE streaming) and Telegram channels with configurable persona, multi-conversation support, and sub-agent orchestration.

## Features

- **Real-time streaming** — SSE endpoint streams text tokens, tool usage, and subagent activity as they happen
- **Multi-conversation** — Each user can have multiple conversations with SDK session resume
- **Telegram integration** — Full Telegram bot with typing indicators, inline keyboards, and proactive messaging
- **Telegram commands** — Built-in `/info`, `/cost`, `/model`, `/commands`, `/compact`, `/clear` with menu autocomplete
- **Model switching** — Switch models at runtime via `/model` with live model list from Anthropic API
- **Usage tracking** — Per-message and per-conversation cost/token accumulation with footer on every reply
- **Configurable persona** — Name, system prompt, tone, constraints, and greeting via YAML
- **Persistent memory** — Core notes, self-improvement notes, and free-form memory folders
- **Permission system** — Interactive tool approval via Telegram inline keyboards or HTTP endpoint
- **Sub-agent system** — Register custom agents that the main bot can delegate to
- **Interactive installer** — `python install.py` walks through first-time setup
- **Docker ready** — Single `docker compose up` to deploy
- **Scheduler service** — Automated task execution on configurable intervals
- **telegram-send CLI** — Send messages directly to Telegram: `uv run telegram-send "message"`
- **File logging** — Logs to stdout + `logs/bot.log`
- **SDK Skills** — Load skills from `.claude/skills/` automatically
- **98% test coverage** — Comprehensive test suite with pytest-cov

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Node.js 20+ (bundled in Docker, needed for the SDK CLI backend)
- **One of:**
  - [Claude Code](https://claude.com/claude-code) subscription (Pro/Max/Team/Enterprise plan) — **or**
  - Anthropic API key from [console.anthropic.com](https://console.anthropic.com)

### 1. Clone and install

```bash
git clone https://github.com/cfircoo/claude-code-bot.git
cd claude-code-bot
uv sync
```

### 2. Connect to Claude

The bot uses [claude-agent-sdk](https://platform.claude.com/docs/en/agent-sdk/python), which runs Claude Code under the hood. You need to authenticate so the SDK can make API calls.

**Option A — Claude Code subscription (recommended for Docker):**

If you have a Claude Pro, Max, Team, or Enterprise plan with Claude Code enabled:

1. Install Claude Code on your host machine:
   ```bash
   npm install -g @anthropic-ai/claude-code
   ```

2. Log in once to create your credentials:
   ```bash
   claude login
   ```
   This stores auth credentials in `~/.claude/`.

3. When running with Docker, mount your credentials into the container:
   ```yaml
   # docker-compose.yml already has this:
   volumes:
     - ~/.claude:/root/.claude
   ```

   No API key needed — the SDK reads the credentials file directly.

**Option B — Anthropic API key:**

If you prefer using a pay-per-use API key:

1. Get a key from [console.anthropic.com](https://console.anthropic.com)

2. Set it as an environment variable:
   ```bash
   export ANTHROPIC_API_KEY=sk-ant-...
   ```

3. For Docker, uncomment the line in `docker-compose.yml`:
   ```yaml
   environment:
     - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
   ```

### 3. Configure the bot

**Option A — Interactive installer (recommended):**

```bash
python install.py
```

This walks you through persona, channels, API keys, settings, and creates `config.yaml`, `.env`, and required folders.

**Option B — Manual:**

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your persona and settings:

```yaml
persona:
  name: "<Bot Name>"
  system_prompt: "You are <Bot Name>, a trusted assistant."
  tone: "friendly"
  constraints:
    - "Be concise"
    - "Stay on topic"
  greeting: "Hello! How can I help?"
  fallback_message: "I'm having trouble right now. Try again in a moment."

channels:
  - type: http
    settings: {}
  - type: telegram
    settings: {}

api_keys:
  telegram_bot_token: ""  # or set TELEGRAM_BOT_TOKEN env var
```

### 4. Run

**With Docker (recommended):**

```bash
docker compose up --build
```

**Without Docker:**

```bash
uv run python -m claude_code_bot
```

The bot starts on `http://localhost:8000` (mapped to `8010` in Docker).

**Verify it's running:**

```bash
curl http://localhost:8010/health
# {"status": "ok"}
```

### 5. Chat

**CLI tool:**

```bash
# Single message
uv run python agent.py "Hello!"

# Interactive mode with streaming
uv run python agent.py -i

# Target specific conversation
uv run python agent.py --conversation <id> "Continue our discussion"

# With API key auth (if configured on the HTTP channel)
uv run python agent.py -i --api-key "your-secret-key"

# Debug mode (raw SSE events)
uv run python agent.py -i --debug
```

**HTTP API:**

```bash
# Streaming (SSE)
curl -N -X POST http://localhost:8010/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"user_id": "user1", "message": "Hello!"}'
```

**Telegram:** See [Setting Up Telegram](#setting-up-telegram) below.

## Setting Up Telegram

### 1. Create a bot with BotFather

1. Open Telegram and search for **@BotFather**
2. Send `/newbot`
3. Choose a **display name** (e.g., "My Assistant")
4. Choose a **username** ending in `bot` (e.g., `my_assistant_bot`)
5. BotFather will give you a **bot token** like `7123456789:AAH...`

### 2. Configure the token

**Option A — Environment variable:**

```bash
export TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

**Option B — In config.yaml:**

```yaml
api_keys:
  telegram_bot_token: "7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
```

**Option C — In .env file (for Docker):**

```bash
TELEGRAM_BOT_TOKEN=7123456789:AAHxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

### 3. Start chatting

1. Find your bot on Telegram by searching its username
2. Press **Start** or send `/start`
3. The bot will greet you and you can start chatting
4. The bot can only message users who have started a conversation first

### Telegram Commands

| Command | Description |
|---------|-------------|
| `/start` | Start the bot and get a greeting |
| `/info` / `/status` | Bot info, uptime, model, usage stats |
| `/cost` | API usage costs per conversation |
| `/model` | Switch AI model (inline keyboard with live model list) |
| `/commands` | Show all available commands (system, SDK, custom) |
| `/compact` | Summarize history to save tokens (SDK) |
| `/clear` | Reset conversation and clear context (SDK) |

Every reply includes a usage footer with token counts, cost, duration, and conversation ID.

### Optional: Customize your bot with BotFather

Send these commands to @BotFather:

- `/setdescription` — Short description shown in bot profile
- `/setabouttext` — About text shown when users open the bot
- `/setuserpic` — Set a profile picture
- `/setcommands` — Set command menu (e.g., `start - Start chatting`)

## Scheduler

The scheduler service triggers the bot on a cron schedule to execute automated tasks.

### Configuration

Add to `config.yaml`:

```yaml
scheduler:
  enabled: true                # false to disable (container exits cleanly)
  cron: "30 * * * *"           # Run at minute 30 of every hour
  timezone: "Asia/Jerusalem"   # Timezone for cron evaluation
  system_prompt: |
    <scheduler>
      You are receiving a scheduled trigger.
      1. Read `memory/scheduled_tasks.md` for your task list
      2. Execute due tasks based on current time
      3. Update the file with completion timestamps
      4. Send a summary to Telegram using telegram-send skill
    </scheduler>
  message: "Scheduler trigger: check and execute scheduled tasks."
```

### Cron Examples

| Cron Expression | Description |
|-----------------|-------------|
| `30 * * * *` | Every hour at :30 |
| `0 8 * * *` | Daily at 8:00 |
| `*/15 * * * *` | Every 15 minutes |
| `0 9,18 * * *` | At 9:00 and 18:00 |
| `0 0 * * 0` | Weekly on Sunday at midnight |

### Running

```bash
# Bot + scheduler (if scheduler.enabled: true)
docker compose up

# Scheduler reads from main config.yaml
# Bot manages its own task list at memory/scheduled_tasks.md
```

## telegram-send CLI

Send messages directly to Telegram without going through the bot.

```bash
# Basic usage (loads chat_id and token from config.yaml)
uv run telegram-send "Hello from CLI!"

# With explicit options
uv run telegram-send "Hello" --chat-id 123456789 --token "BOT_TOKEN"
```

Config priority: CLI args > environment variables > config.yaml

The tool reads `chat_id` from `channels.telegram.settings.chat_id` and `token` from `api_keys.telegram_bot_token`.

## API Reference

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat/stream` | SSE streaming chat (main endpoint) |
| `GET` | `/health` | Health check |
| `GET` | `/conversations/{user_id}` | List user's conversations |
| `POST` | `/conversations/{user_id}` | Create new conversation |
| `DELETE` | `/conversations/{user_id}/{conv_id}` | Delete conversation |
| `POST` | `/permissions/{request_id}` | Resolve tool permission request |
| `POST` | `/proactive` | Send proactive Telegram message |

### SSE Event Types

```
data: {"type": "text", "content": "Hello"}        # Streamed text token
data: {"type": "tool_start", "tool": "Read"}       # Tool execution started
data: {"type": "tool_done", "tool": "Read"}        # Tool execution finished
data: {"type": "result", "session_id": "abc-123"}  # Stream complete
data: {"type": "error", "content": "..."}          # Error occurred
```

### Authentication

Set `api_key` in the HTTP channel config to require `X-API-Key` header:

```yaml
channels:
  - type: http
    settings:
      api_key: "your-secret-key"
```

## Docker

```yaml
# docker-compose.yml
services:
  bot:
    build: .
    restart: unless-stopped
    ports:
      - "8010:8000"
    volumes:
      - ./config.yaml:/app/config.yaml:ro  # Bot configuration
      - ./data:/app/data                    # Conversation data persistence
      - ~/.claude-docker:/root/.claude      # Claude credentials (see below)
      - ./memory:/app/memory                # Persistent memory
      - ./logs:/app/logs                    # Log files
    environment:
      - CONFIG_PATH=/app/config.yaml
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN:-}
    # - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}  # Uncomment for API key auth

  scheduler:
    build:
      context: .
      dockerfile: scheduler/Dockerfile
    restart: on-failure                     # Exits cleanly when disabled
    volumes:
      - ./config.yaml:/app/config.yaml:ro
    environment:
      - TZ=${TZ:-Asia/Jerusalem}
      - BOT_URL=http://bot:8000
      - HTTP_API_KEY=${HTTP_API_KEY:-}
    depends_on:
      bot:
        condition: service_healthy
```

### Claude Credentials for Docker

We recommend using a minimal `~/.claude-docker/` directory instead of mounting your full `~/.claude/`:

```bash
# Create minimal claude directory for Docker (avoids MCP plugin conflicts)
mkdir -p ~/.claude-docker
cp ~/.claude/.credentials.json ~/.claude-docker/
```

This avoids issues with MCP plugins that can't run in Docker containers.

See [Connect to Claude](#2-connect-to-claude) for authentication options.

### Logs

Logs are written to both stdout and `logs/bot.log`:

```bash
# View logs
tail -f logs/bot.log

# Or via docker
docker compose logs -f bot
```

## Configuration Reference

```yaml
model: "claude-sonnet-4-20250514"   # Default model (switchable at runtime)
max_turns: 10                        # Max agent turns per message
permission_mode: "acceptEdits"       # default | acceptEdits | plan | bypassPermissions
allowed_tools:                       # Tools the agent can use
  - WebSearch
  - WebFetch
  - Read
  - Write
  - Edit
  - Bash
memory_path: "~/.claude-bot/memory"  # Persistent memory location
log_level: "INFO"                    # DEBUG | INFO | WARNING | ERROR
port: 8000
```

### Memory System

The bot has a persistent memory system with three zones:

- `core/` — Read-only notes curated by the owner (personality, guidelines)
- `to_improve/` — Self-improvement suggestions written by the bot
- Everything else — Free-form notes organized by the bot

### Permission System

Tools listed in `tools_requiring_approval` (default: `["Bash"]`) trigger interactive approval. On Telegram, this shows inline keyboard buttons. Via HTTP, use the `/permissions/{request_id}` endpoint.

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Run tests with coverage
uv run pytest --cov=claude_code_bot --cov-report=term-missing

# Type check
uv run mypy src/

# Lint
uv run ruff check src/
```

## Project Structure

```
src/claude_code_bot/
  __init__.py
  __main__.py        # Entry point
  app.py             # FastAPI app, endpoints, lifespan
  agent.py           # AgentService — SDK integration, streaming
  config.py          # Pydantic config models, YAML loader
  memory.py          # ConversationStore, conversation metadata
  agents.py          # Sub-agent base class and registry
  tools.py           # MCP tool definitions
  logging.py         # structlog JSON configuration (stdout + file)
  memory_store.py    # Persistent memory (core/notes/to_improve)
  permissions.py     # Interactive tool approval system
  channels/
    telegram.py      # Telegram adapter (aiogram, commands, inline keyboards)
  cli/
    telegram_send.py # CLI tool for direct Telegram messaging
scheduler/
  run.py             # Scheduler service
  Dockerfile
.claude/skills/      # SDK skills (auto-loaded)
agent.py             # CLI chat tool
install.py           # Interactive first-time setup
config.example.yaml  # Example configuration
Dockerfile
docker-compose.yml
logs/                # Log files (gitignored)
```

## License

MIT
