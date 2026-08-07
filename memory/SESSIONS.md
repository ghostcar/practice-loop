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
