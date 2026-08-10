# Журнал сессий

Формат: `дата — Сессия N: тема` → что обсуждали → результаты/договорённости → артефакты.
Новая запись добавляется **в конце каждой сессии**.

## 2026-08-06 — Сессия 1: Интервью (базовое)
- Обсуждали: скоуп, пользователи, язык UI, деплой, LLM, провайдеры, ошибки LLM, штрафы, тесты, UI, админка, приватность, геймификация, каталог, уведомления, AGENTS.md, подписки, сессии, бэкапы, логи.
- Артефакты: `tracker-spec.md`.

## 2026-08-06 — Сессия 2: Открытые вопросы
- Решения: aiogram 3.x, Omniroute+Groq+OpenRouter, простая регистрация, кастомная геймификация, locale.
- Артефакты: разделы «Решённые/Осталось открытым» в спеке.

## 2026-08-06 — Сессия 3: AGENTS.md + Telegram-бот
- AGENTS.md переработан, бот: 6 команд, вебхук, уведомления, код-привязка.
- Артефакты: новый AGENTS.md, раздел 8 спеки.

## 2026-08-06 — Сессия 4: Сессии/штрафы, каталог, доска достижений
- Детализация механик: сессии created/active/ended, штрафы с эскалацией, комбо, челленджи, каталог 30+, доска.
- Артефакты: разделы 9–11 спеки.

## 2026-08-06 — Сессия 5: Система памяти
- Созданы memory/*, правила чтения/обновления.
- Артефакты: 7 memory-файлов, правка AGENTS.md.

## 2026-08-06 — Сессия 6: Phase 1 — Фундамент
- Проект, Docker, FastAPI, User, Alembic, JWT, i18n, темы, шаблоны, тесты.
- Артефакты: 40 файлов.

## 2026-08-06 — Сессия 7: Phase 2 — Каталог и конфиги
- Entity, OptIn, LLMProviderConfig, шифрование, CRUD, seed, админка.
- Артефакты: +14 файлов (всего 56).

## 2026-08-06 — Сессия 8: Phase 3 — LLM-пайплайн
- ActivitySession, ActivityLog, Context Builder, OpenAI-клиент, JSON repair, tool calling, /tasks.
- Артефакты: +12 файлов (всего 68).

## 2026-08-07 — Сессия 9: Phase 4 — UI, сессии, геймификация
- UserProgress, Achievement, Notification, XP-движок, дашборд v2, доска, уведомления, сессии, приватность, Telegram-бот.
- Артефакты: +16 файлов (всего 84).

## 2026-08-07 — Сессия 10: Тесты и линтинг
- Ruff 181→0 ошибок, 73 теста, JSONB→JSON, pyproject.toml.
- Артефакты: +7 тестовых файлов.

## 2026-08-07 — Сессия 11: Training (тренировки)
- TrainingDay, subtasks, LLM-промпты, pipeline, геймификация training mode.
- Артефакты: +6 файлов.

## 2026-08-07 — Сессия 12: Points v2 + Measurements + Inventory + Schedule + Import
- Points v2 engine, gamification_config JSON, PenaltyConfig, ScheduleRule, BodyMeasurement, InventoryItem, Import module, Seed v2, 100 тестов.
- Артефакты: +15 файлов (всего 105).

## 2026-08-07 — Сессия 13: Import/Export + Charts + Layout fix
- Import/export: 8 типов шаблонов, CSV/JSON upload, API-push, full backup, CLI, веб-страница
- Charts: 2 новых API (category-breakdown, completion-rate), 4 графика на дашборде, графики на training/sessions/achievements
- Layout: компактная вёрстка всех страниц (chart heights ÷2, padding сокращён)
- Docker: исправлены миграции, nginx.conf, порты 8080/8443, SSL-сертификаты
- Git: инициализирован, 3 коммита запушены на GitHub
- Артефакты: +3 файла (import_data.html, cli.py), изменены 10+ шаблонов

## 2026-08-07 — Сессия 14: Calendar + Schedule Timeline + Интеграция
- Calendar: 3 модели (CalendarTemplate, AvailabilityWindow, CalendarOverride), Entity.intensity
- API: CRUD + `/calendar/check` + `is_available()` + `get_day_schedule()`
- LLM-интеграция: календарь в context_builder → промпт
- Веб: `/calendar` с timeline-баром, `/tasks` с индикатором доступности
- Schedule: weekly timeline chart (горизонтальные бары по дням)
- Миграция 007
- Тесты 105/105
- Артефакты: +5 файлов (calendar модель, схема, API, шаблон, миграция), изменены 6 файлов

## 2026-08-07 — Сессия 15: Penalty & Points v2 — штрафы и баллы
- PenaltyRedemption: модель + миграция 008 — отслеживание отработок штрафов
- Redemption API: список pending, complete (возврат баллов), skip
- Handler: авто-создание PenaltyRedemption при прерывании задачи
- PointsProfile: CRUD + назначение на сущность + удаление
- Threshold effects: уведомления при пересечении порогов (negative/warning/good)
- Gamification editor: PUT /entities/{id}/gamification
- Points page: redemption list с Complete/Skip, профили, назначение
- Тесты 105/105, ruff 0 ошибок
- Артефакты: +1 модель, +1 миграция, изменены handler, API, шаблон

## 2026-08-07 — Сессия 16: Telegram Bot v2 — реальный бот
- Полный реврайт app/telegram/bot.py: 8 команд с реальной логикой
- /next вызывает LLM-пайплайн (generate_task), показывает карточку с inline-кнопками
- /done и /interrupt интегрированы с gamification handler (XP, streak, points, PenaltyRedemption)
- /stats показывает реальную статистику из БД (XP, level, streak, points)
- /session показывает статус активной сессии
- /settings переключает язык (inline EN/RU кнопки)
- Привязка аккаунта: 6-значный код через /profile/telegram-link-code, /link CODE
- User.telegram_chat_id, telegram_link_code, telegram_link_code_expires (миграция 009)
- Уведомления: send_telegram_notification() + хук _send_tg_notifications в gamification handler
- Webhook: авто-регистрация при старте (setup_webhook в lifespan)
- Дашборд: карточка «Link Telegram» с JS (generateLinkCode, checkTelegramStatus)
- config: tg_bot_username, tg_webhook_base_url
- Тесты 105/105, ruff 0 ошибок
- Артефакты: +1 миграция, переписан bot.py, изменены handler, dashboard, main, config, user model, dashboard шаблон

## 2026-08-07 — Сессия 17: Polling-режим бота
- Добавлен tg_polling флаг в config (True = локальная разработка, False = production webhook)
- start_polling(): удаляет webhook, запускает dp.start_polling() как фоновую asyncio задачу
- stop_polling(): graceful cancel при shutdown приложения
- lifespan: автоматический выбор webhook/polling по флагу
- Использование: tg_polling=true + tg_bot_token=xxx в .env
- Артефакты: изменены bot.py, main.py, config.py

## 2026-08-07 — Сессия 18: Auto-Analysis Scheduler
- Фоновый триггер авто-анализа тренировок: asyncio loop, проверяет время каждую минуту
- В `tg_auto_analysis_time` (по умолчанию 23:00 UTC) сканирует все TrainingDay со статусом active/planned
- Для каждого вызывает `analyze_training_day` (LLM-анализ + генерация плана на завтра)
- Без внешних зависимостей (без APScheduler) — чистый asyncio
- Запуск/остановка в lifespan: `start_auto_analysis()` / `stop_auto_analysis()`
- Артефакты: +1 файл (scheduler.py), изменены config.py, main.py

## 2026-08-07 — Сессия 19: v0.7 Аудит и интервью (R0)
- Прочитаны REMEDIATION_SPEC.md (внешний аудит, 18 дефектов) и AGENTS_.md (новая инструкция)
- Интервью по 6 ключевым архитектурным решениям:
  1. Штрафы — оставить как есть (ADR-029)
  2. LLM-режимы — full + abstract, настраивается в провайдере (ADR-030)
  3. Entity — оставить единой моделью (ADR-031)
  4. Training — оставить отдельной страницей (ADR-032)
  5. Вторичные модули — оставить в главном меню (ADR-033)
  6. raw_llm_response — опциональное хранение + usage-метрики отдельно (ADR-034)
- AGENTS.md обновлён: приоритет документов, LLM-режимы, актуальные фазы
- AGENTS_.md удалён
- DECISIONS.md: +6 ADR (029–034)
- CONTEXT.md: убран «код не написан»
- STATUS.md: секция v0.7 Audit & Interview
- Артефакты: изменены AGENTS.md, DECISIONS.md, CONTEXT.md, STATUS.md, SESSIONS.md; удалён AGENTS_.md

## 2026-08-07 — Сессия 20: R1 — воспроизводимость (часть 1)
- pyproject.toml: единый источник зависимостей, bcrypt<4.1, python-dotenv
- requirements.txt: перегенерирован из pyproject.toml
- Версия: 0.5.0 → 0.7.0 (pyproject.toml + main.py)
- create_all: оставлен с предупреждением (Alembic для production)
- Артефакты: изменены pyproject.toml, requirements.txt, main.py
- CI: .github/workflows/ci.yml (ruff lint + pytest на PostgreSQL 15)
- Миграции: subtasks String→JSON, next_day_suggestion Text→JSONB — расхождения зафиксированы, не блокируют (create_all создаёт правильные типы)

## 2026-08-07 — Сессия 21: R2 — Безопасность и авторизация
- CSRF: двойная кука (csrf_token), HTMX auto-include X-CSRF-Token, meta tag в base.html
- Идемпотентность: complete_once/interrupt_once в app/security.py, применены в /tasks
- Отдельный ключ шифрования: CREDENTIALS_ENCRYPTION_KEY ≠ JWT_SECRET_KEY
- Безопасные cookies: HttpOnly для access_token, path=/, очистка при logout
- OwnershipChecker: хелпер для проверки владельца объекта (создан, ждёт применения)
- base.html: добавлен блок scripts (требование DESIGN.md)
- Артефакты: +1 файл (security.py), изменены auth, tasks, config, encryption, dashboard, main, base.html

## 2026-08-07 — Сессия 22: R3 — Роли, object-level auth, scheduler
- User.role + миграция 010 (user/moderator/admin), require_admin() dependency
- OwnershipChecker применён: tasks, training, sessions, achievements, notifications
- /admin защищён — обычный пользователь получает 403
- unacceptable → strong_aversion: model, schemas, pipeline, tests
- Soft scheduler: app/services/scheduler.py — get_due_practices, set_next_due, set_retry_block
- UserEntityOptIn: next_due_at, retry_not_before_at (миграция 011)
- Tasks: показаны due practices, авто next_due/retry после complete/interrupt
- Артефакты: +4 файла (2 миграции, scheduler, services/__init__), изменены 9 файлов

## 2026-08-07 — Сессия 23: R4 — LLM planner + фиксы типов
- LLMProviderConfig.llm_mode (full/abstract) — переключается в настройках провайдера
- context_builder: format_context_abstract() для opaque-режима (только ID и категории)
- app/llm/validator.py: валидация entity_id в allowed set, схемы параметров
- Pipeline: авто-выбор формата по llm_mode, валидация после парсинга
- Deterministic fallback: /tasks/generate-deterministic — выбор из due practices без LLM
- tasks.html: список due practices с цветовой кодировкой, кнопка fallback
- Миграция 012: subtasks String→JSON, next_day_suggestion Text→JSONB — типы исправлены
- Артефакты: +2 файла (validator.py, миграция 012), изменены 4 файла

## 2026-08-07 — Сессия 24: R5 — Frontend shell
- active_nav: переменная во всех шаблонах, подсветка текущей страницы в навигации
- Навигация упрощена: dashboard, tasks, training, catalog, points, admin
- CSRF hidden поля в формах переключения языка/темы
- innerHTML аудит: всё использование — рендеринг серверных данных (безопасно)
- scripts блок в base.html
- active_nav проброшен в dashboard, tasks, training
- Артефакты: изменены base.html, dashboard.py, tasks.py, training.py

## 2026-08-07 — Сессия 25: R6 — Object-level auth для вторичных модулей
- security.py: require_entity_owner() — хелпер проверки владельца Entity (owner_id)
- points_v2.py: update_gamification_config + assign_profile_to_entity — проверка владельца
- calendar.py: create_override — проверка владельца template
- Полный аудит всех эндпоинтов: остальные уже фильтруют по user_id
- Тесты 105/105, ruff 0, Docker smoke OK
- Артефакты: изменены security.py, points_v2.py, calendar.py

## 2026-08-07 — Сессия 26: DESIGN.md compliance — дашборд, графики, вёрстка
- DESIGN.md — 600+ строк дизайн-системы (уже существовал, переименован из DESING.md)
- base.html: убраны градиенты, emoji из навигации, animate-fade-in из main
- dashboard_v2.html: полный редизайн — 4 графика, solid индикаторы, SVG иконки, DESIGN.md палитра
- training.html: SVG checkmark, solid progress ring, компактный график
- sessions.html/schedule.html: timeline без градиентов, light mode
- measurements/calendar/points/inventory: light+dark тема, semantic токены
- Убраны дубликаты Chart.js CDN из 4 шаблонов
- 522 insertions, 704 deletions — чистое сокращение кода
- 105 тестов, ruff 0, Docker smoke ok
- Артефакты: изменены 9 шаблонов HTML

## 2026-08-07 — Сессия 27: R0-R6 переаудит — критические исправления
- Внешний аудит выявил оставшиеся P0-дефекты после R0-R6
- CSRF: verify_csrf header-less bypass исправлен (было: if header AND mismatch; стало: if NO header OR mismatch)
- CSRF: подключена как HTTP middleware в main.py (вне lifespan)
- CSRF: пропускает запросы без access_token cookie
- create_all(): полностью удалён из lifespan — Alembic единственный путь
- requirements.lock: 102 пакета, pip freeze
- Миграция 014: subtasks String→JSONB, meta→JSONB, boolean defaults 0/1→false/true
- Object-level auth: get_gamification_config + toggle_opt_in (is_public|owner_id), delete_window (JOIN template.user_id)
- Идемпотентность: training complete_training_task теперь проверяет статус
- XSS: escapeHtml() в base.html, экранирование в inventory/schedule/points/calendar/measurements
- HTMX listener: document.addEventListener('DOMContentLoaded', ...)
- CDN: FIXME-комментарии, план на локальную сборку
- conftest.py: auth_headers включает csrf_token cookie + X-CSRF-Token header
- main.py: очищены неиспользуемые импорты (engine, Base, logger)
- training.py: next_day_suggestion Text→JSON, pipeline хранит dict
- opt_in.py: UniqueConstraint(user_id, entity_id)
- Миграция 013: training_days FK, opt-in unique, active session partial index
- 105/105 тестов с CSRF, ruff 0, format clean, Docker ok
- Артефакты: +2 миграции, +requirements.lock, изменены 12 файлов

## 2026-08-07 — Сессия 28: Cross-user auth тесты + README
- test_cross_user_auth.py: 22 теста межпользовательской авторизации
  - Entity gamification config: чтение/обновление приватных практик → 404
  - Entity opt-in: нельзя подписаться на приватную практику → 404
  - Calendar: удаление чужих окон/шаблонов, создание override на чужом шаблоне → 404
  - Schedule rules: удаление чужих правил → 404
  - Inventory: обновление/удаление чужих предметов → 404
  - Points profiles: удаление чужих профилей → 404
  - Penalty redemptions: завершение чужих отработок → 404
  - Sessions: старт/стоп чужих сессий → 303 (status unchanged)
  - Notifications: отметка чужих уведомлений → 303 (is_read unchanged)
  - LLM configs: удаление чужих конфигов → 404
  - Training: завершение/переключение чужих задач → 404
  - Tasks: complete/interrupt чужих логов → 404
  - Admin: не-админ GET /admin/ → 403, POST /admin/seed-entities → 403
  - CSRF: POST без X-CSRF-Token → 403
- CSRF middleware fix: HTTPException → JSONResponse (try/except в main.py)
  - Раньше HTTPException из verify_csrf пропагировался необработанным
  - Теперь возвращает JSONResponse с кодом 403
- SQLite-совместимость в тестах: time(9,0) вместо "09:00", /admin/ с trailing slash
- README.md: полная документация (описание, структура, установка, архитектура, API, конфигурация, разработка)
- 127/127 тестов, ruff 0, format clean, Docker ok
- Артефакты: +1 тестовый файл, +README.md, изменены main.py, STATUS.md

## 2026-08-07 — Сессия 29: CDN → локальные статические файлы
- 3 CDN-ссылки в base.html заменены на локальные /static/... файлы:
  - `https://cdn.tailwindcss.com` → `/static/tailwindcss.js` (407 KB)
  - `https://unpkg.com/htmx.org@2.0.0` → `/static/htmx.min.js` (49 KB)
  - `https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js` → `/static/chart.umd.min.js` (205 KB)
- Dockerfile уже копирует app/ → static-файлы автоматически в образе
- Нет внешней сетевой зависимости во время работы приложения
- Проверка: curl -sk /static/* → HTTP 200 для всех трёх, главная страница — 0 CDN refs
- 127 тестов, ruff 0, Docker ok
- Артефакты: +3 статических файла в app/static/, изменён base.html

## 2026-08-07 — Сессия 30: Интеграционные тесты + Обновление зависимостей
- test_scheduler.py (8 тестов):
  - _parse_time: 6 параметризованных кейсов (23:00, 00:00, 12:30, 06:05, leading spaces, overflow 25:99)
  - Scheduler lifecycle: start/stop без ошибок, double-start идемпотентен
  - Training day lifecycle: создание через API (не 404), статусы, связь с ActivityLog
  - Multiple training days: несколько дней на одного пользователя
  - Auto-analysis: noop когда нечего анализировать, находит active дни
  - Cross-user isolation: запрос анализа не смешивает пользователей
- test_telegram_bot.py (10 тестов):
  - POST /profile/telegram-link-code → 6-символьный код, сохраняется в БД
  - Expiry: 25-35 минут, SQLite naive datetime
  - GET /profile/telegram-status: linked false/true
  - Bot get_user_by_chat: found/not found (прямой SQL без импорта из bot.py)
  - _require_user логика: linked user найден, unlinked → None
  - Webhook: без секрета → bot not configured
  - send_telegram_notification: False когда бот не настроен
  - Кросс-пользовательская изоляция кода привязки
- requirements.txt + requirements.lock: перегенерированы (102 пакета)
- 153/153 тестов, ruff 0, format clean, Docker ok
- Артефакты: +2 тестовых файла, обновлены requirements.txt + requirements.lock

## 2026-08-08 — Сессия 31: CI GitHub Actions — переработка
- pyproject.toml: добавлен [build-system] (setuptools + wheel) для `pip install .[dev]`
- CI переработан: 3 job'а вместо 2:
  - **lint** — ruff check + format check для app/, cli.py, tests/, seed_prod.py
  - **test** — pytest с SQLite (был PostgreSQL-сервис, но тесты его не использовали)
  - **migrations** — Alembic upgrade → downgrade → upgrade на PostgreSQL 15
- seed_prod.py: ruff fix (unused `pts` → `_pts`)
- 153/153 тестов, ruff 0, format clean
- Артефакты: изменены .github/workflows/ci.yml, pyproject.toml, seed_prod.py

## 2026-08-08 — Сессия 32: CI fix — зелёные job'ы
- CI запущен, lint ✅, но test ❌ и migrations ❌
- **test**: 3 теста repair падали — `json_repair` на Python 3.11 успешно «чинил» plain text в JSON-строку, тесты ожидали исключение
- **migrations**: downgrade 014 — `SET DEFAULT 0` на boolean колонке, PostgreSQL требовал `false`
- Исправления:
  - `app/llm/repair.py`: добавлена проверка типа результата (dict/list) после каждой стратегии repair
  - `alembic/versions/014`: boolean defaults `0`→`false`, `1`→`true` в downgrade
- Все 3 job'а зелёные: lint ✅ test ✅ migrations ✅
- Артефакты: изменены app/llm/repair.py, alembic/versions/014_fix_migration_types.py

## 2026-08-09 — Сессия 33: Обновление статических файлов
- HTMX: 2.0.0 → 2.0.10 (51KB, +2KB) — bugfix release
- Chart.js: 4.4.0 → 4.5.1 (209KB, -27KB) — минорное обновление
- TailwindCSS: v3 → v4.3.3 (282KB, -125KB) — мажорная версия (@tailwindcss/browser@4)
  - Убран `tailwind.config = { darkMode: 'class' }` — v4 использует `class`-стратегию по умолчанию
  - Шаблоны совместимы: нет deprecated opacity-утилит, @apply, @layer
  - CSS-first конфигурация (@theme) не требуется для текущего использования
- 153/153 тестов, ruff 0
- Артефакты: обновлены 3 статических файла в app/static/, изменён base.html

## 2026-08-09 — Сессия 34: Подготовка релиза 0.8.0 + Docker smoke-test + README
- Версия: 0.7.0 → 0.8.0 (pyproject.toml + main.py)
- `.env.example`: добавлены CREDENTIALS_ENCRYPTION_KEY, TG_BOT_TOKEN, TG_WEBHOOK_SECRET, TG_WEBHOOK_BASE_URL, TG_BOT_USERNAME, TG_POLLING, TG_AUTO_ANALYSIS_TIME
- `docker-compose.yml`: добавлены все недостающие env vars, nginx — опциональный профиль `full`, app порт 8000 проброшен на хост, depends_on заменён на pg_isready wait-loop, postgresql-client добавлен в Dockerfile
- `seed_prod.py`: argparse (--email, --database-url), читает DATABASE_URL из env
- `docker-compose.override.yml`: dev-окружение (SQLite, hot-reload, polling Telegram, без postgres/nginx)
- **Docker smoke-test**: db + app подняты, все эндпоинты проверены:
  - `/healthz` → 200 "ok"
  - `/static/htmx.min.js` → 200, 51KB
  - `/static/chart.umd.min.js` → 200, 209KB
  - `/static/tailwindcss.js` → 200, 282KB
  - `/` → 200, 7.6KB HTML
- **README**: секция Deployment — хост-nginx + certbot + docker compose, бэкапы pg_dump, seed
- 153/153 тестов, ruff 0, format clean
- Артефакты: +1 docker-compose.override.yml, изменены 8 файлов

## 2026-08-09 — Сессия 35: Деплой на VPS + Seed тренировки
- Остановлен старый nginx-контейнер, запущены db + app (port 8000 → host)
- Host nginx: конфиг для tracker.gorbunovr.ru создан в `/tmp/practice-loop-nginx.conf` (ждёт sudo reload)
- Training day: создан в БД с полным расписанием гидратации (воскресенье, 24ч график, микро-сливы, ночной блок)
- Обнаружен пробел: нет inline-полей для ввода реальных данных (объёмы, временные интервалы, секунды микро-сливов)
  - ActivityLog.subtasks — только чекбоксы (is_done), нет value-полей
  - ActivityLog.selected_params — только LLM-параметры, не для ручного ввода
  - ActivityLog.planned_value/actual_value — строковые поля, не используются в training UI
  - BodyMeasurement — только физические замеры (вес, обхваты)
- 153/153 тестов, CI зелёный
- Артефакты: +1 скрипт seed_training.py, конфиг nginx

## 2026-08-09 — Сессия 40: Deferred-фиксы (P0 production gate, bif, JS i18n) — В ПРОЦЕССЕ

Цель: закрыть оставшиеся deferred пункты из Сессій 37 + 39.

### Этап 2 ✅ — AGENTS.md bif-комментарий
Добавлена секция 0 «Архитектурный bif v0.8-actual ↔ v0.7-spec» в AGENTS.md: явная таблица 6 пунктов расхождения + ссылки на ADR-029, ADR-031, ADR-032, ADR-033, ADR-034. Зафиксировано требование «при работе следуй коду; при пересмотре — отмена ADR явно».

### Этап 3 ✅ — Production gate в config.py
`app/config.py`: добавлен `app_env` + `@model_validator`, который в production отвергает `change-me-...` placeholder-ы и секреты длиной <32. TG_WEBHOOK_SECRET проверяется только если установлен TG_BOT_TOKEN.

`docker-compose.yml`: `APP_ENV: ${APP_ENV:-production}` — то есть по умолчанию в compose-сборке включён gate.

`docker-compose.override.yml`: принудительно `APP_ENV: development` для dev-окружения.

Новый файл `tests/test_config.py`: 11 тестов:
- `TestAppEnv`: default development, нормализация регистра/пробелов
- `TestProductionGate`: dev принимает placeholders, production отклоняет JWT/ENCRYPTION/TG_WEBHOOK, length ≥32 enforced, error message перечисляет все нарушители

Все 11 проходят ✅.

### Этап 4 ✅ — store_raw_response flag (REM §7.5)
- `alembic/versions/016_add_store_raw_response.py`: миграция добавила поле `llm_provider_configs.store_raw_response BOOLEAN DEFAULT TRUE` + `activity_logs.raw_response_expires_at TIMESTAMPTZ NULL` + индекс на expires_at.
- `app/models/llm_config.py`: добавлено поле `store_raw_response` (default True, как ADR-034 сохраняет backwards-compat).
- `app/models/activity_log.py`: добавлено поле `raw_response_expires_at` (nullable, indexed).
- `app/llm/pipeline.py`: helper `_resolve_raw_response(config, raw)` возвращает `(raw, expires)` в зависимости от `store_raw_response` + TTL 30 дней (константа `RAW_RESPONSE_TTL_DAYS`). Применён во все 3 точки сохранения ActivityLog.
- `app/schemas/llm_config.py`: добавлен `store_raw_response: bool = Field(default=True)` в `LLMConfigCreate` / `LLMConfigUpdate` / `LLMConfigResponse`.
- `app/api/llm_configs.py`: form принимает `store_raw_response` (true/false/on/1/yes parsing).
- `app/templates/llm_configs.html`: показывает LLM mode и store_raw_response; 🤖 emoji заменён на SVG.
- Новый файл `tests/test_llm_raw_response_policy.py`: 5 тестов (сохраняем с TTL, дроп при отключении, дроп при отсутствии атрибута, дроп для empty raw, sanity TTL в [7,90] дней).
- Все 5 тестов ✅.

### Этап 5 ✅ — Расширение LLM validator (REM §7.4)
- `app/llm/validator.py`: новая функция `validate_params_against_schema(params, schema)` — рекусивно проверяет:
   - тип (`number` / `integer` / `string` / `boolean`);
   - диапазоны min/max для number+integer;
   - длины min_length/max_length для строк;
   - `enum` для строк (whitelist значений);
   - `optional` для всех ключей (default false);
   - `PARAMS_NOT_DICT` для неправильных типов контейнера;
   - `UNKNOWN_PARAM_TYPE` для опечаток в schema.
- В `app/llm/pipeline.py` после `validate_llm_response` (top-level) вызывается `validate_params_against_schema`, используя `params_schema` из `context[allowed_entities]`.
- Новый файл `tests/test_llm_validator.py`: 32 теста (4 на top-level + 28 параметризованных на schema validation).
- Все 32 ✅.

### Этап 6 ✅ — dashboard_v2 refactor (DESIGN §11 ≤2 графика)
- `app/templates/dashboard_v2.html` (368→ранее): теперь 4 графика → 2 канваса (Weekly Activity + Points Trend) + 2 compact summary cards (categories + completion).
- Ровно 2 chart-elements per viewport согласно DESIGN.md §11.
- Completion Rate сжат в одну карточку: «big number + цвет» + пару строк completed/total.
- Categories сжаты в top-3 bar list с %.
- Все capture-JS используют переводы через `t.*` + escapeHtml в JS (mini-SSR escape).
- `app/i18n/en.py` + `app/i18n/ru.py`: +37 ключей (nav_training/tasks/sessions/import/calendar/points/inventory/notifications/achievements, dashboard_points/xp/streak/days_suffix/done/level_label/active_session/loading/link/no_categories/browse_catalog/others/completion_completed/total/see_history/chart_weekly/chart_points_trend/chart_categories_title/chart_completion_title/chart_last_7/chart_last_30/chart_done/chart_stop/chart_pending/telegram_connected/code_ready/not_linked/link/code_valid/code_hint/new_code/open_bot, notifications_title, achievements_title).
- Шаблон рендерится (28 KB), синтаксис в порядке.

### Этапы 7+8 ✅ — calendar.html & inventory.html JS async i18n
- `app/templates/calendar.html`: заменены все hardcoded EN тексты → `{{ t.calendar_* }}` ключи (today's legend, header titles, intensity select, day-of-week selector, policy selector); JS использует инжектированный `I18N` dict + `POLICY_LABEL` map; все user-controlled values проходят через `escapeHtml()`; новый `calendar_btn_delete` = «Удалить»/«Delete».
- `app/templates/inventory.html`: аналогично — All/Clothing/Equipment/Cosmetics/Shopping List → `t.inventory_filter_*`; status badges используют `STATUS_LABEL` map; placeholder'ы, кнопки и labels → i18n; новый блок `inv_*` ключей с RU переводами; `STATUS_LABEL` + `I18N` инжектируются Jinja из статических переводов (безопасны).
- Добавлены ключи в en.py + ru.py: `inventory_filter_shopping_list`, `inv_btn_add`, `inv_btn_add_new_item`, `inv_btn_save`, `inv_btn_delete`, `inv_ph_category/name/qty/qty_needed/priority`, `inv_shopping_list`, `inv_chart_breakdown`, `inv_qty_label`, `inv_priority_label`, `inv_empty`, `inv_mark_shopping`, `inv_items_counter_suffix`, `inv_status_need/ordered/bought/built/other`. 31 ключ.
- Шаблоны рендерятся (calendar 20 KB, inventory 19 KB), синтаксис OK.

### Этап 9 ✅ — import_data.html: localhost:8443 → config + i18n + emoji removal
- `app/api/import_data.py`: добавлен `app_url` в контекст шаблона — `str(request.url_root).rstrip("/")`.Проиходит из `request`, deployments не привязаны к localhost.
- `app/templates/import_data.html`:
     - hardcoded `https://localhost:8443` заменены на `{{ app_url }}` в clipboard-button и в curl-примере;
     - hardcoded EN/RU тексты → `t.import_*` ключи (`import_title`, `import_subtitle`, `import_data_types`, `import_section_templates`, `import_section_upload`, `import_section_export`, `import_drop_hint`, `import_or`, `import_file_label`, `import_autodetect_hint`, `import_submit`, `import_full_backup`, `import_download_all`, `import_api_title`, `import_api_desc`, `import_api_example_title`, `import_api_types_line`).
     - Все эмодзи 📦📥📤📁🚀🔄⬇️🔌 заменены на SVG-иконки (DESIGN.md 6.3).
     - Градиент `from-indigo-50 to-purple-50` → solid `bg-indigo-50`.
     - aria-live на upload-result, aria-label на copy-URL, type="button" на всех кнопках (CSRF-safe).
- 17 новых ключей в en.py + ru.py.
- Шаблон рендерится (16 KB), синтаксис OK.

### Этап 10 ✅ — XSS-fixture тесты (REM §A14)
- Новый файл `tests/test_xss_fixtures.py`: 24 XSS-защитных теста в 4 фазах:
   1. **Jinja autoescape**: подтверждена, что `{{payload}}` в HTML-аттрибуте/content рендерит контент безопасно;
   2. **escapeHtml** (mirror base.html): 8 параметризованных тестов на OWASP payloads (script tag, img onerror, mouseover, javascript URI, unicode, None, int, двойное экранирование);
   3. **end-to-end**: `calendar.html` / `inventory.html` рендер враждебного ввода через Jinja autoescape — `<script>` всегда заменяется на `&lt;script&gt;`;
   4. **регрессия**: 10 известных payload-ов из OWASP cheat sheet (svg/onload, iframe/src, body/onload, input/autofocus, ERB/Jinja/JS-инъекции).
- Все 24 ✅.

### Этап 11 ✅ — финальная валидация
- `ruff check app/ cli.py tests/ seed_prod.py` → All checks passed! ✅
- `ruff format --check app/ cli.py tests/ seed_prod.py` → 86 files already formatted ✅ (после autoformat)
- `python3 -m pytest tests/` → **225 passed in 38.49s** ✅ (было 153 → +72 новых: 11+5+32+24)
- Все P0/P1 из предыдущих сессий закрыты.

## 2026-08-09 — Сессия 39: Frontend-фиксы (P0/P1 из аудита)

- Выполнены все рекомендации из FRONTEND_AUDIT_SESSION_38.md
- **P0-баг**: catalog.html — enum `unacceptable → strong_aversion` (миграция ADR-029 не покрыла UI-слой)
- i18n: добавлено ~50 новых ключей в en.py + ru.py; удалён 1 дубль `catalog_no_entities_hint`
- training.html: 8 RU строк → t.* + CSRF + aria-label
- Градиент в index.html удалён; SVG иконки вместо эмодзи
- Эмодзи удалены из заголовков: admin, llm_configs, catalog, notifications, privacy, my_entities, tasks, dashboard
- Hover-translate и shadow-lift убраны с 16+ карточек
- base.html: CSS variables (light/dark), skip-link, ARIA, focus ring, motion easing (`cubic-bezier`), 44px touch target, `aria-live`, `aria-current="page"`
- Градиент в achievements.html → solid
- **Результат**: 153/153 теста ✅, ruff ✅, format ✅
- Детальный отчёт: `memory/FIX_SESSION_39.md`
- Артефакты: +~200 строк в i18n, изменены 15 шаблонов

## 2026-08-09 — Сессия 38: Frontend-аудит (по запросу владельца)

- Прочитан DESIGN.md (694 строки) — приоритетный документ для frontend.
- Прочитаны все 22 шаблона (2914 строк).
- Проверки: `grep 'innerHTML'` 18 вхождений / 8 файлов; `grep 'aria-|role='` 0; `grep 'bg-slate|bg-gray'` 465 строк; `grep 'hover:-translate|hover:shadow-lg'` 21 нарушение DESIGN.md 6.3; `grep 'csrf_token'` 4 формы из ~25.
- Ключевая находка: `app/templates/catalog.html` всё ещё использует enum `unacceptable` после миграции на `strong_aversion` (ADR-029). Это **P0-баг**: CSS ветка в строке 74 не сработает + нет option для нового значения.
- Найдены hardcoded RU/EN строки вне `t.*` словаря в training.html (8 строк RU), dashboard.html, index.html, catalog.html, calendar.html.
- 0 ARIA атрибутов во всех 22 шаблонах (нет aria-label, aria-current, aria-live, skip-link).
- DESIGN.md compliance ≈30%.
- Результат: `memory/FRONTEND_AUDIT_SESSION_38.md` (полный отчёт), SESSIONS/STATUS/OPEN_QUESTIONS обновлены.
- Код НЕ изменён. Изменения отложены в Сессию 39.

## 2026-08-09 — Сессия 37: Аудит проекта (по запросу владельца)

- Прочитаны все priority-документы: REMEDIATION_SPEC.md (676), AGENTS.md (219), DESIGN.md (694), tracker-spec.md (409), README.md (304), все 7 memory/* файлов.
- Снят срез кода: main.py, security.py, entity.py, api/tasks.py, llm/pipeline.py, llm/validator.py, services/scheduler.py, config.py, alembic/versions/* (15 миграций), .github/workflows/ci.yml, docker-compose.yml.
- Проверки: `rg create_all|metadata.create` — пусто; `rg innerHTML` — 18 совпадений в 8 файлах; `rg eval(` — только htmx; `python3 -m pytest --collect-only` — 153 теста.
- Бриф-интервью: владелец выбрал bif (REMEDIATION_SPEC.md остаётся целевой, ADR-029–034 — зафиксированный компромисс v0.8-actual) и «эта сессия — только аудит».
- Результат: `memory/AUDIT_SESSION_37.md` (полный отчёт), SESSIONS.md, STATUS.md, OPEN_QUESTIONS.md (Q7) обновлены.
- Код НЕ изменён. Изменения AGENTS.md/конфига отложены в Сессию 38.
- Артефакты: +1 memory-файл, изменены SESSIONS/STATUS/OPEN_QUESTIONS.

## 2026-08-09 — Сессия 36: TrainingLogEntry — журнал тренировки
- **Модель** `app/models/training_log.py`: TrainingLogEntry (time_label, entry_type, planned/actual_value, unit, notes, sort_order, is_extra)
- **Миграция** 015: таблица `training_log_entries`
- **API** (3 эндпоинта):
  - `POST /training/log-entry/{id}` — обновление actual_value + notes (inline HTMX)
  - `POST /training/log-entry` — добавление внеплановой записи (is_extra=True)
  - `DELETE /training/log-entry/{id}` — удаление внеплановой записи
- **UI**: training.html — inline-формы для каждой строки журнала (факт + заметки), кнопка «+ Добавить запись» с выбором типа (приём/микро-слив/давление/заметка)
- **Seed**: 27 записей по расписанию гидратации (fluid_intake, micro_leak, general_note)
- 153/153 тестов, ruff 0
- Артефакты: +3 файла (модель, миграция, seed_training.py), изменены training.py + training.html
