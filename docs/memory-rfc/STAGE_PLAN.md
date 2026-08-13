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

- harness по `BENCHMARK_TASKS.md` (12 задач): recall@5, MRR, размер pack, лишние чтения;
- сравнение baseline v1 workflow ↔ M3-base;
- после benchmark — решение владельца по пилотам (Qdrant local vectors, codebase-memory-mcp graph,
  QMD docs) и embedding profile (§10 RFC). Пилоты в `shadow` mode, не обязательны.

## Этап 3 — M4 preflight (обязательный)

- `.agents/skills/project-memory/SKILL.md`;
- `bin/practice-agent` launcher (bootstrap → freebuff → close);
- sentinel-проверка (pre-commit) → required CI `memory-lint` после периода наблюдения;
- M5 (freeze legacy `memory/*` сессионных логов) — отдельным шагом после 10 сессий.

## Вне этого плана (не смешивать)

- Аудит P1-1 (innerHTML XSS), P1-2 (weekly planner dates), P1-3 (media finalize target),
  P1-4 (browser E2E), P1-5 (transaction ownership), P1-6 (CSP), P1-7 (version), P2-*.
- Gate B (стабилизация) → Gate C (фронт/CSP) → Gate D (публичная эксплуатация).
