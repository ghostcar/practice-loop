---
schema_version: memory/v2alpha1
id: K-DEVICE-TZ-BUCKETS
kind: knowledge
title: Device-tz дневные бакеты и границы суток
status: active
authority: derived
owners:
  - project-owner
scope:
  - platform/time
source_refs:
  - path: docs/adr/ADR-066.md
    relation: defines
  - path: docs/adr/ADR-067.md
    relation: supports
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 2bdbfb8bc41f5c3ebeec6f78b61c57b08348b2a6
review_on: source-change
---
# Device-tz дневные бакеты и границы суток

## Кратко

Дневные ряды (графики, календарь, «сегодня») бакетируются в Python по `local_date(created_at)`
из device-календарного дня, а не SQL `func.date()` (UTC-день БД).

## Инварианты

- Графики: бакеты по device-local дню; подписи оси — `local_today()`; cutoff — UTC-инстант.
- Фоновые задачи без request-контекста берут «сегодня» из `tg_auto_analysis_tz` (IANA), не из ContextVar.
- Все datetime сравнения — aware UTC; отображение — через device-tz.

## Границы

- TTL-пурдж raw-ответов — сравнение UTC-инстантов, не граница суток.

## Failure modes

- SQL `func.date()` сдвигает бары на день для пользователей вблизи UTC-полуночи.

## Проверка

- `tests/test_timeutils.py` + chart-эндпоинт тесты с device-tz бакетированием.
