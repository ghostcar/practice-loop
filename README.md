# Practice Loop

> **v0.8.1-actual** — Personal-first activity tracker with LLM-assisted planning, advanced gamification, encrypted media vault, D/s delegation, and community features.

Consensual adult activity tracker. Privacy-first, single-user by default, multi-user model-ready.

---

## Features

### Core
- **Practice Catalog** — system + personal activities with params schemas, risk levels, opt-in per user
- **LLM Hybrid Pipeline** — AI picks tasks *from your approved catalog*, never generates content; full/abstract provider modes
- **Task Engine** — 11-state machine, LLM + deterministic generation, subtasks checklist
- **Sessions** — time-boxed activity sessions with accepted-freeze, append-only audit, cooperative mode
- **Gamification** — XP, levels, streaks, combos, achievements, configurable penalties + escalation + redemption, weekly challenges

### Training & Health
- **Training Module** — daily plans, subtask checklists, LLM end-of-day analysis, photo reports
- **Adaptive Programs** — 7-day AI-generated programs based on recovery logs
- **Health & Cycle Dashboard** — daily check-in (mood/energy/sleep/symptoms), cycle phase, `BodyCycleLog`
- **Measurements** — body measurements with morning/evening tracking and charts
- **Medication Organizer** — meds, pharmacy stock, schedule, intake log, doctor export

### Media Vault
- **AES-256-GCM Encryption** at rest for all uploaded media
- **Anti-Leak Watermarking** — semi-transparent overlay with user ID + timestamp
- **Video Proof** — key frame extraction from video proofs
- **pHash Anti-Spoofing** — dHash/pHash duplicate detection + EXIF authenticity audit
- **Multi-Signature Proofing** — HMAC cryptographic integrity verification
- **AI Visual Comparison** — multimodal "Before/After" progression analysis
- **Auto AI Tagging & Smart Albums** — semantic tag generation and album categorization
- **Media Timeline** — chronological proof timeline at `/media/timeline`

### Analytics & AI Agents
- **Correlation Graph** — interactive multi-variable correlation matrix at `/analytics/graph`
- **Analytics Engine v2** — pairwise Pearson correlation across all modules, top correlation triplets, dynamic insight findings at `/insights/analytics`
- **Trajectory & Medical Export** — `/insights/trajectory`, `/insights/report`, `/insights/export-medical`
- **AI Persona Builder** — 4 archetypes (Strict Keyholder, Caring Curator, Endurance Trainer, Anonymous Observer), strictness scale 1–5, tone of voice, proactivity level
- **Safety & Burnout Auditor** — burnout risk index 0–100%, protective load freeze at >70%
- **Pre-Session Readiness Test** — 5-question physical readiness score (0–100%), auto-throttle if <30%
- **Monthly Visual Reports** — HTML progress reports from activity history
- **Automation Triggers** — AI analyzes 14-day history, auto-creates penalty/emergency-care triggers
- **Weekly AI Digest** — weekly summary + predictive next-week goal (75–98.5%)
- **LLM Exchange Hub** — cross-domain prompt export, external-model response parsing, plan hydration (`/llm/exchange`)
- **Voice STT Intake** — voice note transcript → tasks & health metrics

### Gamification & Social
- **Community Leagues** — Bronze→Silver→Gold→Master tier promotions
- **Weekly 1-on-1 Duels** — challenge engine with automatic winner determination
- **Quests Hub** — daily/weekly/streak quests with XP claims at `/achievements/quests`
- **Community Top Agent** — autonomous persona (name, strictness 1–5), feed posts, profile block delegation (tasks/training/care/timer)
- **Public Tournaments** — compliance/xp/care/lock metrics, top-3 badges, iCal feed
- **Co-Governance Roles** — co_top, keyholder, trainer, care_curator, tournament_organizer
- **Equipment Maintenance Tracker** — hygiene and maintenance check-in reminders
- **Social Platform** — profiles, connections, verification, anonymous leaderboard, pillory
- **Achievements Board** — anonymized public showcase

### D/s & Delegation
- **D/s Portal** — Keyholder / Submissive role system (ADR-129)
- **D/s Command Center** — multi-submissive portal with cohort analytics at `/ds/portal`
- **Capability Grants** — 7 delegation scopes, invite codes, Safe Word instant revoke
- **AI Keyholder Wheel** — random lock extensions / key rewards / seal inspections
- **Wear Check-Ins & OCR Verification** — tag seal inspection center with OCR scanning & verification
- **Cross-Activity Dead Man's Switch** — universal monitor across chastity seals, daily tasks, medications, and general heartbeats at `/dms`
- **Lock Timer** — chastity management with session templates and violation tracking
- **Full delegation model** — submissive retains digital autonomy, can emulate any task

### Platform & Media Security
- **Points Economy v2** — balance, profiles, transaction history, penalty redemption
- **Calendar & Scheduling** — weekly availability windows, vacation overrides, day rules
- **iCal Feed** — RFC 5545 export of active tournaments at `/calendar/feed.ics`
- **Media Showcase & Dynamic Drops** — One-Time Burn-on-Read, Dynamic Countdown (+15m/+1h/+24h quick adjust), and Immutable Permanent Showcase
- **Deep EXIF Stripper & Privacy Masking** — automatic GPS/metadata sanitization with HMAC proof, Gaussian blur & blackout redaction
- **Smart Albums & Encrypted Batch Export** — auto-categorized albums, password-protected ZIP export, batch deletion with permanent protection
- **Inventory** — items, photos, drag-and-drop sorting, shopping list
- **Telegram Bot** — aiogram 3.x, webhook + push notifications
- **Telegram Broadcast Engine** — direct AI-agent alerts via bot
- **Billing & Multi-Gateway Payments** — subscription tiers + promotions, Stripe / Telegram Stars / Crypto / ЮKassa checkout, webhooks, invoices
- **Promocodes & Gift Subscriptions** — `POST /billing/promocodes/claim`
- **Digital Achievement Certificates** — public verification at `GET /certificates/{id}/verify`
- **2FA protection** — optional authenticator-app TOTP (`/security/totp/*`) plus legacy PIN Shield (`POST /security/verify-pin`) for Media Vault and D/s controls
- **Media Vault v2 One-Time Links** — burn-on-read tokens at `/media/one-time-token`
- **Import/Export** — CSV/JSON templates, full data export, API push
- **Admin Panel** — catalog seed, LLM presets, user management, tier management
- **i18n** — EN/RU, dark/light/system themes, 3 accent sets (ember/sage/slate)

---

## Stack

| Layer | Technology |
|-------|-----------|
| Backend | FastAPI (Python 3.11+), SQLAlchemy 2.0 async, Pydantic v2 |
| Database | PostgreSQL 15 (prod), SQLite (dev/tests) |
| Migrations | Alembic |
| Auth | JWT cookies, CSRF double-submit, optional TOTP + PIN sensitive-operation verification |
| Frontend | Jinja2, TailwindCSS, HTMX, Chart.js, ES modules |
| LLM | OpenAI-compatible API (BYOK): Omniroute (default), Groq, OpenRouter |
| Bot | aiogram 3.x (Telegram) |
| Media | AES-256-GCM (cryptography), Pillow (watermark/pHash), OpenCV (video frames) |
| Infra | Docker Compose, Nginx + SSL (Let's Encrypt) |

---

## Quick Start

### Prerequisites
- Python 3.11+, Docker & Docker Compose, PostgreSQL 15

### Setup

```bash
git clone https://github.com/ghostcar/practice-loop.git
cd practice-loop
cp .env.example .env
# Edit .env with your secrets
docker compose up -d
```

App available at `https://localhost:8443` (self-signed SSL in dev).

### Development (without Docker)

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
createdb tracker_dev
export DATABASE_URL=postgresql+asyncpg://localhost/tracker_dev
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql+asyncpg://...` | DB connection string |
| `JWT_SECRET_KEY` | *(required)* | JWT signing secret (min 32 chars) |
| `CREDENTIALS_ENCRYPTION_KEY` | *(required)* | Separate key for API key encryption |
| `TG_BOT_TOKEN` | — | Telegram bot token from @BotFather |
| `TG_BOT_USERNAME` | — | Bot username |
| `TG_POLLING` | `false` | Use polling instead of webhook (local dev) |
| `TG_WEBHOOK_BASE_URL` | `https://localhost:8443` | Public URL for Telegram webhook |
| `TG_AUTO_ANALYSIS_TIME` | `23:00` | Daily training analysis time (HH:MM) |
| `TG_AUTO_ANALYSIS_TZ` | `UTC` | IANA timezone for analysis time |

---

## Deployment

> Full step-by-step VPS runbook: [`DEPLOY_VPS.md`](DEPLOY_VPS.md) — 14 steps from zero to `https://your-domain.com`.

### Production (host nginx + certbot)

```bash
git clone https://github.com/ghostcar/practice-loop.git && cd practice-loop
cp .env.example .env  # fill secrets
docker compose up -d db app
# Configure nginx → 127.0.0.1:8000, obtain SSL with certbot
sudo certbot --nginx -d your-domain.com
```

**Seed (optional):**
```bash
python seed_prod.py --email your@email.com \
  --database-url postgresql+asyncpg://tracker:PASSWORD@localhost:5432/tracker
```

**Backups:**
```bash
0 3 * * * pg_dump -U tracker tracker | gzip > /backups/tracker_$(date +\%Y\%m\%d).sql.gz \
  && find /backups -name 'tracker_*.sql.gz' -mtime +7 -delete
```

### Full stack (built-in nginx)
```bash
# Place SSL certs in ./nginx/ssl/
docker compose --profile full up -d
```

---

## Architecture

```
app/
├── api/            # HTTP routes (thin — call services/agents)
│   ├── auth.py, admin.py, entities.py, tasks.py, training.py
│   ├── points_v2.py, calendar.py, import_data.py, llm_configs.py
│   ├── ds.py, insights_analytics.py, media_timeline.py
│   ├── persona_builder.py, health_dashboard.py
│   ├── billing.py, quests.py, community_agent.py, llm_exchange.py
│   ├── media_vault_v2.py, calendar_v2.py, automation_triggers.py
│   ├── certificates.py, promocodes.py, security_2fa.py
│   └── ...
├── agent/          # AI engines
│   ├── training_generator.py   # 7-day adaptive training programs
│   ├── community_leagues.py    # Bronze→Master league promotions
│   ├── safety_auditor.py       # Burnout risk + load freeze
│   ├── media_comparison.py     # AI Before/After visual comparison
│   ├── media_tagging.py        # Semantic auto-tagging & smart albums
│   ├── persona_builder.py      # AI Persona archetypes + tone of voice
│   ├── equipment_maintenance.py # Hygiene/maintenance reminders
│   ├── weekly_duels.py         # 1-on-1 weekly challenge engine
│   ├── pdf_reports.py          # Monthly visual progress reports
│   ├── stress_test.py          # Pre-session readiness scorer
│   ├── community_agent.py      # Community Top Agent + tournaments
│   ├── community_roles.py      # Co-governance roles
│   ├── automation_triggers.py  # AI auto-triggers from history
│   ├── weekly_digest.py        # Weekly AI digest + prediction
│   └── voice_hydration.py      # Voice STT intake
├── billing/        # Multi-gateway payment dispatcher + webhooks
├── analytics/      # Correlation engine (Pearson, clusters)
├── media/          # Media processing
│   ├── crypto.py       # AES-256-GCM encryption at rest
│   ├── watermark.py    # Anti-leak watermark overlay
│   ├── video_frames.py # Key frame extraction from video proofs
│   ├── anti_spoofing.py # dHash/pHash + EXIF audit
│   └── multi_sig.py    # HMAC multi-signature proofing
├── models/         # SQLAlchemy models
├── schemas/        # Pydantic v2 schemas
├── llm/            # LLM pipeline: context builder, client, validator, repair
├── gamification/   # XP engine, achievements, handler
├── telegram/       # Bot handlers + broadcast engine
├── training/       # Auto-analysis scheduler
├── i18n/           # EN/RU translations
├── templates/      # Jinja2 HTML templates
└── static/         # Icons sprite, JS modules, CSS
```

### Key Models

| Model | Purpose |
|-------|---------|
| `User` | Account with role (user/moderator/admin) |
| `Entity` | Practice template with params schema and gamification config |
| `UserEntityOptIn` | Per-user practice: enabled, attitude, frequency, due dates |
| `ActivityLog` | Task execution (11-state machine), params, subtasks, LLM usage |
| `TrainingDay` | Daily training plan grouping activity logs |
| `AdaptiveProgram` / `AdaptiveProgramStep` | AI-generated multi-day programs |
| `UserProgress` | XP, level, streak, combo, points balance |
| `ActivitySession` | Time-boxed session with accepted-freeze + audit |
| `UserAgentPersona` | AI Persona archetype, tone, strictness settings |
| `UserDuel` | 1-on-1 weekly duel records |
| `UserLeagueTier` | Community league tier (Bronze/Silver/Gold/Master) |
| `Quest` / `UserQuest` | Daily/weekly/streak quests with XP claims |
| `SubscriptionTier` / `TierFeatureGrant` | Billing tiers + feature grants |
| `PaymentInvoice` | Multi-gateway payment records; schema created by migration `082_add_missing_module_tables` |
| `CommunityTournament` / `CommunityTournamentEntry` | Public tournaments + leaderboards |
| `CommunityMemberRole` | Co-governance roles (co_top, keyholder, trainer, ...) |
| `AutomationTrigger` | AI-generated condition/action rules |
| `ManagedSubmissive` / `CapabilityGrant` | D/s delegation model (ADR-129) |
| `BodyCycleLog` | Health cycle + daily check-in data |
| `PromoCode` | Promotional codes for tier grants |
| `LLMProviderConfig` | BYOK provider: URL, key (encrypted), model, usage stats |

### LLM Pipeline

```
Catalog (opt-in) → Context Builder → LLM → JSON Repair → Validator → ActivityLog
                       ↑                                       ↓
                  History, stats,                        Failure: retry
                  penalties, calendar               (up to 3 attempts, then error)
```

Modes:
- **full** (default): LLM sees practice names, descriptions, categories
- **abstract**: opaque IDs only (for strict content-filtering providers)

---

## Testing

```bash
# Full suite (SQLite in-memory, 1300+ tests)
pytest tests/ -v

# Lint + format (pinned to the CI version)
ruff==0.5.7 check app/ cli.py tests/ seed_prod.py
ruff==0.5.7 format --check app/ cli.py tests/ seed_prod.py
```

Key test suites:
- `test_icon_pack.py` — sprite coverage & no-emoji watchdog
- `test_audit_s57.py` — отсутствие несанкционированных inline scripts, DSL safety
- `test_transaction_boundary.py` — commit isolation
- `test_cross_user_auth.py` — cross-user authorization (22 tests)
- `test_6_next_extensions.py` — Broadcast, Promocodes, Reports, Readiness, Certificates, 2FA
- v0.8.1: `test_billing_and_gateways.py`, `test_community_top_agent.py`,
  `test_tournament_rewards.py`, `test_automation_triggers_and_tts.py`,
  `test_voice_hydration.py`, `test_llm_exchange.py`, `test_encrypted_media_vault_and_ai.py`,
  `test_ds_portal_suite.py`, `test_multi_top_and_digest.py`, `test_persona_health_and_duels.py`
- `test_localization.py` — i18n consistency: EN/RU parity, placeholders, template & JS keys,
  page-i18n JSON blocks, locale detection (15 tests)

Browser E2E (`npm run test:browser`, `--grep @smoke` in CI):
- `portal.spec.ts` — 8 tests: 2×`@smoke` (navigation, session flow), 2×`@a11y`
  (axe wcag2a/2aa/wcag21a/aa across **47 user routes + 7 admin routes × dark/light**),
  4×`@usability` (keyboard focus, no horizontal overflow, reduced motion, timer discoverability).
  Protected/off-navigation coverage includes `/admin/tiers`, `/social/leaderboard`,
  `/social/pillory`, `/certificates/{id}/verify`, billing, DMS, communities and insights pages.
  The admin test promotes a disposable test user via SQL only; no production self-promotion path exists.
- Run the a11y audit alone with `npm run test:a11y`; usability with `npm run test:usability`.

---

## Architectural Decisions

Key decisions recorded in `docs/adr/` and `memory/DECISIONS.md`:

| ADR | Decision |
|-----|---------|
| ADR-029 | Penalties always applied on interruption; escalation + redemption preserved |
| ADR-030 | LLM `full` (default) and `abstract` modes — per-provider setting |
| ADR-031 | Entity remains single model (no Template/Variant/UserPractice split) |
| ADR-032 | Training stays as separate full-featured page |
| ADR-033 | All secondary modules in main navigation |
| ADR-034 | `raw_llm_response` optional; usage metrics always stored |
| ADR-106 | Opt-in = approval boundary; risk_level is informational |
| ADR-129 | D/s delegation: digital autonomy always preserved; emulation always available |

---

## Privacy

- All user data private by default
- API keys encrypted with separate `CREDENTIALS_ENCRYPTION_KEY`
- Media files encrypted with AES-256-GCM at rest
- No analytics, telemetry, or external tracking
- Full data export: `/privacy/export`, `/import/export/full`
- Account deletion with anonymized data retention option

---

## License

MIT
