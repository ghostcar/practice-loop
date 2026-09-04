---
schema_version: memory/v2alpha1
id: C-LOCKTIMER
kind: contract
title: LockTimer — domain contract
status: active
authority: technical
owners:
  - project-owner
scope:
  - locktimer/core
source_refs:
  - path: AGENTS.md
    relation: origin
  - path: docs/adr/ADR-047.md
    relation: supports
  - path: docs/adr/ADR-062.md
    relation: supports
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 2bdbfb8bc41f5c3ebeec6f78b61c57b08348b2a6
review_on: source-change
---
# LockTimer — domain contract

## Кратко

LockTimer — bounded context внутри Practice Loop (не второе приложение): таблицы `lock_*`,
собственные state machines, но один код, один Alembic head, общая auth/platform. Терминология
честная: lock = chastity (ADR-062); таблицы и API остаются `lock_*`, фронт — честные термины.

## Инварианты

- Safety stop всегда технически доступен и имеет приоритет; игровые последствия не блокируют остановку.
- Прерывание всегда со штрафом (ADR-029/038); penalty-механика доменная.
- Сессии: draft → active → safety_stopped; материализация слотов/задач на горизонте 90 дней.
- Окно открытия слота = `[planned_open, planned_open + max_late_seconds]`; без `max_late_seconds` окно нулевой ширины (баг S108 — исправлен).
- Номерные бирки: `close_tag_number` + `require_tag`; `verify_tag` сверяет номер, расхождение → `lock_tag_violations`.

## Границы

- Timer не импортирует Tracker models/services; platform-owned контракты в `app/platform/`.
- OCR для seal/media-потока реализован по ADR-181; HMAC остаётся источником истины. OCR именно кодов лекарств не входит в LockTimer-контракт.

## Failure modes

- Открыть слот в реальном времени при `allow_late_open=false` (нулевое окно) — учитывать grace.
- Penalty wiring в HTTP реализован по ADR-072: `skip_task` и позднее закрытие слота применяют явно заданную политику правила, а action API возвращает фактический результат penalty. Ошибочная или отсутствующая политика не должна превращаться в скрытый штраф.

## Проверка

- `pytest tests/test_locktimer_*.py tests/test_timer_standalone.py`.
