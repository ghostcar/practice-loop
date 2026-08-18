---
schema_version: memory/v2alpha1
id: K-AUTHENTICATED-TEMPLATE-CONTEXT
kind: knowledge
title: Authenticated pages must pass user into the base template
status: active
authority: derived
owners:
  - project-owner
scope:
  - platform/auth
  - ui/shell
source_refs:
  - path: app/templates/base.html
    relation: contract
  - path: app/api/today.py
    relation: fixed-example
last_verified_at: 2026-08-18T00:00:00Z
last_verified_commit: 299d2814779296063c9d854f9142db3ea3b3627f
review_on: source-change
---

# Authenticated pages must pass user into the base template

FastAPI dependency authentication and Jinja shell authentication are separate concerns. A route
can successfully resolve `get_current_user` yet render the anonymous shell if its
`TemplateResponse` context omits `user`.

Every authenticated SSR route extending `base.html` must pass `"user": user`. Browser smoke must
assert that the sidebar exists and that the guest login link does not exist, rather than relying
only on HTTP 200. The `/today` regression fixed in S6a is the canonical example.
