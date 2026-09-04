---
schema_version: memory/v2alpha1
id: C-ENGINEERING-MEMORY
kind: contract
title: Project Memory workflow (Memory v2)
status: active
authority: technical
owners:
  - project-owner
scope:
  - engineering/memory
applies_to:
  - tools/memoryctl/**
  - docs/adr/**
  - docs/wiki/**
  - docs/questions/**
  - docs/state/**
  - knowledge.md
source_refs:
  - path: MEMORY_ARCHITECTURE.md
    anchor: §8 Обязательное использование Freebuff
    relation: origin
  - path: MEMORY_IMPLEMENTATION_PLAN.md
    anchor: M4 — сделать preflight обязательным
    relation: origin
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: null
review_on: source-change
---

# Project Memory workflow (Memory v2)

## Language of owner communication (mandatory)

All communication with the owner is **Russian-only**: progress notes, work summaries,
problem explanations, plans, verification results, commit summaries and final reports.
English is allowed only inside code, identifiers, file/command names, exact quotations,
or unprocessed output from external tools; all explanatory text around those fragments
must remain in Russian. This applies regardless of the language of the owner’s request.

This skill is the single documented workflow for project memory. It keeps
retrieval, impact checking and closing deterministic and reviewable.

## When to use

Any task that touches `app/`, `tests/`, `alembic/`, `tools/` or changes
canonical docs. For pure doc/typo fixes the preflight is still cheap and
recommended.

## Workflow

1. **Start via launcher** — `bin/practice-agent "<task>"` (never raw agent
   without preflight). It runs `memoryctl bootstrap` and refuses to start if the
   sentinel is not `ready`.
2. **Preflight** — `python -m tools.memoryctl bootstrap --task "<task>"`:
   - classifies the task and selects L0/L1 canonical docs;
   - exact/lexical code search + impact frontier (tests/migrations/call sites);
   - writes `.agent-runtime/context-pack.json` + `session.json` (sentinel).
3. **Read, don't trust** — every retrieved path is confirmed by reading the file
   or `rg`; a semantic/vector candidate never becomes authority by itself.
4. **Before finishing a significant change** — `python -m tools.memoryctl impact`:
   out-of-scope code changes mean the preflight didn't cover them; re-run
   `bootstrap` if so.
5. **Before committing** — the pre-commit hook (`.githooks/pre-commit`, installed
   via `git config core.hooksPath .githooks`) verifies a fresh sentinel. CI
   `memory-lint` stays informational during the observation period.
6. **Close** — update memory through the deterministic commands, not freeform prose:
   - `python -m tools.memoryctl facts` (generated state, HEAD-bound);
   - `python -m tools.memoryctl adr compile` (only when ADRs change);
   - ADR/wiki/question proposals are `proposed`/`derived` — product/safety
     decisions are never auto-accepted.

## ADR registry format (canonical, mandatory)

`memory/DECISIONS.md` rows follow exactly one layout (the format contract is
also embedded as an HTML comment at the top of the file):

```
| ADR-NNN | YYYY-MM-DD | Тема | Краткое решение | статус |
```

- `статус` — only `принято` | `отложено` | `отклонено` (english synonyms are
  accepted by the parser for legacy rows, never for new ones).
- Detailed section (optional): `### ADR-NNN — Тема` — H3 + em-dash exactly.
  A `**Date:**`/`**Status:**` block inside lets section-only ADRs compile.
- Skipped numbers get a tombstone comment: `<!-- ADR-NNN: номер не использован -->`.
- Decision text must avoid literal `|` (the parser reconstructs them, but the
  canonical row keeps one cell per field).
- `docs/adr/ADR-*.md` without the `Compiled by` marker are hand-written and are
  NEVER overwritten by `adr compile`; generated files keep their provenance
  timestamps on recompile (no churn). Verify with `adr check` (bidirectional).

## Invariants

- Preflight is mandatory for code changes in the supported workflow; bypass is
  recorded as unsupported.
- `docs/state/*` and `docs/adr/*` are generated, deterministic and HEAD-bound —
  never hand-edit.
- Secrets, uploads, raw LLM responses, user data and raw transcripts are never
  indexed or committed (denylist + secret scan in `memoryctl lint`).
- Owner product/safety decisions are accepted only by the owner.

## Verification

```bash
python -m tools.memoryctl sentinel       # fresh preflight
python -m tools.memoryctl impact         # changes covered by preflight
python -m tools.memoryctl lint           # 0 errors
python -m tools.memoryctl facts --check  # generated state fresh
python -m tools.memoryctl adr check      # ADR split bidirectional
```
