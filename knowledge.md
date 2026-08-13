---
schema_version: memory/v2alpha1
id: C-PRACTICE-LOOP
kind: contract
title: Practice Loop — always-on contract
status: active
authority: technical
owners:
  - project-owner
scope:
  - platform
source_refs:
  - path: AGENTS.md
    relation: origin
  - path: PRODUCT_DECISIONS.md
    relation: supports
  - path: DOCUMENTATION_MAP.md
    relation: supports
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 2bdbfb8bc41f5c3ebeec6f78b61c57b08348b2a6
review_on: source-change
---
# Practice Loop — always-on contract

## Кратко

Practice Loop — Personal-first приложение для отслеживания личных активностей.
Три контура по способу управления: Personal (владение и действие), Social (ограниченные
проекции без передачи управления), D/s (явные полномочия над частью Personal). Один
репозиторий, один deployable, один Alembic head. Три варианта сборки: `tracker`, `timer`,
`combined` (см. ADR-048).

## Инварианты

- Один Alembic head; `create_all` в startup запрещён.
- Владелец задаёт продуктовые решения; агент не принимает их автоматически.
- Безопасность/приватность строже любых игровых последствий; safety stop всегда доступен.
- Секреты только в `.env`; никогда в коде, git, памяти.
- Owner-scoped доступ — контракт во всех доменах (cross-user тесты обязательны).

## Границы

- Личный контур приоритетен; публичный доступ — после Gate A–B аудита.
- Мобильное приложение и масштабирование — после запуска портала (ADR-063/064).
- Не менять продукты/БД в рамках работ по памяти.

## Failure modes

- Смешение решения/факта/истории → различать authority (см. DOCUMENTATION_MAP.md).
- Регенерация FACTS.json при чужом HEAD → staleness (см. `memoryctl facts --check`).
- Двойной commit транзакций в роутерах → единый transaction-owner (аудит P1-5).

## Проверка

- `pytest tests/` — полный suite.
- `python -m tools.memoryctl lint` и `facts --check`.
- `pre_deploy_check.sh`.
