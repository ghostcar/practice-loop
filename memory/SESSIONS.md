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
