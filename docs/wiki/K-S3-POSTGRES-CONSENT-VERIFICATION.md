---
schema_version: memory/v2alpha1
id: K-S3-POSTGRES-CONSENT-VERIFICATION
kind: knowledge
title: PostgreSQL 15 verification для миграций 054–058 и consent concurrency
status: active
authority: derived
owners:
  - project-owner
scope:
  - data/migrations
source_refs:
  - path: scripts/s3_postgres_consent_verify.py
    relation: verification
  - path: PLAN.md
    anchor: "S3 — Миграции и интеграционные проверки"
    relation: evidence
last_verified_at: 2026-08-18T00:00:00Z
last_verified_commit: 37ae129c229046f1519670b6298f4aac34f1bd9b
review_on: source-change
---
# PostgreSQL 15 verification для миграций 054–058 и consent concurrency

S3 выполняется только на disposable PostgreSQL database. Живую compose-БД нельзя использовать
для downgrade/roundtrip. Проверенная последовательность: чистая БД `base→057→058`, затем
`058→057→058`; во всех точках `alembic current` совпал с ожидаемой revision.

После head запускается `scripts/s3_postgres_consent_verify.py`. Он проверяет двумя независимыми
транзакциями:

- concurrent double-grant одной цели создаёт одну версию;
- revoke немедленно закрывает `require_consent` с 428;
- concurrent re-grant создаёт ровно одну следующую версию;
- итоговая append-only история: `1 granted`, `2 revoked`, `3 granted` с `terms_version=1`;
- PostgreSQL CRUD и user cascade для `chastity_device_events`, `chastity_check_ins` и
  `aftercare_entries`.

Результат 18.08.2026: `S3_CONSENT_POSTGRES_OK`. Временная БД удалена. Запущенный compose после
проверки сохранил `healthz=ok`; его основная БД остаётся на 053 до отдельного S5 deploy gate.
