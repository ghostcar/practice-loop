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
