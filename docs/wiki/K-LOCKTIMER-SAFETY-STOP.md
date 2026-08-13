---
schema_version: memory/v2alpha1
id: K-LOCKTIMER-SAFETY-STOP
kind: knowledge
title: Safety stop в LockTimer
status: active
authority: derived
owners:
  - project-owner
scope:
  - locktimer/core
source_refs:
  - path: PRODUCT_DECISIONS.md
    anchor: PD-006
    relation: defines
  - path: docs/adr/ADR-029.md
    relation: supports
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 2bdbfb8bc41f5c3ebeec6f78b61c57b08348b2a6
review_on: source-change
---
# Safety stop в LockTimer

## Кратко

Safety/emergency stop всегда технически доступен и имеет приоритет. Игровое последствие может
существовать, но не блокирует остановку.

## Инварианты

- Переход active → safety_stopped немедленный, отменяет будущие occurrences.
- Прерывание всегда со штрафом (ADR-029); безусловные остановки без последствий не допускаются.
- Danger/safety UX: safety stop всегда видим, keyboard reachable, не зависит от JS confirm.

## Основные пути

- `app/locktimer/services/session.py` — safety stop реализация.
- `app/api/locktimer_commands.py` — `POST /sessions/{id}/safety-stop`.

## Failure modes

- Скрытие safety stop за меню/JS-confirm → риск недоступности в критический момент.

## Проверка

- `tests/test_locktimer_services.py` (safety stop) + smoke активной сессии.
