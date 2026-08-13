# Benchmark-набор Memory v2 (M0 baseline)

> Для каждой задачи фиксируются expected sources (пути/символы) и запрещённые false positives.
> Сравнение вариантов retrieval (см. MEMORY_IMPLEMENTATION_PLAN.md §7): время до первого
> релевантного файла, recall top-5, размер контекста, число лишних чтений, пропущенные call sites.

## 1. Маршрут → handler → service → model → миграция → тесты

- Запрос: «Что происходит при POST /api/v2/locktimer/slot-occurrences/{id}/open? Найди полную цепочку».
- Expected: `app/api/locktimer_commands.py` (api_open_slot) → `app/locktimer/services/execution.py` (open_slot) →
  `app/models/locktimer.py` (LockSlotOccurrence) → `alembic/versions/*025*` (миграция lock_*) →
  `tests/test_locktimer_services.py` (TestSlotExecution).

## 2. Изменить exported symbol → все consumers

- Запрос: «Переименовать/изменить сигнатуру `list_sessions_by_date_range` — найти всех потребителей».
- Expected: `app/locktimer/repositories.py` (определение) → `app/api/locktimer_ui.py`,
  `app/timeutils.py` (local_day_bounds), `tests/test_locktimer_services.py` / `tests/test_timeutils.py`.

## 3. Day-boundary / timezone поведение

- Запрос: «Границы суток „сегодня“ в tz устройства — где считается и как рендерится?».
- Expected: `app/timeutils.py` (local_today/local_date/local_day_bounds/client_tz ContextVar),
  `app/main.py` (middleware), `app/api/points/charts.py` (day bucketing), `app/templates/base.html` (JS Intl),
  `app/templates/dashboard_v2.html`, `tests/test_charts_tz.py`.

## 4. LockTimer safety stop

- Запрос: «Как работает safety/emergency stop в LockTimer — какие инварианты?».
- Expected: `app/locktimer/services/session.py` (safety_stop), `app/locktimer/domain.py` (validate_safety_stop_reason),
  `app/locktimer/enums.py` (SESSION_SAFETY_STOPPED), `app/api/locktimer_commands.py` (api_safety_stop),
  `tests/test_locktimer_services.py`; product boundary — `PRODUCT_DECISIONS.md` / `DOCUMENTATION_MAP.md` (safety приоритет).

## 5. Social/Dynamics boundary

- Запрос: «Граница Social и D/s: что Social хранит и что не хранит про отношения».
- Expected: `app/platform/social/models.py` (15 таблиц), `app/platform/social/api/relationships.py`,
  `PRODUCT_DECISIONS.md` (разделение Social и D/s), `memory/DECISIONS.md` (ADR по social).

## 6. LLM provider contract без чтения raw user data

- Запрос: «Контракт LLM-провайдера: где шифруется api_key и где гарантированно не светится raw_llm_response».
- Expected: `app/encryption.py`, `app/models/llm_config.py`, `app/security.py` (redacted projection),
  `app/api/llm_configs.py`, `app/platform/social/adapters.py` (Strips raw_llm_response).

## 7. UI-изменение с локализацией

- Запрос: «Добавить новую кнопку на страницу таймера с переводом EN/RU».
- Expected: `app/templates/locktimer/session_detail.html`, `app/i18n/en.py`, `app/i18n/ru.py`,
  `app/i18n/helpers.py` (detect_locale), `app/static/js/pages/*` (при необходимости).

## 8. Диагностика Alembic head

- Запрос: «Сколько сейчас миграций и какая последняя? Есть ли расхождение head?».
- Expected: `alembic/versions/*.py`, `alembic/env.py`, `alembic.ini`; факт — команда `alembic heads`
  (docs/state/FACTS.json), не текст из memory.

## 9. Найти superseded ADR

- Запрос: «Какое решение отменило „Timer Core обязан быть семантически нейтральным“?».
- Expected: `DOCUMENTATION_MAP.md` §4 (таблица superseded), `memory/DECISIONS.md` (ADR-062 и связные).

## 10. Отличить roadmap item от реализованного факта

- Запрос: «Реализован ли OCR/LLM верификация кодов по фото?».
- Expected: `app/models/media.py` / `app/services/media.py` / `app/api/verification.py` (OCR support deferred),
  `memory/OPEN_QUESTIONS.md` (Q13), `CURRENT_STATE.md`. Запрещено: утверждать реализацию по ROADMAP.

## 11. Воспроизвести старую ошибку из Git

- Запрос: «Почему /locktimer давал 500 на Postgres и как чинили?».
- Expected: `app/locktimer/repositories.py` (list_sessions_by_date_range), `app/timeutils.py` (local_day_bounds),
  Git log (commit `fix(s107)…`), `tests/test_locktimer_services.py` (TestDateRangeQueries).

## 12. Найти все тесты конкретного сервиса

- Запрос: «Где тесты на verify_tag и tag violations?».
- Expected: `tests/test_locktimer_services.py` (tag mechanics), `app/locktimer/services/tags.py`,
  `app/api/locktimer_commands.py` (api_verify_tag / api_tag_violations).
