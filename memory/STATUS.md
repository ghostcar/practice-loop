# Текущий статус

Обновляется **в конце каждой сессии**. Последнее обновление: 2026-08-07 (сессия 15).

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

## Что сделано (Phase 9 — Penalty & Points v2)
- [x] PenaltyRedemption модель + миграция 008: отслеживание отработок штрафов (pending/completed/skipped)
- [x] Redemption API: `GET /api/v2/points/redemptions`, `POST .../complete` (возврат баллов), `POST .../skip`
- [x] Handler: авто-создание PenaltyRedemption при прерывании задачи
- [x] PointsProfile: полный CRUD (`POST`/`GET`/`DELETE`), назначение профиля на сущность
- [x] Threshold effects: авто-уведомления при пересечении negative/warning/good порогов
- [x] Gamification editor: `PUT /entities/{id}/gamification` — обновление конфига баллов/штрафов
- [x] Points page: список pending отработок (✅ Complete / ⏭ Skip), профили баллов, назначение на сущность
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

## В работе
- Ничего. Все 9 фаз завершены.

## Следующие шаги
1. Push на GitHub (`git push --force -u origin main`)
2. Telegram-бот: доработка и тестирование
3. Деплой на VPS, SSL, бэкапы
4. Фоновый триггер авто-анализа тренировки (APScheduler/cron)
5. Points spending: магазин наград, redeem баллов на бонусы
