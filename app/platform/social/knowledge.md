---
schema_version: memory/v2alpha1
id: C-SOCIAL
kind: contract
title: Platform Social — domain contract
status: active
authority: technical
owners:
  - project-owner
scope:
  - social
source_refs:
  - path: AGENTS.md
    relation: origin
  - path: docs/adr/ADR-058.md
    relation: supports
  - path: docs/adr/ADR-059.md
    relation: supports
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 2bdbfb8bc41f5c3ebeec6f78b61c57b08348b2a6
review_on: source-change
---
# Platform Social — domain contract

## Кратко

`app/platform/social/` — независимый пакет, не импортирует Tracker/Timer. Публичная идентичность —
alias-based profiles (social_profiles), доменные объекты регистрируются через opaque
`social_subjects` + SocialSubjectAdapter. Управление через grants, а не через общий «дружеский»
доступ.

## Инварианты

- Personal остаётся владельцем данных; Social — ограниченные проекции (redacted), без передачи управления.
- Единый relationship/block graph: invitation lifecycle (pending→accepted/declined/expired/revoked), cooldown 24h.
- Block отменяет pending и отключает accepted grants.
- Verification: quorum (min_approvals→verified, max_rejections→review_required); один голос на верификатора; owner не голосует за свои запросы.
- Moderation: жалобы/очереди/скрытие — до открытия Social (S5).

## Границы

- S8 keyholder / публичный доступ — после личного контура; сейчас не в scope.
- Без публикации raw_llm_response, penalty_details, user_id в проекциях.

## Failure modes

- Выдавать публичный media напрямую (P0-1 аудита) — только через owner/grant-авторизованный endpoint.
- Смешение display_role и capability grants: display_role — только UI-лейбл.

## Проверка

- `pytest tests/test_social_*.py tests/test_social_privacy_audit.py`.
