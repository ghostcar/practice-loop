---
schema_version: memory/v2alpha1
id: K-REPRODUCIBLE-PY311-BASELINE
kind: knowledge
title: Воспроизводимый Python 3.11 baseline
status: active
authority: derived
owners:
  - project-owner
scope:
  - engineering/testing
source_refs:
  - path: Dockerfile.dev
    relation: implementation
  - path: requirements.lock
    relation: dependency-lock
  - path: PLAN.md
    anchor: "S2 — Зелёный воспроизводимый baseline"
    relation: evidence
last_verified_at: 2026-08-18T00:00:00Z
last_verified_commit: fcda0aa9adb6132a550878bd4f84127c546f4bda
review_on: source-change
---
# Воспроизводимый Python 3.11 baseline

Канонический локальный test/lint-контур собирается из `Dockerfile.dev`: Python 3.11, системный
Git (нужен memory-suite) и зависимости из `requirements.lock`. Runtime media pipeline требует
Pillow; зависимость должна присутствовать одновременно в `pyproject.toml`, runtime lock и dev lock.

```bash
docker build -f Dockerfile.dev -t practice-loop-dev:py311 .
docker run --rm -v "$PWD:/workspace" -w /workspace practice-loop-dev:py311 ruff check .
docker run --rm -v "$PWD:/workspace" -w /workspace practice-loop-dev:py311 ruff format --check .
docker run --rm -v "$PWD:/workspace" -w /workspace practice-loop-dev:py311 pytest tests/ -q
```

Последнее доказательство относится только к конкретному рабочему дереву 18.08.2026:
`1132 passed, 1 skipped, 4 warnings`; Ruff check/format-check зелёные на 388 файлах. После любого
изменения HEAD эти числа являются историей, а не текущим доказательством.
