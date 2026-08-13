---
schema_version: memory/v2alpha1
id: C-TESTS
kind: contract
title: Tests — domain contract
status: active
authority: technical
owners:
  - project-owner
scope:
  - tests
source_refs:
  - path: AGENTS.md
    relation: origin
  - path: docs/adr/ADR-015.md
    relation: supports
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 2bdbfb8bc41f5c3ebeec6f78b61c57b08348b2a6
review_on: source-change
---
# Tests — domain contract

## Кратко

pytest unit + integration (SQLite, без внешних сервисов); конкуренция, cross-user, privacy,
migration roundtrip — обязательные классы тестов.

## Инварианты

- Cross-user тесты для каждого owner-scoped домена.
- Concurrency/idempotency тесты для переходов состояний (conditional UPDATE + rowcount).
- Память: `tests/memory/` покрывает memoryctl (schema/facts/lint/inventory/adr).

## Границы

- Браузерных E2E/a11y тестов пока нет (P1-4 аудита) — добавить Playwright smoke до публичного доступа.

## Failure modes

- Тесты, зависящие от wall-clock (использовать clock abstraction / детерминированные входы).
- SQLite-only ложные «зелёные» против PG-поведения (напр. `AT TIME ZONE`).

## Проверка

- `pytest tests/ -q` — полный suite.
