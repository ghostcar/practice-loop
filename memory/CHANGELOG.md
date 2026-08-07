# История изменений

| Дата | Файл | Изменение |
| --- | --- | --- |
| 2026-08-06 | `tracker-spec.md` | Создан по итогам интервью (5 раундов) |
| 2026-08-06 | `tracker-spec.md` | Решены открытые вопросы; разделы «Решённые/Осталось открытым» |
| 2026-08-06 | `AGENT.md` | Полностью переработан в единый стиль (8 разделов, без Semantic Masking) |
| 2026-08-06 | `tracker-spec.md` | Раздел 8 «Telegram-бот (детализация)» |
| 2026-08-06 | `tracker-spec.md` | Разделы 9–11: сессии/штрафы, каталог задач (+стартовый набор 30+), доска достижений |
| 2026-08-06 | `memory/*` | Создана система памяти: README, CONTEXT, STATUS, DECISIONS, SESSIONS, OPEN_QUESTIONS, CHANGELOG |
| 2026-08-06 | `AGENT.md` | Добавлены правила обязательного использования памяти (раздел 7) |
| 2026-08-06 | Phase 1 (40 файлов) | Созданы: проект, Docker, FastAPI, User-модель, JWT-аутентификация, Alembic, i18n EN/RU, темы dark/light, шаблоны, тесты |
| 2026-08-06 | Phase 2 (+14 файлов) | Entity/LLMProviderConfig/OptIn модели + миграция 002; CRUD API; шифрование API-ключей (Fernet); seed (30+ задач + 3 пресета); админ-панель; шаблоны каталога |
| 2026-08-06 | Phase 3 (+12 файлов) | ActivitySession/ActivityLog модели + миграция 003; Context Builder; OpenAI-клиент; JSON repair (3 попытки); tool calling; POST /tasks/generate; подсчёт токенов/стоимости; locale-промпты |
| 2026-08-06 | Phase 4 (+16 файлов) | UserProgress/Achievement/Notification модели + миграция 004; XP-движок (формулы/уровни/streak/комбо); достижения (13 seed); дашборд v2; доска достижений; in-app уведомления; сессии; приватность (экспорт/удаление); Telegram-бот (aiogram) |
| 2026-08-07 | Phase 5 (+6 файлов) | TrainingDay + subtasks; LLM-промпты тренировки; генерация плана дня; чек-листы; анализ дня; облегчённая геймификация |
| 2026-08-07 | Ruff + Tests | 181→0 ruff ошибок; 73 теста (9 test files) |
| 2026-08-07 | Phase 6 (+15 файлов) | Points v2: гибкая балльная система (gamification_config JSON на Entity); PenaltyConfig с уровнями+redemption; BonusCondition с eval-условиями; Thresholds; PointsTransaction/PointsProfile; ScheduleRule; BodyMeasurement + Chart.js; InventoryItem + shopping list; Import module (CSV/JSON шаблоны + upload + API-push); Seed v2; 100 тестов |
