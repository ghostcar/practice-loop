# История изменений

| Дата | Файл | Изменение |
| --- | --- | --- |
| 2026-08-06 | `tracker-spec.md` | Создан по итогам интервью (5 раундов) |
| 2026-08-06 | `tracker-spec.md` | Решены открытые вопросы; разделы «Решённые/Осталось открытым» |
| 2026-08-06 | `AGENTS.md` | Полностью переработан в единый стиль (8 разделов, без Semantic Masking) |
| 2026-08-06 | `tracker-spec.md` | Раздел 8 «Telegram-бот (детализация)» |
| 2026-08-06 | `tracker-spec.md` | Разделы 9–11: сессии/штрафы, каталог (+30 задач), доска достижений |
| 2026-08-06 | `memory/*` | Создана система памяти: 7 файлов |
| 2026-08-06 | `AGENTS.md` | Правила обязательного использования памяти (раздел 7) |
| 2026-08-06 | Phase 1 (40 файлов) | Проект, Docker, FastAPI, User, Alembic, JWT, i18n, темы, шаблоны, тесты |
| 2026-08-06 | Phase 2 (+14 файлов) | Entity/LLMConfig/OptIn, шифрование, CRUD, seed, админка |
| 2026-08-06 | Phase 3 (+12 файлов) | ActivitySession/Log, Context Builder, OpenAI, JSON repair, tool calling, /tasks |
| 2026-08-06 | Phase 4 (+16 файлов) | XP-движок, достижения, дашборд v2, уведомления, сессии, приватность, Telegram-бот |
| 2026-08-07 | Phase 5 (+6 файлов) | TrainingDay, subtasks, LLM-промпты тренировки, pipeline |
| 2026-08-07 | Ruff + Tests | 181→0 ruff ошибок; 73→105 тестов |
| 2026-08-07 | Phase 6 (+15 файлов) | Points v2, gamification_config, ScheduleRule, BodyMeasurement, InventoryItem, Import, Seed v2 |
| 2026-08-07 | Phase 7 (+3 файла) | Import/Export (8 типов), CLI, chart APIs, дашборд с 4 графиками, компактный layout |
| 2026-08-07 | Phase 8 (+5 файлов) | Calendar (3 модели), Entity.intensity, `/calendar/check`, LLM-интеграция, schedule timeline chart |
| 2026-08-07 | Phase 9 (+1 файл) | PenaltyRedemption, PointsProfile CRUD, Threshold effects, Redemption tracking, Gamification editor |
| 2026-08-07 | Phase 10 (+1 файл) | Telegram bot v2: 8 команд с реальной логикой (LLM, gamification, stats), inline-кнопки, привязка аккаунта, уведомления, webhook |
| 2026-08-07 | Phase 11 (+1 файл) | Auto-Analysis Scheduler: asyncio фоновый триггер авто-анализа тренировок |
| 2026-08-07 | R0-R4 (+8 файлов) | v0.7 Audit, AGENTS.md, роли, CSRF, scheduler, LLM planner, frontend shell |
| 2026-08-07 | R5-R6 | Object-level auth, DESIGN.md compliance, dashboard редизайн |
| 2026-08-07 | Переаудит | CSRF fix, create_all удалён, 2 миграции (013-014), XSS-экранирование |
| 2026-08-07 | Session 28 | Cross-user auth тесты (22), README.md |
| 2026-08-07 | Session 29 | CDN → локальные static-файлы (TailwindCSS, HTMX, Chart.js) |
| 2026-08-07 | Session 30 | Интеграционные тесты (scheduler + Telegram), обновление зависимостей |
| 2026-08-08 | Session 31 | CI: 3 job'a (lint/test/migrations), [build-system] в pyproject.toml, ruff fix |
| 2026-08-08 | Session 32 | CI fix: repair type guard + migration boolean defaults (lint✅ test✅ migrations✅) |
| 2026-08-08 | Session 33 | Статические файлы: HTMX 2.0.10, Chart.js 4.5.1, TailwindCSS v4.3.3 |
| 2026-08-08 | Session 34 | Релиз 0.8.0: env vars, seed config, docker profiles, smoke-test, README deployment |
| 2026-08-09 | Session 35 | Деплой на VPS: db+app, nginx конфиг, seed тренировочного дня |
| 2026-08-09 | Session 39 | Frontend-фиксы: P0-баг `unacceptable→strong_aversion`, ~50 новых i18n ключей, градиенты/emoji/hover-translate удалены, CSS variables, skip-link, aria-* (nav, current, live, label, focus), motion easing cubic-bezier, 44px touch targets, CSRF в 8 формах; 153/153 теста ✅, ruff ✅, format ✅ |
| 2026-08-09 | Session 38 | Frontend-аудит по DESIGN.md: compliance ≈30%, P0-баг enum, hardcoded строки, 0 ARIA, no CSS vars |
| 2026-08-09 | Session 37 | Бэкенд-аудит: bif REM ↔ ADR, 6 пунктов вразрез |
| 2026-08-09 | Session 36 | TrainingLogEntry: журнал тренировки с inline-редактированием и внеплановыми записями |
| 2026-08-09 | Session 40 | Deferred-фиксы: production gate секретов (APP_ENV + 32 chars + change-me-... drain), bif-комментарий в AGENTS.md, store_raw_response flag + TTL 30 days (migration 016), расширение LLM validator (params_schema + enum + min/max), dashboard_v2 4→2 графика, calendar/inventory/import_data JS i18n, localhost:8443→app_url, XSS-fixtures (REM §A14) — **225/225 тестов ✅** |
| 2026-08-09 | Session 41 | `DEPLOY_VPS.md` — standalone VPS deployment runbook (14 шагов, bash-only, copy-paste для второго монитора); ссылка в README Deployment |
| 2026-08-09 | Session 42 | Troubleshooting в DEPLOY_VPS.md (раздел 13.1): «address already in use: 127.0.0.1:8000» — диагностика (`ss -ltnp`, `docker compose ps -a`), cleanup (`down --remove-orphans`, `fuser -k`), выбор профиля (`--profile prod` vs `--profile full`), типичные причины |
| 2026-08-09 | Session 43 | Troubleshooting в DEPLOY_VPS.md (раздел 13.2): «порт свободен, но bind всё равно падает» — iptables residue (`DOCKER`/`DOCKER-USER` chain flush), app crash loop (production gate / migration / race с db), conflict имени сети `tracker_default` между compose-проектами; diagnostic all-in-one блок |
| 2026-08-10 | Session 44 | Docker Compose prerelease fix: автоматический SQLite override заменён явным `docker-compose.dev.yml` на PostgreSQL; app ждёт healthy db через `depends_on`; сборка, миграции 001–016 и `/healthz` проверены |
| 2026-08-10 | Session 45 | SSL через Cloudflare: DEPLOY_VPS §8 развёрнут в три ветки — 🅰️ CF Origin Certificate (🟠 proxied, 15 лет, без автопродления), 🅱️ certbot-dns-cloudflare (⚪ DNS-only, DNS-01 без порта 80), 🅲️ certbot standalone (без CF); certbot убран из обязательного §0; §8.4 таблица ошибок CF (520/521/522/526); чисто runbook-only |
| 2026-08-10 | Session 46 | §8.🅰️ DEPLOY_VPS.md развёрнут click-by-click по CF Dashboard (SSL/TLS → Origin Server → Create Certificate); добавлены DNS-проверка и openssl-modulus sanity; убран дубль «Сохранить сертификаты»
| 2026-08-10 | Session 47 | Реальный домен `gorbunovr.ru`, уже есть wildcard CF Origin Cert (`*.gorbunovr.ru, gorbunovr.ru`). nginx -t emerg: старая `practice-loop` активна с битой ссылкой `/etc/nginx/ssl/origin.pem`. Фикс: `rm /etc/nginx/sites-enabled/practice-loop`. Warn: `listen ... http2` deprecated → `http2 on;` отдельно. DEPLOY_VPS §8.🅰️/🅱️ обновлён на современный синтаксис.

---

## Подробный changelog сессии 40 (2026-08-09)

- **`app/config.py`**: `app_env` env-toggle + `@model_validator` — при APP_ENV=production запрет `change-me-...` + проверка длины ≥32 для JWT/ENCRYPTION/TG_WEBHOOK. 11 тестов в `tests/test_config.py`.
- **`AGENTS.md`**: новая секция 0 «Архитектурный bif v0.8-actual ↔ v0.7-spec» с таблицей 6 расхождений и ADR-029/031/032/033/034.
- **`alembic/versions/016_add_store_raw_response.py`**: миграция (`llm_provider_configs.store_raw_response` + `activity_logs.raw_response_expires_at` + индекс).
- **`app/models/llm_config.py` + `app/models/activity_log.py`**: добавлены поля `store_raw_response`, `raw_response_expires_at`.
- **`app/llm/pipeline.py`**: helper `_resolve_raw_response(config, raw)` (TTL 30 дней) — во все 3 точки сохранения ActivityLog.
- **`app/llm/validator.py`**: `validate_params_against_schema(params, schema)` — типы/min/max/length/enum/optional.
- **`app/llm/pipeline.py`**: schema-validator подключён в цепочке после `validate_llm_response`.
- **`app/schemas/llm_config.py`**: `store_raw_response: bool = True` в `LLMConfig*`.
- **`app/api/llm_configs.py`**: `create_llm_config` принимает `store_raw_response` из формы.
- **`app/api/import_data.py`**: `app_url = str(request.url_root).rstrip("/")` в контексте шаблона.
- **`app/templates/dashboard_v2.html`**: 4 графика → 2 канваса + 2 summary-карточки.
- **`app/templates/calendar.html`**: JS `I18N` dict + `POLICY_LABEL` map; hardcoded EN → `t.calendar_*`.
- **`app/templates/inventory.html`**: JS `I18N` dict + `STATUS_LABEL` map.
- **`app/templates/llm_configs.html`**: показывает LLM mode + store_raw_response; 🤖 → SVG.
- **`app/templates/import_data.html`**: `localhost:8443` → `{{ app_url }}` (+ curl-example); 17 i18n ключей; эмодзи → SVG; градиент → solid.
- **`app/i18n/en.py` + `app/i18n/ru.py`**: +105 ключей (nav_*, dashboard_*, calendar_*, inventory_*, inv_*, import_*, telegram_*).
- **`docker-compose.yml` / `docker-compose.override.yml`**: `APP_ENV` default = production / dev override.
- **Новые тесты**: test_config (11), test_llm_raw_response_policy (5), test_llm_validator (32), test_xss_fixtures (24) — **72 новых**.
- `ruff check` ✅ | `ruff format` ✅ | `pytest`: **225 passed ✅** (153→225, +72)
