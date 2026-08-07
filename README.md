# Practice Loop

Consensual adult activity tracker with LLM-assisted planning, gamification, and privacy-first design.

> Version 0.7.0 — stabilization release.

## Overview

Practice Loop helps you build and maintain personal practice routines. It combines:

- **Deterministic scheduler** — practices rotate on your schedule, with due dates and retry blocks
- **LLM planner** — optional AI assistance to compose balanced daily plans from your enabled practices
- **Gamification** — configurable points, XP, streaks, achievements, and penalty redemption
- **Calendar** — define weekly availability windows and vacation overrides
- **Training mode** — daily plans with subtask checklists and end-of-day analysis
- **Telegram bot** — mobile access to tasks, stats, and notifications

The app is designed for **one user, private use**. Multi-user catalog sharing supports optional community practice templates with moderation.

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python 3.11+), SQLAlchemy 2.0 async |
| Database | PostgreSQL 15 (prod), SQLite (dev/tests) |
| Migrations | Alembic |
| Auth | JWT cookies, CSRF double-submit |
| Frontend | Jinja2, TailwindCSS, HTMX, Chart.js |
| LLM | OpenAI-compatible API (configurable provider) |
| Bot | aiogram 3.x (Telegram) |
| Infra | Docker Compose, Nginx |

## Quick Start

### Prerequisites

- Python 3.11+
- Docker & Docker Compose
- PostgreSQL 15 (for production)

### Setup

```bash
# Clone
git clone https://github.com/ghostcar/practice-loop.git
cd practice-loop

# Create .env (see Configuration section)
cp .env.example .env
# Edit .env with your secrets

# Start
docker compose up -d
```

The app will be available at `https://localhost:8443` (self-signed SSL in dev).

### Development (without Docker)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Create database
createdb tracker_dev
export DATABASE_URL=postgresql+asyncpg://localhost/tracker_dev

# Run migrations
alembic upgrade head

# Start dev server
uvicorn app.main:app --reload --port 8000
```

## Configuration

All settings via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | Database connection string |
| `JWT_SECRET_KEY` | *(required)* | JWT signing secret (min 32 chars) |
| `CREDENTIALS_ENCRYPTION_KEY` | *(required)* | Separate key for API key encryption |
| `TG_BOT_TOKEN` | — | Telegram bot token from @BotFather |
| `TG_BOT_USERNAME` | — | Bot username (e.g. `my_tracker_bot`) |
| `TG_POLLING` | `false` | Use polling instead of webhook (local dev) |
| `TG_WEBHOOK_BASE_URL` | `https://localhost:8443` | Public URL for Telegram webhook |
| `TG_AUTO_ANALYSIS_TIME` | `23:00` | UTC time for daily training analysis |

## Architecture

```
app/
├── api/            # HTTP routes (thin — call services)
│   ├── auth.py         # Registration, login, logout, locale/theme
│   ├── admin.py        # Admin dashboard (role-protected)
│   ├── calendar.py     # Availability calendar CRUD + check
│   ├── dashboard.py    # Dashboard, sessions, achievements, privacy
│   ├── entities.py     # Practice catalog CRUD + opt-in
│   ├── import_data.py  # CSV/JSON import/export
│   ├── llm_configs.py  # LLM provider configuration
│   ├── points_v2.py    # Points economy, measurements, inventory, schedule
│   ├── tasks.py        # Task generation, completion, interruption
│   └── training.py     # Training day plans, subtasks, analysis
├── models/         # SQLAlchemy models
├── schemas/        # Pydantic request/response schemas
├── services/       # Business logic (scheduler, etc.)
├── llm/            # LLM pipeline: context builder, client, validator, repair
├── gamification/   # XP engine, achievements, handler
├── telegram/       # Telegram bot handlers
├── training/       # Auto-analysis scheduler
├── i18n/           # EN/RU translations
├── templates/      # Jinja2 HTML templates
└── static/         # Static assets
```

### Key Models

| Model | Purpose |
|-------|---------|
| `User` | Account with role (user/moderator/admin) |
| `Entity` | Practice template — catalog item with gamification config |
| `UserEntityOptIn` | Per-user practice settings: enabled, attitude, frequency, due dates |
| `ActivityLog` | Task execution record with status, params, subtasks |
| `TrainingDay` | Daily training plan grouping activity logs |
| `UserProgress` | XP, level, streak, combo, points balance |
| `ActivitySession` | Time-boxed activity session |

### LLM Pipeline

```
User request → Context Builder → LLM Client → JSON Repair → Validator → Response
                    ↑                                              ↓
              User history,                                 Failure: retry
              due practices,                                (up to 3 attempts)
              calendar
```

Two modes:
- **full** (default): LLM sees practice names, descriptions, categories
- **abstract**: LLM sees only opaque IDs (for strict content-filtering providers)

## Testing

```bash
# All tests (SQLite in-memory, 120+ tests)
pytest tests/ -v

# Lint + format
ruff check app/
ruff format --check app/
```

Test categories:
- `test_healthz.py` — health check
- `test_entities.py` — CRUD, opt-in
- `test_training.py` — training days, subtasks, gamification
- `test_sessions.py` — session lifecycle
- `test_repair.py` — JSON repair strategies
- `test_cross_user_auth.py` — cross-user authorization (22 tests)
- `conftest.py` — fixtures (SQLite, auth client with CSRF)

## CI

GitHub Actions on push to `main`:

1. **lint**: ruff check + ruff format --check
2. **test**: pytest on PostgreSQL 15

## Decisions

Key architectural decisions are recorded in `memory/DECISIONS.md` (ADR format). Notable:

- **ADR-029**: Penalties preserved with escalation + redemption (not removed)
- **ADR-030**: LLM `full` (default) and `abstract` modes — user-selectable per provider
- **ADR-031**: Entity remains a single model (not split into Template/Variant/UserPractice)
- **ADR-032**: Training stays as a separate full-featured page
- **ADR-033**: Secondary modules (Points, Measurements, Inventory) stay in main navigation
- **ADR-034**: `raw_llm_response` storage is optional; usage metrics stored separately

## License

MIT

## Privacy

- All user data is private by default
- API keys encrypted with a separate key (`CREDENTIALS_ENCRYPTION_KEY`)
- No analytics, telemetry, or external services
- Raw LLM responses are not stored by default
- Exports available via `/privacy/export` and `/import/export/full`
