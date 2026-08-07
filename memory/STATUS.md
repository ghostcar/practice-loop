# Текущий статус

Обновляется **в конце каждой сессии**. Последнее обновление: 2026-08-07 (сессия 25).

## Обзор фаз
| Область | Статус |
| --- | --- |
| Проектирование (AGENTS.md, tracker-spec.md, memory) | ✅ Завершено |
| Phase 1 — Фундамент и инфраструктура | ✅ Завершена |
| Phase 2 — Каталог и конфиги | ✅ Завершена |
| Phase 3 — LLM-пайплайн | ✅ Завершена |
| Phase 4 — UI, сессии, геймификация, уведомления | ✅ Завершена |
| Phase 5 — Training (тренировки) | ✅ Завершена |
| Phase 6 — Points v2, Measurements, Inventory, Schedule | ✅ Завершена |
| Phase 7 — Import/Export + Charts + Layout | ✅ Завершена |
| Phase 8 — Calendar (календарь доступности) | ✅ Завершена |
| Phase 9 — Penalty & Points v2 (штрафы и баллы) | ✅ Завершена |
| Phase 10 — Telegram Bot v2 (реальный бот) | ✅ Завершена |
| Phase 11 — Auto-Analysis Scheduler | ✅ Завершена |
| v0.7 Audit & Interview (R0) | ✅ Завершён |
| R1 — Воспроизводимость | ✅ Завершён |
| R2 — Безопасность и транзакции | ✅ Завершён |
| R3 — Каталог, модерация, scheduler | ✅ Завершён |
| R4 — LLM planner | ✅ Завершён |
| R5 — Frontend shell | ✅ Завершён |
| R6 — Возврат вторичных модулей | ✅ Завершён |

## R6 — Возврат вторичных модулей (object-level auth)
- [x] security.py: require_entity_owner() — отдельный хелпер для Entity (owner_id ≠ user_id)
- [x] points_v2.py: update_gamification_config + assign_profile_to_entity проверяют владельца entity
- [x] calendar.py: create_override проверяет владельца template
- [x] Аудит всех остальных эндпоинтов: уже используют user_id-фильтрацию (безопасны)

## Что сделано (Phase 9 — Penalty & Points v2)
- [x] PenaltyRedemption модель + миграция 008: отслеживание отработок штрафов (pending/completed/skipped)
- [x] Redemption API: `GET /api/v2/points/redemptions`, `POST .../complete` (возврат баллов), `POST .../skip`
- [x] Handler: авто-создание PenaltyRedemption при прерывании задачи
- [x] PointsProfile: полный CRUD (`POST`/`GET`/`DELETE`), назначение профиля на сущность
- [x] Threshold effects: авто-уведомления при пересечении negative/warning/good порогов
- [x] Gamification editor: `PUT /entities/{id}/gamification` — обновление конфига баллов/штрафов
- [x] Points page: список pending отработок (✅ Complete / ⏭ Skip), профили баллов, назначение на сущность
- [x] Тесты: 105/105

## Что сделано (Phase 10 — Telegram Bot v2)
- [x] 8 команд с реальной логикой: /start, /link, /next→LLM, /tasks, /done→gamification, /interrupt→penalty, /stats→DB, /session→DB, /settings→locale
- [x] Inline-клавиатуры: ✅ Done / ⏹ Interrupt на каждой задаче, подтверждение прерывания
- [x] User.telegram_chat_id, telegram_link_code, telegram_link_code_expires (миграция 009)
- [x] Привязка: 6-значный код (30 мин), /link CODE, /profile/telegram-link-code, /profile/telegram-status
- [x] Уведомления: send_telegram_notification(), хук _send_tg_notifications в gamification handler
- [x] Webhook: авто-регистрация при старте (setup_webhook в lifespan)
- [x] Дашборд: карточка «Link Telegram» с генерацией кода, статусом, кнопкой
- [x] config: tg_bot_username, tg_webhook_base_url
- [x] Polling-режим: tg_polling=true → start_polling() (фоновая asyncio task), stop_polling() при shutdown
- [x] Тесты: 105/105

## Что сделано (Phase 11 — Auto-Analysis Scheduler)
- [x] app/training/scheduler.py — фоновая asyncio задача, без внешних зависимостей
- [x] Ежедневный запуск в tg_auto_analysis_time (по умолчанию 23:00 UTC)
- [x] Сканирует всех пользователей: ищет TrainingDay со статусом active/planned
- [x] Вызывает analyze_training_day (анализ дня + генерация плана на завтра)
- [x] Запуск/остановка в lifespan вместе с Telegram
- [x] Тесты: 105/105

## Что сделано (Phase 7 — Import/Export + Charts + Layout)
- [x] Import/export модуль: 8 типов шаблонов (measurements, inventory, entities, schedule, points_transactions, training_days, activity_logs, points_profiles)
- [x] CSV/JSON upload с авто-определением типа по заголовкам
- [x] API-push для внешних сервисов (`POST /import/api`)
- [x] Full backup: `GET /import/export/full` — все данные пользователя одним JSON
- [x] Per-type export: `GET /import/export/{type}?format=csv|json`
- [x] CLI-утилита: `python cli.py import/export/template`
- [x] Веб-страница `/import` с шаблонами, загрузкой, экспортом, API-документацией
- [x] 2 новых chart API: `/api/v2/charts/category-breakdown` + `/api/v2/charts/completion-rate`
- [x] Dashboard v2: 4 графика (points trend, category donut, completion gauge, XP sparkline)
- [x] Training page: weekly completion rate chart
- [x] Sessions page: 14-day activity timeline + duration bars
- [x] Achievements: улучшенные прогресс-бары + 3 счётчика
- [x] Все страницы: компактный layout (chart heights h-72→h-40, py-8→py-4, text-3xl→text-2xl)
- [x] python-dotenv в requirements.txt

## Что сделано (Phase 8 — Calendar)
- [x] 3 модели: CalendarTemplate (шаблон недели), AvailabilityWindow (окно с политикой allowed/disallowed/passive_only), CalendarOverride (отпуск/каникулы на диапазон дат)
- [x] Entity.intensity (active/passive/neutral) — пассивные активности обходят ограничения
- [x] Миграция 007 (calendar_templates, availability_windows, calendar_overrides + entity.intensity)
- [x] API: CRUD templates/windows/overrides + `GET /calendar/check` (проверка доступности)
- [x] `is_available()` — утилита проверки (time + duration + intensity → bool)
- [x] `get_day_schedule()` — получение расписания на день (для LLM и UI)
- [x] LLM-интеграция: календарь в `context_builder` → инжектится в промпт
- [x] Веб-страница `/calendar` с timeline-баром на сегодня, конструктором шаблонов, управлением отпусками
- [x] Интеграция в `/tasks`: индикатор доступности + today's schedule
- [x] Schedule page: weekly timeline chart (горизонтальные бары по дням недели)
- [x] Отпуск = CalendarOverride с шаблоном «Vacation» на диапазон дат

## v0.7 Audit & Interview (R0)
- [x] Внешний аудит: REMEDIATION_SPEC.md прочитан, 18 дефектов зафиксированы
- [x] Интервью по 6 ключевым архитектурным решениям (ADR-029–034)
- [x] AGENTS.md обновлён: приоритет документов, LLM-режимы, актуальные фазы
- [x] AGENTS_.md удалён (заменён на AGENTS.md)
- [x] DECISIONS.md: +6 ADR
- [x] CONTEXT.md: убрано «код не написан», отражён статус
- [x] DESIGN.md — ожидает создания

## R1 — Воспроизводимость
- [x] pyproject.toml — единый источник зависимостей
- [x] requirements.txt — сгенерирован из pyproject.toml
- [x] bcrypt закреплён <4.1 (совместимость с passlib)
- [x] python-dotenv добавлен в pyproject.toml
- [x] Версия 0.7.0 в pyproject.toml и main.py
- [x] create_all с предупреждением (Alembic для production)
- [x] CI: ruff lint + pytest на PostgreSQL 15 (.github/workflows/ci.yml)
- [x] Миграция 012: subtasks String→JSON, next_day_suggestion Text→JSONB исправлены

## R2 — Безопасность
- [x] app/security.py: CSRF (double-submit cookie), OwnershipChecker, complete_once/interrupt_once
- [x] login/logout: CSRF cookie + очистка, access_token path=/
- [x] base.html: CSRF meta tag, HTMX auto-include X-CSRF-Token, scripts block
- [x] tasks: идемпотентный complete/interrupt (защита от двойной награды)
- [x] encryption: ключ от CREDENTIALS_ENCRYPTION_KEY (отделён от JWT_SECRET)
- [x] config: credentials_encryption_key
- [x] dashboard/home: csrf_token в шаблонах
- [ ] Object-level auth: OwnershipChecker создан, но нужно применить во всех эндпоинтах

## R3 — Каталог, модерация, scheduler
- [x] User.role (user/moderator/admin) + миграция 010
- [x] require_admin() dependency — /admin защищён
- [x] OwnershipChecker применён в tasks, training, sessions, achievements, notifications
- [x] unacceptable → strong_aversion (модель, схемы, pipeline, тесты)
- [x] Soft scheduler: get_due_practices(), set_next_due(), set_retry_block()
- [x] UserEntityOptIn.next_due_at + retry_not_before_at (миграция 011)
- [x] Tasks page: due practices + авто-установка сроков после complete/interrupt

## R4 — LLM planner
- [x] LLMProviderConfig.llm_mode (full/abstract) + миграция 012
- [x] context_builder: format_context_abstract() — opaque IDs
- [x] app/llm/validator.py — проверка entity_id в allowed set
- [x] Pipeline: валидатор ответа, выбор формата по llm_mode
- [x] Deterministic fallback: /tasks/generate-deterministic
- [x] tasks.html: due practices + кнопка «Pick from due (no LLM)»
- [x] Миграция 012: subtasks + next_day_suggestion типы исправлены

## В работе
- Ничего. R0–R4 завершены.

## R5 — Frontend shell
- [x] active_nav: подсветка активной страницы в навигации
- [x] Навигация упрощена: dashboard, tasks, training, catalog, points, admin
- [x] CSRF hidden поля в формах locale/theme
- [x] innerHTML аудит: всё использование — серверные данные (безопасно)
- [x] scripts блок в base.html

## В работе
- Ничего. R0–R6 завершены.

## Следующие шаги
1. Push на GitHub (`git push --force -u origin main`)
2. Деплой на VPS, SSL, бэкапы
3. R6 — Возврат вторичных модулей (DESIGN.md compliance)
