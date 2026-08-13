# Чекпоинт — 2026-08-13 (после Сессии 108)

> Зафиксировано перед кратким перерывом на сервисные задачи. Чтобы продолжить без потери контекста.
> См. также: `memory/STATUS.md`, `memory/OPEN_QUESTIONS.md`, `REFACTORING.md`.

## Текущее состояние

- **Тесты: 624/624 ✅, ruff ✅, format ✅** (полный прогон — Сессия 105/108).
- **Prod (VPS)**: задеплоены все правки через S108 (docker compose up -d --build), healthz 200, readiness ready, контейнеры healthy.
- **Git**: рабочее дерево чистое. **⚠️ 3 коммита не запушены в origin/main** (origin на S106):
  `b9ffbea` (S107 fix 500 /locktimer), `4eecb97` + `a06dffb` (S108 fix open слота + память).
- **Домен**: tracker.gorbunovr.ru (host-nginx → app:8000). Chrome на VPS **нет** — smoke-тесты прода идут на HTTP-уровне (urllib + cookie-jar).

## ✅ Сделано (главные вехи)

| Блок | Что | Сессии |
|---|---|---|
| Трекер | 11 фаз прототипа: каталог, LLM-пайплайн (hybrid, BYOK, repair), сессии, геймификация (XP/Points v2/достижения), Training, Measurements/Inventory, Import/Export/Charts, Calendar, Penalty/Redemptions, Telegram Bot v2, Auto-Analysis Scheduler | 1–62 |
| Новая модель активностей | ADR-035…042: ActivityCategory (16), статус-машина 11 состояний + аудит, DSL параметров (ADR-041), title-генератор i18n (ADR-042), scheduler в transition API | S58–62 |
| update2.md | Справочники BodyPart/TaskLocation/InventoryCategory + link-таблицы + DSL-селекторы + импорт/экспорт | S59–60 |
| **LockTimer Core** | C0–C9 ✅: platform composition (tracker/timer/combined), domain + 12 таблиц lock_* (миграция 025), materializer (5 slot + 6 task типов, rolling 90d), execution (slots/tasks/penalty/safety-stop/outbox), Universal Media + verification_challenges, LLM proposals, UI (overview/session detail/templates/calendar/dashboard card), numbered tags (пломбы), drag&drop правил и шаблонов, честная терминология (ADR-062) | S63–79 |
| **Social** | S0–S7 ✅: профили/consents, subjects/adapters, relationships/grants/blocks, публикации (redacted snapshot SHA-256) + feed, verification + comments, moderation, hardening + owner allowlist | S73–76 |
| Рефакторинг | REFACTORING.md **7/7 ✅**: execution→services/, import_data→importers/, references→references/, points_v2→points/, social repositories/, social api/, pipeline→llm/pipeline/ + **API v1→v2 консолидация** (всё под /api/v2) | S82–88 |
| Дата/время | tz-серия ✅: as_utc, utcnow→UTC, device-tz (ContextVar + localtime + JS Intl), границы суток (ADR-066), charts day-bucketing, TG_AUTO_ANALYSIS_TZ (ADR-067), календарь today в tz устройства | S90–98 |
| Доки/сервис | FUNCTIONAL/PRODUCT сверены, §15 = 54 таблицы, §17 = 15 social, pre_deploy_check 8/8 ✅, lint-долг в alembic убран, .env/README/RUNBOOK/DEPLOY_VPS дополнены | S99–105 |
| Prod smoke | S107: фикс **500 /locktimer + /calendar** (timestamptz vs VARCHAR date-строки) → `local_day_bounds()`; S108: фикс **open слота всегда 409** (max_late_seconds не пробрасывался) → полный цикл активной сессии зелёный | S107–108 |

## 🔧 Осталось доделать (долги, приоритет — личный контур)

1. **Q14 — LockTimer penalty не проброшен в HTTP** (S108). `apply_penalty` (ADD_TIME/BLOCK_NEXT_SLOT/MARK_TASK_FAILED/POINTS, idempotency, cap max_end_at) реализован и покрыт тестами, но **вызывающих нет**; UI «Skip this task? Penalty may apply» вводит в заблуждение; `lock_penalty_events` на проде = 0.
   → Рекомендация: привязать к `skip_task`/late-close через `rule.penalty_policy` (+ поле в форме) или POST /sessions/{id}/penalties. Нужно продуктовое решение: дефолтный тип/размер.
2. **On-time slot open UX** (S108). При `allow_late_open=false` окно открытия = `[planned_open, planned_open]` (нулевой ширины) — реально открыть нельзя. При `true` + `max_late_seconds` (теперь default 3600) — работает.
   → Нужно решение: разумный дефолт окна, auto-open по расписанию (job), или честный UI (кнопка появляется только в окне).
3. **Q13 — OCR/LLM верификация кодов по фото** (отложено S81). verification_challenges реализованы как ручной ввод кода (HMAC, constant-time, TTL, max attempts). OCR-распознавание по фото — deferred (маркеры в `app/models/media.py`, `app/services/media.py`, `app/api/verification.py`).
4. **Скоуп доступа на проде**: `locktimer_owner_allowlist` **пуст** — timer/social страницы доступны любому зарегистрированному юзеру. Решить политику до того, как появится публичный доступ (связано с Q5/Q6).
5. **Push**: 3 коммита (S107–S108) не запушены — запушить при первой возможности.

## ⏸ Не делали (осознанно отложено — не забыть)

- **S8 Social keyholder** — отложено (фокус на личном контуре, решение владельца S77).
- **Публичный доступ / регистрация для других**: Q5 (оплата/тарифы subscription_tier), Q6 (рейт-лимиты и лимиты расходов) — ⏸ до открытия.
- **Мобильное приложение** — после запуска базового портала (видение New_doc).
- **Масштабирование** — future (модель данных уже межпользовательская).
- **Браузерные UI-тесты на проде** — на VPS нет Chrome; локально есть browser-use (dev-машина), можно прогнать verify-tag диалог / countdown / drag&drop.
- **Video в media_assets** — deferred (nullable метаданные).
- **CDN/local assets** — FIXME-комментарии в base.html, план миграции на локальные assets (S57).
- **Кастомизация Telegram-текстов** — косметика, опционально (Q4 закрыт базовым форматом).

## ▶️ С чего продолжить после перерыва (предложенный порядок)

1. Push коммитов S107–S108 (сервисная пауза).
2. Полировка таймера: **Q14 penalty wiring** → **on-time open UX** → **Q13 OCR** (по приоритету).
3. Browser-тест таймера локально (диалог verify-tag, real-time countdown, drag&drop).
4. Затем вернуться к соцблоку: S8 keyholder / публичный доступ (Q5/Q6).
