# Practice Loop — Memory v2: план на 3 этапа вперёд

> Статус: рабочий roadmap (принят владельцем 2026-08-13, Сессия 114).
> Дисциплина: этапы выполняются последовательно; параллельные темы (аудит P1/Gate B–D)
> не смешиваются с памятью, чтобы не прыгать.

## Этап 1 — M3 base: `memoryctl bootstrap` (детерминированный, stdlib-only)

Результат: воспроизводимый context pack + sentinel из текущего HEAD, без внешних зависимостей.

- классификация задачи (product/fact/code/ui/data/security/deploy + scope);
- выбор L0 (AGENTS.md + root/domain knowledge.md) и релевантных L1 (ADR/wiki/questions по scope/keyword);
- exact/lexical поиск кода (pure-Python, fallback без `rg`);
- impact frontier (тесты, миграции, call sites);
- context pack + sentinel (`.agent-runtime/`, gitignored);
- risks + required_checks из классификации.

Gate: unit-тесты на классификацию, выбор docs, поиск, детерминизм, denylist/HEAD staleness.

## Этап 2 — M3 benchmark + пилоты (только с доказанным приростом)

- [x] harness по `BENCHMARK_TASKS.md` (12 задач): recall@5, MRR, размер pack, лишние чтения
      (`tools/memoryctl/benchmark.py` → `docs/state/BENCHMARK.json`, Сессия 115);
- [x] baseline M3-base измерен: recall@5 0.26, MRR 0.356, pack ≤9 KiB, 0 forbidden;
- [x] решение владельца по пилотам (Сессия 116, **ADR-069**):
      - **embedding**: BGE-M3 (multilingual, fastembed/ONNX, local-only);
      - **пилот**: только Qdrant local vectors (shadow);
      - QMD (docs) и codebase-memory-mcp (graph) — отложены;
      - code-specific второй named-вектор — только если BGE-M3 слаб на коде;
      - зависимости — только в optional dev-group, рантайм продукта не трогается.
- [x] реализация пилота (Сессия 118): `memoryctl index-code` (структурные code units,
      stdlib `ast`/regex parser) + `memoryctl search-code` (hybrid dense+lexical, клиентский RRF
      fusion, exact confirmation) + A/B флаг `benchmark --vectors`; graceful degradation без
      optional `memory` dev-group; ~25 новых тестов.
- [x] **реальный A/B** (Сессия 118, Omniroute): embedding через локальный LLM-прокси
      Omniroute (`openrouter/openai/text-embedding-3-small`, 1536-dim; ADR-069 amended —
      BGE-M3 невозможна на VPS: fastembed не поддерживает + OOM локальной fp32-модели).
      Индекс 2167 units ≈ 4 мин, ~$0.01. **Результат: recall@5 0.24 → 0.37 (+0.13),
      MRR 0.356 → 0.496 (+0.14), pack ≤12 KiB, 0 forbidden; прирост на RU→EN задачах
      (T3/T4/T5/T8). Gate пройден → пилот admit (shadow/assist-режим).**

Gate: прирост recall@5/MRR против baseline 0.26/0.356 с pack ≤12 KiB; иначе пилот остаётся off/optional.

## Этап 3 — M4 preflight (обязательный)

- [x] `memoryctl sentinel` — проверка свежего preflight (status/head-ancestor/pack hash/TTL);
- [x] `memoryctl impact` — advisory: изменения кода vs impact frontier последнего pack;
- [x] `bin/practice-agent` launcher (bootstrap → sentinel-check → exec агента);
- [x] `.agents/skills/project-memory/SKILL.md` — единый workflow;
- [x] `.githooks/pre-commit` (opt-in: `git config core.hooksPath .githooks`) — блокирует code-commit без sentinel;
- [x] RUNBOOK.md §12 — как пользоваться;
- [ ] `.agents/practice-loop.ts` (Freebuff custom agent) — отложено: требует pinned Freebuff SDK, формат не верифицирован;
- [ ] `.agents/mcp.json` (per-agent MCP profiles) — отложено: MCP-серверы не подключены (M6);
- [ ] required CI `memory-lint` после периода наблюдения (сейчас informational);
- [ ] M5 (freeze legacy `memory/*` сессионных логов) — отдельным шагом после 10 сессий.

Gate: `memoryctl sentinel` блокирует code-commit без preflight; launcher отказывается стартовать без `ready`-sentinel.

## Вне этого плана (не смешивать)

- Аудит P1-1 (innerHTML XSS), P1-2 (weekly planner dates), P1-3 (media finalize target),
  P1-4 (browser E2E), P1-5 (transaction ownership), P1-6 (CSP), P1-7 (version), P2-*.
- Gate B (стабилизация) → Gate C (фронт/CSP) → Gate D (публичная эксплуатация).
