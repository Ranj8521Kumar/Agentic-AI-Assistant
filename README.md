# Agentic AI Enterprise Assistant Platform

> **Chat-first enterprise AI assistant** — control Gmail, Outlook, Slack, Microsoft Teams, Google Calendar/Meet, Jira, and Notion entirely through natural language chat.

---

## Architecture

```
Client Layer (Next.js)
  ├── Chat UI          — streaming SSE chat with tool execution cards
  ├── Login Page       — OAuth 2.0 (Google / Microsoft / Slack)
  └── Settings Page    — connect / disconnect integrations

API Gateway (FastAPI)
  ├── Auth Routing     — JWT Bearer + CORS + Rate Limiting
  └── Routes           — /api/auth  /api/chat  /api/integrations  /api/jobs

Backend Services
  ├── Chat Service     — conversation persistence, history retrieval
  ├── Agent (Brain)    — intent recognition, tool selection, multi-step execution
  ├── LLM Adapter      — OpenAI GPT-4o (function calling + streaming)
  └── Tool Registry    — 15 tools across 6 integrations

Integration Handlers
  Gmail · Slack · Calendar · Outlook · Teams · Jira · Notion

Data Layer
  ├── PostgreSQL        — users, workspaces, conversations, messages, audit log
  └── Redis             — sessions, rate limiting, background job queue

Background Worker (ARQ)
  └── Scheduled tasks, delayed sends, session cleanup cron
```

---

## Quick Start

### Prerequisites

- Python 3.13+
- Node.js 22+
- Docker (for Postgres + Redis)
- An OpenAI API key

### 1 — Start infrastructure

```bash
docker compose up -d
```

This starts PostgreSQL (port 5432) and Redis (port 6379).

### 2 — Backend setup

```bash
cd backend

# Create .env from the example
cp .env.example .env
# Edit .env — fill in OPENAI_API_KEY, FERNET_KEY, SECRET_KEY, OAuth credentials

# Generate FERNET_KEY:
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate SECRET_KEY:
python -c "import secrets; print(secrets.token_hex(32))"

# Install dependencies (uv creates .venv automatically)
uv sync

# Run database migrations
.venv/Scripts/python.exe -m alembic upgrade head    # Windows
# OR
.venv/bin/python -m alembic upgrade head             # Mac/Linux

# Start the API server
.venv/Scripts/uvicorn.exe app.main:app --reload --port 8000
```

Backend runs at **http://localhost:8000**
API docs at **http://localhost:8000/api/docs**

### 3 — Background worker (optional for scheduled tasks)

```bash
cd backend
.venv/Scripts/python.exe -m app.jobs.worker
```

### 4 — Frontend setup

```bash
cd frontend

# Create env file
echo "NEXT_PUBLIC_API_URL=http://localhost:8000/api" > .env.local

# Install dependencies
npm install

# Start dev server
npm run dev
```

Frontend runs at **http://localhost:3000**

---

## Environment Variables

All backend secrets live in `backend/.env`. See `backend/.env.example` for the full list.

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL async connection string |
| `REDIS_URL` | Redis connection string |
| `SECRET_KEY` | JWT signing secret (generate with `secrets.token_hex(32)`) |
| `FERNET_KEY` | Token encryption key (generate with `Fernet.generate_key()`) |
| `OPENAI_API_KEY` | OpenAI API key |
| `OPENAI_MODEL` | Model to use (default: `gpt-4o`) |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | Google OAuth client secret |
| `GOOGLE_REDIRECT_URI` | Must match Google Console setting |
| `MICROSOFT_CLIENT_ID` | Azure App Registration client ID |
| `MICROSOFT_CLIENT_SECRET` | Azure App Registration secret |
| `SLACK_CLIENT_ID` | Slack App client ID |
| `SLACK_CLIENT_SECRET` | Slack App client secret |
| `JIRA_BASE_URL` | Your Atlassian instance URL |

---

## Integration Setup

### Google (Gmail + Calendar)
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project → **APIs & Services → Credentials → OAuth 2.0 Client ID**
3. Enable **Gmail API** and **Google Calendar API**
4. Add `http://localhost:8000/api/auth/google/callback` as a redirect URI
5. Copy Client ID and Secret into `.env`

### Microsoft (Outlook + Teams)
1. Go to [Azure Portal](https://portal.azure.com/) → **App registrations → New**
2. Add redirect URI: `http://localhost:8000/api/auth/microsoft/callback`
3. Grant permissions: `Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`, `Chat.ReadWrite`
4. Copy Client ID, Secret, and Tenant ID into `.env`

### Slack
1. Go to [api.slack.com/apps](https://api.slack.com/apps) → Create App
2. Add redirect URI: `http://localhost:8000/api/auth/slack/callback`
3. Add scopes: `channels:read`, `chat:write`, `im:read`, `im:write`, `users:read`
4. Copy Client ID and Secret into `.env`

### Jira
- Generate an API token at [Atlassian account settings](https://id.atlassian.com/manage-profile/security/api-tokens)
- Connect from **Settings → Integrations → Jira** in the UI — paste your email + token

### Notion
- Create an integration at [notion.so/my-integrations](https://www.notion.so/my-integrations)
- Connect from **Settings → Integrations → Notion** — paste the integration token

---

## Key Request Flows

### Send Email
```
User: "Email sarah@company.com about the Q3 review"
  → Agent: intent=action, tool=gmail_send_email
  → Confirmation: "I'm about to send an email to sarah@company.com. Proceed?"
  → User: "yes"
  → Tool executes → Gmail API sends email
  → Agent: "Email sent to sarah@company.com"
```

### Send Slack Message
```
User: "Post 'Deployment done' to #releases"
  → Agent: tool=slack_send_message
  → Confirmation request
  → Slack API posts message
  → Agent: "Message posted to #releases"
```

### Schedule Meeting
```
User: "Schedule a 30-min call with john@co.com tomorrow at 2pm"
  → Agent: tool=calendar_schedule_meeting
  → Confirmation with details
  → Google Calendar API creates event + Meet link
  → Agent: "Meeting scheduled. Meet link: https://meet.google.com/..."
```

### Read Inbox
```
User: "Show my last 5 emails"
  → Agent: tool=gmail_read_inbox (no confirmation needed — read-only)
  → Gmail API fetches messages
  → Agent: formats and displays email list
```

---

## Adding a New Tool

1. **Create the tool class** in `backend/app/tools/definitions/`:

```python
# my_tools.py
from app.tools.base import BaseTool, ToolDefinition, ToolExecutionError

class MyNewTool(BaseTool):
    @property
    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name="my_tool_action",
            description="What this tool does",
            provider="my_provider",    # matches connected_account.provider
            requires_confirmation=True,
            parameters={
                "type": "object",
                "properties": {
                    "param1": {"type": "string", "description": "..."},
                },
                "required": ["param1"],
            },
        )

    async def execute(self, arguments, user_id, access_token):
        # Call external API, return structured dict
        return {"success": True, "summary": "Action completed."}
```

2. **Register it** in `backend/app/tools/registry.py` → `bootstrap_registry()`:

```python
from app.tools.definitions.my_tools import MyNewTool
registry.register(MyNewTool())
```

3. **Add a label** in `frontend/src/components/chat/ToolCallCard.tsx` → `TOOL_LABELS`:

```typescript
my_tool_action: "MyProvider · Action Name",
```

4. **Add the integration status** to `frontend/src/components/layout/Sidebar.tsx` → `INTEGRATIONS` array.

That's it — no changes to the agent or LLM adapter needed.

---

## Running Tests

```bash
cd backend

# Unit tests (no DB or credentials required)
.venv/Scripts/python.exe -m pytest tests/unit/ -v

# Integration tests (no real credentials — mocked)
.venv/Scripts/python.exe -m pytest tests/integration/ -v

# All tests
.venv/Scripts/python.exe -m pytest -v
```

---

## Project Structure

```
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, middleware, routers
│   │   ├── config.py            # Pydantic Settings
│   │   ├── dependencies.py      # DI: DB, Redis, current user
│   │   ├── api/                 # HTTP route handlers
│   │   ├── agent/               # Orchestrator (agentic loop)
│   │   ├── llm/                 # OpenAI adapter + prompt builder
│   │   ├── tools/               # Tool registry + 15 tool implementations
│   │   ├── integrations/        # (reserved for adapter wrappers)
│   │   ├── models/              # SQLAlchemy ORM models
│   │   ├── services/            # Business logic (auth, chat, audit)
│   │   ├── core/                # Security, rate limiting, logging
│   │   ├── db/                  # Session factory + Alembic migrations
│   │   └── jobs/                # ARQ background worker
│   └── tests/
│       ├── unit/                # Fast, no-IO tests
│       └── integration/         # App-level tests with mocked DB
│
├── frontend/
│   └── src/
│       ├── app/                 # Next.js App Router pages
│       ├── components/          # Chat UI, sidebar, tool cards
│       ├── lib/                 # API client, SSE stream parser
│       ├── store/               # Zustand state (auth, chat, streaming)
│       └── types/               # TypeScript interfaces
│
└── docker-compose.yml           # Local dev: Postgres + Redis
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 + TypeScript, Zustand, CSS Modules |
| Backend | FastAPI + Python 3.13 |
| Agent | Custom orchestrator (OpenAI function calling loop) |
| LLM | OpenAI GPT-4o |
| Database | PostgreSQL 16 (SQLAlchemy async + Alembic) |
| Cache / Queue | Redis 7 (ARQ background jobs) |
| Token Storage | Fernet symmetric encryption at rest |
| Auth | OAuth 2.0 (Google, Microsoft, Slack) + JWT |
