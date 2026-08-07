# Текущий статус

Обновляется **в конце каждой сессии**. Последнее обновление: 2026-08-07 (сессия 12).

## Обзор фаз
| Область | Статус |
| --- | --- |
| Проектирование (AGENTS.md, tracker-spec.md, memory) | ✅ Завершено |
| Phase 1 — Фундамент и инфраструктура | ✅ Завершена |
| Phase 2 — Каталог и конфиги | ✅ Завершена |
| Phase 3 — LLM-пайплайн | ✅ Завершена |
| Phase 4 — UI, сессии, геймификация, уведомления | ✅ Завершена |

## Что сделано
- [x] Интервью с пользователем (5 раундов): скоуп, пользователи, языки, деплой, LLM/маскирование,
      провайдеры, ошибки LLM, штрафы, тесты, UI, админка, приватность, геймификация, каталог,
      уведомления, переработка AGENTS.md, подписки, сессии, бэкапы, логи LLM.
- [x] Открытые вопросы решены: aiogram 3.x; Omniroute+Groq+OpenRouter; без рейт-лимитов;
      простая регистрация; кастомные правила геймификации; контент по locale.
- [x] Детали Telegram-бота: 6 команд, 5 типов уведомлений, код-привязка, интервальные
      напоминания (старт 2 ч), список активных задач, компактная карточка, настройка получателей.
- [x] Сессии/штрафы, каталог задач (вкл. стартовый набор 30+, черновик), доска достижений —
      зафиксированы в спеке (разделы 9–11).
- [x] `AGENTS.md` переработан в единый стиль (8 разделов, без Semantic Masking).
- [x] `tracker-spec.md` создан и дополнен (17 разделов).
- [x] Создана система памяти `memory/*` + правила обязательного использования.

## Что сделано (Phase 1)
- [x] Структура проекта: `pyproject.toml`, `requirements.txt`, `.gitignore`, `.env.example`
- [x] Docker: `Dockerfile` (multi-stage, python:3.11-slim), `docker-compose.yml` (db+app+nginx),
      `nginx/nginx.conf`
- [x] FastAPI-скелет: `app/main.py`, `app/config.py`, `app/database.py`
- [x] Health check: `GET /healthz` → `ok`
- [x] User-модель (SQLAlchemy async): id (UUID), email, password_hash, subscription_tier,
      locale, theme, created_at
- [x] Alembic: `alembic.ini`, `env.py` (async), `001_create_users` миграция
- [x] JWT-аутентификация: `app/auth.py` (hash/verify, create/decode JWT, cookie-based)
- [x] Регистрация/логин: `POST /auth/register`, `POST /auth/login`, `GET /auth/logout`
- [x] i18n: EN/RU, переключатель языка в UI, сохранение в профиле
- [x] Тёмная/светлая тема: переключатель в UI, TailwindCSS dark mode, сохранение в профиле
- [x] Jinja2-шаблоны: base (navbar+flash+footer), index (лендинг), register, login, dashboard
- [x] Базовые тесты: `tests/conftest.py`, `tests/test_healthz.py`

## Что сделано (Phase 2)
- [x] Модели: Entity (тип/категория/теги/params_schema/авторство), UserEntityOptIn (допуск/рейтинг/желание),
      LLMProviderConfig (BYOK: url/ключ/модель/usage)
- [x] Alembic-миграция 002 (entities, llm_provider_configs, user_entity_opt_ins)
- [x] Шифрование API-ключей: Fernet (cryptography), ключ из JWT-секрета
- [x] CRUD Entity: создание (свои), публикация (is_public+авторство), удаление
- [x] Opt-in API: переключение допуска, рейтинг 1–5, шкала желания (want_very_much…unacceptable)
- [x] CRUD LLMProviderConfig: добавление, активация (деактивация остальных), удаление
- [x] Seed-данные: 30+ задач (6 категорий × 5) + 3 LLM-пресета (Omniroute/Groq/OpenRouter)
- [x] Админ-панель: каталог (фильтр по категориям), мои задачи, LLM-конфиги, кнопки seed
- [x] Шаблоны: catalog.html, my_entities.html, llm_configs.html, admin.html
- [x] Баги исправлены: format→%s, tags→list, updated_at onupdate, desire_level-лейблы

## Что сделано (Phase 3)
- [x] Модели: ActivitySession (created/active/ended, правила, участники),
      ActivityLog (raw_llm_response полностью, usage: prompt/completion/total tokens + cost)
- [x] Alembic-миграция 003 (activity_sessions, activity_logs)
- [x] Context Builder: история (10), статистика, допустимые entity (opt-in + desire),
      активные штрафы, locale, форматтер для промпта
- [x] LLM-клиент: AsyncOpenAI, конфиг из LLMProviderConfig, BYOK,
      оценка стоимости по модели (heuristics)
- [x] JSON repair: json_repair → regex-извлечение → 3 попытки (fresh LLM response) → JsonRepairError
- [x] Tool calling: save_activity_log, get_user_stats, apply_penalty (OpenAI-формат)
- [x] Endpoint POST /tasks/generate: контекст → LLM → repair → parse → save в ActivityLog,
      обновление usage в LLMProviderConfig, locale в промпте
- [x] Endpoints: POST /tasks/{id}/complete, POST /tasks/{id}/interrupt
- [x] UI: страница /tasks/ (форма генерации, история с ✅/⏹, стоимость токенов)
- [x] Исправлено: dead code, is_last_attempt, penalties считает все interruptions

## Что сделано (Phase 5 — Training)
- [x] Модель TrainingDay: id, user_id, target_date, status (planned/active/completed/analyzed),
      plan_summary, analysis_summary, next_day_suggestion (JSON string)
- [x] ActivityLog: добавлены поля training_day_id (FK) и subtasks (JSON чек-лист)
- [x] Alembic-миграция 005 (training_days + FK + subtasks)
- [x] LLM-промпты: PLAN_DAY_SYSTEM, ANALYZE_DAY_SYSTEM, SUGGEST_NEXT_DAY_SYSTEM
- [x] LLM pipeline: generate_daily_plan (создаёт TrainingDay + ActivityLog с чек-листами),
      analyze_training_day (анализ дня + предложение плана на завтра)
- [x] Геймификация: режим тренировки — XP начисляется, но streaks/комбо/ачивки пропускаются
- [x] API: GET /training (страница), POST /training/plan (генерация),
      POST /training/tasks/{id}/subtasks/{idx}/toggle (чек-лист),
      POST /training/tasks/{id}/complete (завершение),
      POST /training/analyze (анализ дня)
- [x] Шаблон training.html: карточки задач с чек-листами, прогресс-бар, кнопки Complete/Analyze
- [x] i18n: 14 ключей EN/RU для тренировки
- [x] Тесты: 5 тестов (модель TrainingDay, жизненный цикл, ActivityLog с training,
      toggle subtask, gamification training mode)

## Что сделано (Phase 4)
- [x] Модели: UserProgress (XP/уровень/streak/комбо), Achievement (13 seed),
      UserAchievement (контекст/скрытие), Notification (5 типов)
- [x] Alembic-миграция 004 (user_progress, achievements, user_achievements, notifications)
- [x] XP-движок: база (25/50/15), streak (+5/день), комбо (+10%→+50%), интенсивность (+10%/уровень)
- [x] Пороги уровней: 100/250/500/1000/1750/2750/4000/5500/7500/10000…
- [x] Достижения: 13 типов (streak 3/7/30, count 10/50/100, diversity 3/5, joint 1/10, intensity 5, level 5/10)
- [x] Handler: on_task_completed (XP/streak/комбо/уровни/ачивки/уведомления),
      on_task_interrupted (штраф×эскалация/сброс комбо/уведомление)
- [x] Дашборд v2: реальные XP/уровень/streak, прогресс-бар, история, быстрые ссылки
- [x] Доска достижений: лента всех (анонимно) + «мои» + скрытие отдельных
- [x] In-app уведомления: список (unread подсветка), mark read
- [x] Сессии: create/start/end, список со статусами
- [x] Приватность: JSON-экспорт (профиль/прогресс/200 активностей/ачивки),
      удаление аккаунта (CASCADE)
- [x] Telegram-бот: aiogram 3.x, вебхук /tg/webhook, 6 команд (/start/link/next/done/interrupt/stats/session/settings)
- [x] Баги исправлены: streak только 1/день, raw_llm_response в экспорте, inline import → top-level
- [x] **Тесты: 100 тестов (9 test files), 0 ruff errors.** Покрытие: auth, entities CRUD, LLM configs CRUD,
      JSON repair (13 cases), XP engine (27 cases), context builder (3 cases),
      gamification handler (7 cases), sessions CRUD (4 cases).
- [x] Модели: JSONB → JSON для совместимости с SQLite (тесты).
- [x] pyproject.toml: исправлен license, добавлен setuptools.packages.find, ruff ignore B008.

## Что сделано (Phase 6 — Points v2, Measurements, Inventory, Schedule, Import)
- [x] Модели: Entity (+parent_id, +level, +gamification_config JSON), ActivityLog (+planned_value, +actual_value, +points_awarded), UserProgress (+points_balance)
- [x] Новые модели: PointsTransaction, PointsProfile, ScheduleRule, BodyMeasurement, InventoryItem
- [x] Alembic-миграция 006 (5 новых таблиц + 7 изменений существующих)
- [x] Pydantic-схемы: GamificationConfig (PointsConfig, PenaltyConfig с уровнями и redemption, BonusCondition, ThresholdConfig), схемы для всех новых моделей, ImportPayload
- [x] Points v2 engine: calculate_entity_points (base + intensity + bonuses с eval условий), calculate_entity_penalty (с эскалацией), get_redemption_action
- [x] Обновлён gamification/handler: on_task_completed читает Entity.gamification_config, начисляет points + XP; on_task_interrupted применяет points-штрафы + записывает redemption-действия
- [x] API `/api/v2/*`: gamification config CRUD, points balance/spend, points profiles, schedule rules CRUD, measurements CRUD + charts, inventory CRUD + shopping list
- [x] API `/import/*`: шаблоны CSV/JSON для 4 типов данных, upload (CSV/JSON), API-push для внешних сервисов
- [x] Шаблоны: measurements.html (Chart.js графики), inventory.html (фильтры + CRUD), schedule.html (слоты дня), points.html (баланс + пороги + история)
- [x] Seed v2: 15 entities с gamification_config (ЗД/КП/Прищепки/Бондаж/Упаковка + 10 спортивных), 8 замеров тела, 30+ items инвентаря, 11 правил расписания дня
- [x] Тесты: 27 новых (points engine 11, condition evaluator 5, schemas 4, models 6, import schema 1)

## В работе
- Docker-сборка не проверена (Docker недоступен локально)
- Деплой на VPS, SSL, бэкапы — следующие шаги
- Фоновый триггер для авто-анализа дня (cron/APScheduler) — отложено

## Следующие шаги
1. Собрать Docker-образ и проверить `docker compose up` (на машине с Docker)
2. Заполнить `.env` реальными значениями
3. Настроить SSL (Let's Encrypt) для продакшена
4. Настроить pg_dump бэкапы по cron
5. Деплой на VPS
6. Добавить фоновый триггер авто-анализа тренировки в конце дня
