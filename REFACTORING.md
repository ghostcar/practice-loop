# REFACTORING.md — План декомпозиции крупных модулей

> Статус: **план утверждён владельцем (Session 81)**. Исполнение — по одному файлу за сессию,
> после каждого шага полный прогон тестов (592+) и ruff. Таблицы БД и API-контракты НЕ меняются.

## Принципы

1. **Механический перенос, ноль изменения поведения.** Функции переезжают в новые модули
   «как есть»; публичные имена сохраняются через re-export в `__init__.py`.
2. **Re-export как контракт.** Все потребители (`from app.locktimer.services.execution import
   start_session`) продолжают работать без изменений — пакет выглядит как один модуль.
3. **Целевой размер файла — ≤ 500 строк.** Всё, что больше, разбивается.
4. **Границы по домену**, а не по длине: вместе лежат функции одного слоя/темы.
5. **Каждый шаг завершается:** `ruff format` + `ruff check` + полный `pytest` + коммит.

## Очередь (по риску: сначала самое критичное и самое независимое)

| # | Файл (сейчас) | Строк | Целевая структура | Риск |
|---|---|---|---|---|
| 1 | `app/locktimer/services/execution.py` | 1409 | пакет `services/`: `drafts.py` (create/update/rules/reorder), `session.py` (start/safety_stop), `materializer.py` (occurences), `execution.py` (open/close/tasks/penalty/tag), `jobs.py` (outbox/queue) | Средний — ядро таймера, покрыто 70+ тестами |
| 2 | `app/api/import_data.py` | 988 | пакет `api/importers/`: `base.py` (CSV/JSON/helpers) + по импортёру на тип (measurements, inventory, entities, schedule, points, training, activity_logs, body_parts, locations); `import_data.py` остаётся роутером + экспорт | Низкий — независимый фичер |
| 3 | `app/api/references.py` | 817 | пакет `api/references/`: `body_parts.py`, `locations.py`, `categories.py`, `task_targets.py`, `search.py`; роутер-агрегатор | Низкий — CRUD без скрытой логики |
| 4 | `app/api/points_v2.py` | 940 | пакет `api/points/`: `config.py`, `balance.py`, `profiles.py`, `redemptions.py`, `schedule.py`, `measurements.py`, `inventory.py`, `charts.py`, `pages.py` | Низкий/средний — много разнородных фичер |
| 5 | `app/platform/social/repositories.py` | 1032 | пакет `social/repositories/`: `profile.py`, `consent.py`, `relationships.py`, `subjects.py`, `publications.py`, `notifications.py`, `verification.py`, `comments.py`, `moderation.py` | Средний — Social закрыт, тесты есть |
| 6 | `app/platform/social/api.py` | 957 | пакет `social/api/`: роутеры по контурам (`profile`, `relationships`, `subjects`, `feed`, `verification`, `comments`, `moderation`), `api.py` — include_router | Средний — страницы + формы |
| 7 | `app/llm/pipeline.py` | 953 | пакет `llm/`: `generate.py` (task/weekly/active config), `training.py` (daily plan/analysis), `diet.py` (diet/evaluate/synergy) | Средний — LLM-флоу |

## Метод выполнения шага (checklist)

1. Создать пакет (папку) с `__init__.py`, куда переносятся функции по домену.
2. Перенести тело функций механически (без рефакторинга внутри — он отдельным шагом).
3. В `__init__.py` сделать `from .module import *`-эквивалент — явный re-export всех публичных имён
   (для ruff: `__all__` или явный импорт).
4. `ruff format` + `ruff check` → убедиться, что нет F401 неиспользуемых импортов в исходниках.
5. `pytest tests/ -q` — полный прогон.
6. Коммит: `refactor(sNN): split <file> into <package> (mechanical, re-exports)`.

## Критерий готовности

- Нет файлов > 500 строк в `app/` (кроме `i18n/*` и `telegram/bot.py` — данные/специфика).
- 592+ тестов зелёные, ruff чистый.
- Ни один импорт потребителей не изменился (re-export сохраняет контракт).

## За пределами этого плана (отдельные решения)

- **Тесты на PostgreSQL**: сейчас всё на SQLite; concurrency-семантика PG проверяется вручную
  (миграции up/down, psql). Вынести в отдельный CI-джоб — когда появится второй инстанс.
- **Инлайн-JS в шаблонах** (`session_detail.html` ~540 строк): вынос в `static/js/pages/locktimer.js`
  — фронт-рефакторинг, отдельная сессия.
- **Разбивка `i18n/en.py`/`ru.py` (760+ строк)**: не трогаем — это словари данных.
