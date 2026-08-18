---
schema_version: memory/v2alpha1
id: K-S5-PRODUCTION-DEPLOY-058
kind: knowledge
title: S5 production-like deploy through migration 058
status: active
authority: derived
owners:
  - project-owner
scope:
  - operations/deploy
  - data/migrations
source_refs:
  - path: PLAN.md
    anchor: S5 — Release/deploy gate B–C
    relation: evidence
last_verified_at: 2026-08-18T00:00:00Z
last_verified_commit: 5c6fe2b291fdefd91d94beb160d4ee29a62bd3cd
review_on: source-change
---

# S5 production-like deploy through migration 058

On 18 August 2026 the locally running production-like Docker Compose deployment was upgraded
from Alembic revision 053 (`9a8b7c6d5e4f`) to the single source head 058
(`a9b0c1d2e3f4`). Before migration, a PostgreSQL custom-format backup was written to
`/tmp/practice_loop_pre_s5_20260818.dump`.

Evidence collected during the gate:

- full host suite: 1132 passed, 1 skipped;
- Ruff check/format and single-head check passed after a two-file formatting correction;
- production image built and both app/db containers reported healthy;
- migration logs showed sequential upgrades 054, 055, 056, 057 and 058;
- `scripts/prod_smoke.sh` returned `SMOKE_OK`;
- password-change E2E on PostgreSQL proved old login rejected (401) and new login accepted (303);
- Chromium portal smoke/a11y/usability passed 6/6 after teaching the browser helper to complete
  the mandatory first-login consent flow;
- all smoke/browser users were deleted after verification.

The account `roman@gorbunovr.ru` existed. Its password was reset to a temporary non-empty value;
the deployed `/settings` page now provides self-service password changes with current-password
verification and refresh-token revocation. Do not record the temporary password in project memory.
