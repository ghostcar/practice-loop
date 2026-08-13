---
schema_version: memory/v2alpha1
id: C-ALEMBIC
kind: contract
title: Migrations — domain contract
status: active
authority: technical
owners:
  - project-owner
scope:
  - data/migrations
source_refs:
  - path: AGENTS.md
    relation: origin
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 2bdbfb8bc41f5c3ebeec6f78b61c57b08348b2a6
review_on: source-change
---
# Migrations — domain contract

## Кратко

Один Alembic head; схема управляется миграциями, а не `create_all` в startup. Все таблицы —
в `app/models/` и `app/platform/social/models.py` (и `app/locktimer`).

## Инварианты

- Ровно один Alembic head; migration roundtrip (up→down→up) проверяется в CI на PG15.
- Новые таблицы/поля — отдельной миграцией; без переименований «ради имени» (ADR-062).

## Границы

- Не трогать legacy-данные деструктивно; rollback-миграции сохраняют legacy-значения.

## Failure modes

- Расхождение `pyproject.toml`/README (0.8.0) и FastAPI metadata (0.9.0) — один источник версии.

## Проверка

- `alembic heads` — один head.
