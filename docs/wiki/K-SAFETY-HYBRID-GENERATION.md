---
schema_version: memory/v2alpha1
id: K-SAFETY-HYBRID-GENERATION
kind: knowledge
title: Гибридная генерация и комплаенс
status: active
authority: derived
owners:
  - project-owner
scope:
  - llm
  - safety
source_refs:
  - path: AGENTS.md
    anchor: Гибридная генерация
    relation: defines
  - path: docs/adr/ADR-001.md
    relation: supports
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 2bdbfb8bc41f5c3ebeec6f78b61c57b08348b2a6
review_on: source-change
---
# Гибридная генерация и комплаенс

## Кратко

LLM не генерирует откровенный контент. Каталог задач наполняют админ и пользователи; пользователь
осознанно отмечает допустимые задачи (опт-ин); LLM выбирает задачу и параметры из допустимого
набора на основе истории.

## Инварианты

- Никакого обхода safety-фильтров провайдеров и кодирования контента для сокрытия от LLM.
- LLM не является источником истины; каталог и опт-ин — первичны.
- Контент — только личное пространство пользователя, в рамках законов.

## Границы

- LLM-режимы full/abstract (ADR-030) управляют видимостью названий, не обходом фильтров.

## Failure modes

- Попытка «маскировать» контент под нейтральный → нарушение ToS, риск блокировки ключа.

## Проверка

- `tests/test_llm_*.py` — allowlist/validation; отсутствие eval.
