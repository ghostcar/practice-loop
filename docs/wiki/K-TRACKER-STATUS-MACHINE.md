---
schema_version: memory/v2alpha1
id: K-TRACKER-STATUS-MACHINE
kind: knowledge
title: Статус-машина задач (11 состояний)
status: active
authority: derived
owners:
  - project-owner
scope:
  - tracker/core
source_refs:
  - path: docs/adr/ADR-040.md
    relation: defines
  - path: docs/adr/ADR-036.md
    relation: supports
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 2bdbfb8bc41f5c3ebeec6f78b61c57b08348b2a6
review_on: source-change
---
# Статус-машина задач (11 состояний)

## Кратко

Задача (`activity_logs`, эволюция в ActivityTask — ADR-036) проходит через строгий enum из 11
состояний с правилами переходов и аудитом (`activity_task_history`).

## Инварианты

- Переходы атомарны: conditional UPDATE + rowcount (pattern complete_once); rowcount=0 → idempotent.
- cancelled до начала / skipped / not_applicable — без штрафа и без награды; partially_completed — без награды; stopped — штраф (ADR-038).
- planned_parameters и actual_parameters раздельны; actual валидируется против схемы.

## Основные пути

- `app/models/task_status.py` — enum и правила переходов.
- `app/api/task_flows.py` — transition API с аудитом.

## Проверка

- `tests/test_phase2_task_flows.py` — переходы, аудит, идемпотентность.
