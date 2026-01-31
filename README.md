# Claude Code Bot

A Python framework for building AI-powered conversational bots using [claude-agent-sdk](https://platform.claude.com/docs/en/agent-sdk/python). Supports HTTP (SSE streaming) and Telegram channels with configurable persona, multi-conversation support, and sub-agent orchestration.

## Features

- **Real-time streaming** — SSE endpoint streams text tokens, tool usage, and subagent activity as they happen
- **Multi-conversation** — Each user can have multiple conversations with SDK session resume
- **Telegram integration** — Full Telegram bot with typing indicators and proactive messaging
- **Configurable persona** — Name, system prompt, tone, constraints, and greeting via YAML
- **Sub-agent system** — Register custom agents that the main bot can delegate to
- **Docker ready** — Single `docker compose up` to deploy

## Quick Start

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- [Claude Code](https://claude.com/claude-code) subscription or API key
- Node.js 20+ (bundled in Docker, needed for SDK CLI)

### 1. Clone and install

```bash
git clone https://github.com/cfircoo/claude-code-bot.git
cd claude-code-bot
uv sync
```

### 2. Configure

```bash
cp config.example.yaml config.yaml
```

Edit `config.yaml` with your persona and settings:

```yaml
persona:
  name: "Aristo"
  system_prompt: "You are Aristo, a trusted assistant."
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

### 3. Run

**With Docker (recommended):**

```bash
# Set your Telegram token
export TELEGRAM_BOT_TOKEN=your-token-here

docker compose up --build
```

**Without Docker:**

```bash
uv run python -m claude_code_bot
```

The bot starts on `http://localhost:8000` (mapped to `8010` in Docker).

### 4. Chat

**CLI tool:**

```bash
# Single message
uv run python agent.py "Hello!"

# Interactive mode with streaming
uv run python agent.py -i

# Target specific conversation
uv run python agent.py --conversation <id> "Continue our discussion"

# Debug mode (raw SSE events)
uv run python agent.py -i --debug
```

**HTTP API:**

```bash
# Streaming (SSE)
curl -N -X POST http://localhost:8010/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"user_id": "user1", "message": "Hello!"}'

# Health check
curl http://localhost:8010/health
```

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

### Optional: Customize your bot with BotFather

Send these commands to @BotFather:

- `/setdescription` — Short description shown in bot profile
- `/setabouttext` — About text shown when users open the bot
- `/setuserpic` — Set a profile picture
- `/setcommands` — Set command menu (e.g., `start - Start chatting`)

## API Reference

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/chat/stream` | SSE streaming chat (main endpoint) |
| `GET` | `/health` | Health check |
| `GET` | `/conversations/{user_id}` | List user's conversations |
| `POST` | `/conversations/{user_id}` | Create new conversation |
| `DELETE` | `/conversations/{user_id}/{conv_id}` | Delete conversation |
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

The Docker setup mounts `~/.claude` for Claude subscription authentication (no API key needed).

```yaml
# docker-compose.yml
volumes:
  - ./config.yaml:/app/config.yaml:ro
  - ./data:/app/data          # Conversation data persistence
  - ~/.claude:/root/.claude   # Claude subscription auth
```

To use an API key instead, uncomment `ANTHROPIC_API_KEY` in `docker-compose.yml`.

## Development

```bash
# Install with dev dependencies
uv sync --dev

# Run tests
uv run pytest tests/

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
  logging.py         # structlog JSON configuration
  channels/
    telegram.py      # Telegram adapter (aiogram)
agent.py             # CLI chat tool
config.example.yaml  # Example configuration
Dockerfile
docker-compose.yml
```

## License

MIT
