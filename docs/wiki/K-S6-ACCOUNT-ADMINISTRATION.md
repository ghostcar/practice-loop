---
schema_version: memory/v2alpha1
id: K-S6-ACCOUNT-ADMINISTRATION
kind: knowledge
title: Account profile and administrator access controls
status: active
authority: derived
owners:
  - project-owner
scope:
  - platform/auth
  - operations/access
source_refs:
  - path: app/api/admin.py
    relation: implementation
  - path: app/api/account.py
    relation: implementation
  - path: PLAN.md
    anchor: S6 — Account profile и управление пользователями
    relation: evidence
last_verified_at: 2026-08-18T00:00:00Z
last_verified_commit: 0f4b3291d37c47a00e3f353203806480fd6c2a0e
review_on: source-change
---

# Account profile and administrator access controls

Migration 059 adds nullable `users.disabled_at`. A disabled account is rejected by cookie access,
bearer password login and refresh-token rotation; disabling and administrator password reset also
delete stored refresh tokens. This is an authentication boundary, not merely a UI flag.

`/account` is the authenticated self-profile. `/admin/users` is admin-only and supports roles,
disable/enable and explicit temporary-password reset. The current administrator cannot disable or
demote itself through these endpoints and must use self-service settings for its own password.

Verification on PostgreSQL 15 covered `base→059→058→059`. Production E2E covered role change,
disable causing login 401, re-enable, reset causing the old password to return 401 and the new
password to return 303. Test accounts were deleted afterward. The pre-059 backup is
`/tmp/practice_loop_pre_059_20260818.dump`.
