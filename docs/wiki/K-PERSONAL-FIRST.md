---
schema_version: memory/v2alpha1
id: K-PERSONAL-FIRST
kind: knowledge
title: Personal-first и три контура
status: active
authority: derived
owners:
  - project-owner
scope:
  - product
source_refs:
  - path: PRODUCT_DECISIONS.md
    anchor: PD-001
    relation: defines
  - path: PRODUCT_DECISIONS.md
    anchor: PD-002
    relation: supports
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 2bdbfb8bc41f5c3ebeec6f78b61c57b08348b2a6
review_on: source-change
---
# Personal-first и три контура

## Кратко

Practice Loop — прежде всего приватный личный трекер. Три контура определяются способом управления:
Personal (владение и действие), Social (ограниченные проекции без передачи управления), D/s (явные
полномочия над частью Personal).

## Инварианты

- Личный контур имеет безусловный приоритет разработки (PD-003).
- Chastity Timer — специализированный модуль Personal (PD-004).
- Игровые последствия — функция, а не дефект; допустимость задаётся заранее принятым правилом (PD-005).

## Границы

- Community — поздняя оболочка; публичный доступ — после Gate A–B аудита.

## Проверка

- Соответствие PD-* проверяется в PRODUCT_DECISIONS.md; конфликт → PRODUCT_DECISIONS.md главнее.
