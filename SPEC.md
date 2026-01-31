# Claude Code Bot — MVP Specification

> Generated via spec-interview on 2026-01-31
> Status: DRAFT

---

## 1. Overview

### 1.1 Problem Statement
Developers want to create AI-powered conversational bots with distinct personas, but building the plumbing (channel adapters, memory, sub-agent orchestration, config validation) from scratch every time is tedious and error-prone. There is no lightweight, opinionated Python framework that wires Claude (via `claude-agent-sdk`) as the sole LLM backbone into a ready-to-deploy bot with pluggable channels and extensible sub-agents.

### 1.2 Solution Summary
A Python framework that lets a developer define a bot persona and behavior in a YAML config, then run it as a FastAPI HTTP service and/or a Telegram bot. The main agent (the persona) handles conversations, persists per-user memory, and can dynamically delegate work to developer-defined sub-agents. The framework provides the infrastructure; the developer provides the persona and any custom sub-agents.

### 1.3 Success Metrics
- Metric 1: Time from clone to running bot with a custom persona — Target: < 15 minutes
- Metric 2: Lines of code a developer must write for a basic persona bot — Target: 0 (config-only)
- Metric 3: Lines of code to add a custom sub-agent — Target: < 50

### 1.4 Non-Goals
- Multi-user shared conversations (group chats) — deferred to v2
- Multi-person memory per bot — v1 is 1 person per bot instance
- Built-in sub-agent library (developers define their own)
- Developer extension/plugin marketplace or discovery model
- GUI/admin dashboard
- Voice or media message handling
- Self-hosted LLM support (Claude-only via claude-agent-sdk)

---

## 2. Users & Use Cases

### 2.1 Target Users
| User Type | Description | Technical Level | Usage Frequency |
|-----------|-------------|-----------------|-----------------|
| Bot Developer | Python developer who configures and deploys bots | High | During development |
| End User (HTTP) | Person chatting with the bot via HTTP API | Any | Varies |
| End User (Telegram) | Person chatting with the bot via Telegram | Any | Varies |

### 2.2 Primary Use Cases

1. **Configure & Launch a Persona Bot**: Developer writes a YAML config defining persona, selects channels (HTTP, Telegram, or both), and runs the bot.
2. **Chat with the Bot**: End user sends a message, bot responds in-persona with conversational memory.
3. **Register a Sub-Agent**: Developer defines a sub-agent class, registers it with the framework, and the main persona agent can trigger it when contextually appropriate.
4. **Sub-Agent Delegation**: During a conversation, the main agent decides a task requires a sub-agent, delegates to it, receives the result, and incorporates it into its response.
5. **Proactive Outreach**: The bot initiates a message to the user on Telegram without a prior trigger — e.g., scheduled reminders, follow-ups ("How did that go?"), or notifications from sub-agents. Triggered by schedules, internal events, or the agent's own decision during processing.

### 2.3 User Journey (Developer)

```
Install package → Write YAML config (persona, channels, API keys)
    → (Optional) Define sub-agent classes → Run `python -m claude_code_bot` or `docker compose up`
    → Bot is live on configured channels
```

### 2.3b User Journey (End User)

```
Send message (HTTP POST or Telegram) → Bot receives → Main agent processes with persona + memory
    → [If sub-agent needed] → Delegate → Receive result → Compose response
    → Bot replies → Memory updated
```

---

## 3. Functional Requirements

### 3.1 Core Features (MVP)

| Feature | Description | Priority | Acceptance Criteria |
|---------|-------------|----------|---------------------|
| YAML Config | Bot persona, channel settings, API keys defined in YAML, validated with Pydantic | P0 | Invalid config produces clear error; valid config boots the bot |
| HTTP Channel | FastAPI endpoint accepts messages, returns bot responses | P0 | POST /chat with `{user_id, message}` returns `{response}` |
| Telegram Channel | aiogram-based Telegram bot adapter | P0 | Bot responds to DMs on Telegram |
| Main Agent (Persona) | Claude-agent-sdk powered agent that maintains persona across turns | P0 | Responses are consistent with configured persona |
| Conversation Memory | Per-user conversation history persisted across restarts | P0 | Restart bot, send follow-up, bot remembers context |
| Sub-Agent Infrastructure | Register, trigger, and receive results from sub-agents | P0 | Developer can register a sub-agent; main agent can invoke it and use result |
| Proactive Messaging | Bot can initiate messages to user on Telegram (reminders, follow-ups, scheduled messages, notifications) | P0 | Bot sends a message without prior user trigger; message arrives on Telegram |

### 3.2 Phase 2 Features
- Multi-person memory per bot
- Group chat support
- Additional channel adapters (Discord, Slack, WhatsApp)
- Developer extension model / plugin hooks
- Sub-agent marketplace or registry

### 3.3 Future Considerations
- Web admin UI for config and monitoring
- Voice/media message support
- Multi-LLM backend support
- Analytics and conversation insights

---

## 4. Technical Architecture

### 4.1 System Overview

```
┌──────────────┐     ┌──────────────────────────────────────────┐
│  Telegram     │────▶│                                          │
│  (aiogram)    │     │           Claude Code Bot                │
└──────────────┘     │                                          │
                     │  ┌────────────┐   ┌──────────────────┐  │
┌──────────────┐     │  │  Channel   │──▶│   Main Agent     │  │
│  HTTP Client  │────▶│  │  Router    │   │   (Persona)      │  │
│  (FastAPI)    │     │  └────────────┘   │   claude-agent-sdk│  │
└──────────────┘     │                    └───────┬──────────┘  │
                     │                            │              │
                     │                    ┌───────▼──────────┐  │
                     │                    │  Sub-Agent       │  │
                     │                    │  Registry        │  │
                     │                    └───────┬──────────┘  │
                     │                            │              │
                     │                    ┌───────▼──────────┐  │
                     │                    │  Memory Store    │  │
                     │                    │  (per-user)      │  │
                     │                    └──────────────────┘  │
                     └──────────────────────────────────────────┘
```

### 4.2 Data Model

```
Entity: BotConfig (from YAML, validated by Pydantic)
- persona: PersonaConfig (name, system_prompt, tone, constraints)
- channels: list[ChannelConfig] (type: http|telegram, settings per channel)
- memory: MemoryConfig (backend: "simple"|"mem0", path/connection)
- agents: dict[str, SubAgentConfig] (name → config)
- api_keys: ApiKeysConfig (anthropic_api_key, telegram_bot_token)

Entity: Conversation (runtime)
- user_id: str
- channel: str
- messages: list[Message]  # {role, content, timestamp}
- metadata: dict

Entity: SubAgent (developer-defined, framework-registered)
- name: str
- description: str  # used by main agent to decide when to trigger
- handler: callable  # async function that receives context, returns result
```

### 4.3 API Design

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/chat` | POST | Send message, receive response. Body: `{user_id, message}` | API key (optional, configurable) |
| `/health` | GET | Health check | Public |

Telegram: No HTTP API — uses aiogram long-polling or webhook as configured.

### 4.4 State Management

- **Runtime state**: Conversation context held in memory during session
- **Persistent state**: Conversation history stored via memory backend (simple JSON file store for MVP, Mem0 as optional upgrade)
- **Source of truth**: The memory store is source of truth for conversation history; YAML config is source of truth for bot configuration

### 4.5 Technology Stack

| Layer | Technology | Rationale |
|-------|------------|-----------|
| LLM | claude-agent-sdk | Sole LLM backbone per project requirements |
| HTTP Server | FastAPI | Async, fast, auto-docs, Python-native |
| Telegram | aiogram | Async Telegram bot framework, well-maintained |
| Config | YAML + Pydantic | Human-readable config with strict validation |
| Memory (default) | Simple JSON/SQLite persistence | Zero external dependencies for MVP |
| Memory (optional) | Mem0 | Richer memory semantics when needed |
| Deployment | Docker / Docker Compose | Reproducible, single-command deployment |
| Language | Python 3.11+ | Async support, ecosystem compatibility |

---

## 5. UI/UX Design

> No graphical UI in MVP. The "UI" is the chat interface on each channel.

### 5.1 HTTP Channel
- Request/response JSON API. Developer integrates into their own frontend if desired.

### 5.2 Telegram Channel
- Standard Telegram DM experience. Bot responds to text messages in-persona.

### 5.3 Empty States
- First message from a new user: bot introduces itself per persona config (configurable greeting or organic response).

### 5.4 Error States
- LLM failure: bot replies with a configurable fallback message (e.g., "I'm having trouble thinking right now. Try again in a moment.")
- Sub-agent failure: main agent receives error, decides how to communicate it naturally in-persona.

---

## 6. Integration & Dependencies

### 6.1 External Systems

| System | Purpose | Protocol | Owner |
|--------|---------|----------|-------|
| Anthropic API (via claude-agent-sdk) | LLM inference | HTTPS | Anthropic |
| Telegram Bot API (via aiogram) | Messaging channel | HTTPS | Telegram |

### 6.2 Data Flows

```
Reactive flow:
User Message ──(HTTP/Telegram)──▶ Channel Adapter ──▶ Main Agent
    ──(claude-agent-sdk)──▶ Anthropic API ──▶ Response
    ──(optional)──▶ Sub-Agent ──▶ Result back to Main Agent
    ──▶ Memory Store (persist)
    ──▶ Channel Adapter ──▶ User

Proactive flow:
Scheduler/Event/Sub-Agent ──▶ Main Agent ──▶ Compose message
    ──▶ Channel Adapter (Telegram) ──▶ User (unprompted)
```

### 6.3 Failure Handling

| Dependency | Failure Mode | Handling Strategy |
|------------|--------------|-------------------|
| Anthropic API | Timeout / 5xx / rate limit | Retry with exponential backoff (max 3 attempts), then return fallback message |
| Telegram API | Network failure | aiogram handles reconnection; messages may be delayed |
| Memory Store | File I/O error | Log error, continue without persistence (graceful degradation) |
| Sub-Agent | Exception / timeout | Catch error, return error context to main agent, let persona handle gracefully |

---

## 7. Error Handling & Edge Cases

### 7.1 Error Taxonomy

| Error Type | User Message | Technical Detail | Recovery |
|------------|--------------|------------------|----------|
| LLM Unavailable | Configurable fallback message | Log full error, alert if repeated | Auto-retry, then fallback |
| Invalid Config | N/A (startup failure) | Pydantic validation error with specifics | Developer fixes YAML |
| Memory Write Failure | None (transparent) | Log error | Continue without persistence |
| Sub-Agent Timeout | Persona-appropriate apology | Log timeout details | Main agent responds without sub-agent result |

### 7.2 Edge Cases

| Scenario | Expected Behavior |
|----------|-------------------|
| Empty message | Return persona-appropriate "I didn't catch that" response |
| Very long message (>100k chars) | Truncate to model context limit, warn in logs |
| Rapid duplicate messages | Process both (no dedup in MVP) |
| Unknown user_id on HTTP | Create new conversation context |
| Bot restart mid-conversation | Memory store preserves history; conversation continues |
| Sub-agent returns very large result | Truncate before passing to main agent context |

### 7.3 Partial Failure Handling
- If memory write fails but LLM response succeeded: return response to user, log memory failure. Next turn may lack context.
- If sub-agent fails but main agent can still respond: respond without sub-agent data, optionally mention inability to complete that part.

---

## 8. Security & Privacy

### 8.1 Authentication
- **HTTP channel**: Optional API key via header (`X-API-Key`), configurable in YAML. No auth by default for local dev.
- **Telegram channel**: Telegram handles user identity via chat IDs.

### 8.2 Authorization
- MVP: No role-based access. All end users have equal access. Bot developer controls everything via config.

### 8.3 Data Classification

| Data Type | Classification | Encryption | Retention |
|-----------|---------------|------------|-----------|
| Conversation history | User-generated, potentially PII | At-rest: developer's responsibility (file perms / disk encryption) | Configurable, no auto-expiry in MVP |
| API keys (Anthropic, Telegram) | Secret | Must not be logged; loaded from env vars or config | N/A |
| Bot persona config | Internal | None required | N/A |

### 8.4 Compliance Requirements
- MVP: None. Developer is responsible for compliance based on their use case.

### 8.5 Audit Trail
- MVP: Standard application logging (structured JSON logs). No dedicated audit log.

---

## 9. Performance & Reliability

### 9.1 Performance Targets

| Metric | Target | Notes |
|--------|--------|-------|
| Response time (p50) | < 3s | Dominated by LLM inference time |
| Response time (p99) | < 15s | Including retry on first LLM failure |
| Throughput | 10 concurrent conversations | MVP target for single instance |

### 9.2 Availability Target
- No formal SLA for MVP. Availability limited by Anthropic API uptime and host uptime.

### 9.3 Scalability Plan
- MVP: Single process, single instance. Scales vertically.
- Future: Stateless app servers with external memory store (Redis/PostgreSQL) for horizontal scaling.

### 9.4 Graceful Degradation
- Memory store down: bot continues without memory (stateless mode)
- Sub-agents unavailable: main agent responds solo
- LLM overloaded: queue or reject with friendly error after retries

---

## 10. Operations

### 10.1 Deployment
- **Primary**: `docker compose up` with environment variables for secrets
- **Alternative**: Direct `python -m claude_code_bot` for development
- **Config**: YAML file mounted into container or placed alongside code

### 10.2 Monitoring & Alerting
- MVP: Structured JSON logging to stdout. Developer pipes to their log aggregator.
- `/health` endpoint for uptime monitors.

### 10.3 Debugging
- Structured logs include: user_id, channel, request_id, latency, error details
- Memory store is inspectable (JSON files or SQLite DB)

### 10.4 Rollback Plan
- Re-deploy previous Docker image. Memory store is forward-compatible (append-only conversation history).

### 10.5 Configuration Management
- YAML config file + environment variables for secrets
- Environment variables override YAML values (standard 12-factor pattern)
- No runtime config changes in MVP (restart required)

---

## 11. Testing Strategy

### 11.1 Test Levels

| Level | Scope | Tooling | Coverage Target |
|-------|-------|---------|-----------------|
| Unit | Config validation, memory store, channel routing, sub-agent registry | pytest | Core logic 80%+ |
| Integration | Main agent + claude-agent-sdk (mocked), channel adapters | pytest + httpx (TestClient) | Happy path + error paths |
| E2E | Full flow: HTTP request → response with memory | pytest + httpx | Primary use cases |

### 11.2 Test Data Strategy
- Fixture-based: predefined YAML configs, conversation histories, mock LLM responses
- claude-agent-sdk calls mocked in unit/integration tests to avoid API costs

### 11.3 Acceptance Criteria
- Bot boots with valid config, fails clearly with invalid config
- HTTP and Telegram channels receive and respond to messages
- Conversation memory persists across restarts
- Sub-agent can be registered and triggered by main agent
- All tests pass, mypy clean, ruff clean

---

## 12. Verification Environment

### 12.1 Dev Server
- **Start command:** `python -m claude_code_bot` or `uvicorn claude_code_bot.main:app --reload`
- **URL:** `http://localhost:8000`
- **Health endpoint:** `GET /health`

### 12.2 Database
- **Type:** SQLite (default memory backend) or JSON files
- **ORM/Migration tool:** None in MVP (simple file/sqlite3 direct access)
- **Direct query command:** `sqlite3 data/memory.db` or inspect JSON files in `data/`

### 12.3 Test Runners

| Type | Tool | Command |
|------|------|---------|
| Unit tests | pytest | `pytest tests/` |
| E2E tests | pytest + httpx | `pytest tests/e2e/` |
| Typecheck | mypy | `mypy src/` |
| Lint | ruff | `ruff check src/` |
| Build | Docker | `docker build -t claude-code-bot .` |

### 12.4 Verification Patterns
- **API verification:** `curl -s -X POST http://localhost:8000/chat -H 'Content-Type: application/json' -d '{"user_id":"test","message":"hello"}'`
- **Health check:** `curl -s http://localhost:8000/health`
- **DB verification:** Inspect `data/` directory for persisted memory files
- **CI checks:** pytest, mypy, ruff (to be configured)

---

## 13. Implementation Plan

### 13.1 Phases

| Phase | Scope | Milestone |
|-------|-------|-----------|
| 1a | Project skeleton: config loading (YAML + Pydantic), FastAPI app with `/health` | Bot boots, health check works |
| 1b | Main agent: claude-agent-sdk integration, persona from config, HTTP `/chat` endpoint | Can chat via HTTP |
| 1c | Memory: simple persistence layer, per-user history | Conversations persist across restarts |
| 1d | Telegram channel: aiogram adapter | Can chat via Telegram |
| 1e | Sub-agent infrastructure: registry, trigger/receive pattern | Developer can register and trigger sub-agents |
| 1f | Docker: Dockerfile + docker-compose.yml | `docker compose up` works |

### 13.2 Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| claude-agent-sdk API changes or limitations | M | H | Pin version, abstract behind thin wrapper |
| Mem0 complexity for MVP | L | M | Default to simple JSON/SQLite; Mem0 is optional |
| Telegram webhook setup complexity | M | L | Default to long-polling; webhook as opt-in |
| Context window limits with long conversations | M | M | Implement conversation truncation/summarization strategy |

### 13.3 Open Questions

- [ ] Exact claude-agent-sdk API for tool/sub-agent registration — Owner: developer (investigate SDK docs)
- [ ] Conversation history truncation strategy when approaching context limits — Owner: developer
- [ ] Mem0 integration details (if used as optional backend) — Owner: developer

---

## 14. Appendix

### 14.1 Glossary

| Term | Definition |
|------|------------|
| Persona | The bot's configured identity, tone, and behavioral constraints |
| Main Agent | The primary claude-agent-sdk agent embodying the persona |
| Sub-Agent | A developer-defined agent that the main agent can delegate tasks to |
| Channel | A communication adapter (HTTP, Telegram) through which users interact |
| Memory Store | Persistence layer for per-user conversation history |

### 14.2 References
- [claude-agent-sdk documentation](https://github.com/anthropics/claude-agent-sdk)
- [aiogram documentation](https://docs.aiogram.dev/)
- [FastAPI documentation](https://fastapi.tiangolo.com/)
- [Mem0 documentation](https://docs.mem0.ai/)

### 14.3 Change Log

| Date | Author | Change |
|------|--------|--------|
| 2026-01-31 | spec-interview | Initial MVP spec created |
