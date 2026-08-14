# Система памяти проекта (practice-loop)

> **⚠️ FROZEN v1 (с Сессии 120, M5)** — legacy-память заморожена. Больше не дописывается.
> Активная память проекта — **Memory v2** (ADR-068, RFC в `docs/memory-rfc/`):
> L0 `AGENTS.md` + `knowledge.md`, L1 `docs/adr/` + `docs/wiki/` + `docs/questions/`,
> L2 generated `docs/state/FACTS.json` + `docs/state/NOW.md`, L3 код-поиск, L4 локальные эпизоды.
> Правила: `memoryctl` (lint/facts/adr/bootstrap/sentinel/impact), launcher `bin/practice-agent`,
> workflow `.agents/skills/project-memory/SKILL.md`. История сессий — в Git history.

Папка `memory/` — legacy v1: **состояние проекта**, **принятые решения**, **журнал сессий**
(до M5, Сессия 120). Читать как архив при необходимости; `memory/DECISIONS.md` остаётся
единственным поддерживаемым legacy-реестром (компилируется в `docs/adr/`).

## Файлы

| Файл | Что хранит | Статус (M5) |
| --- | --- | --- |
| `CONTEXT.md` | Краткий контекст проекта | FROZEN — архив |
| `STATUS.md` | Текущий статус (до M5) | FROZEN — архив; актуальное — `docs/state/NOW.md` |
| `DECISIONS.md` | Реестр принятых решений (ADR) | **ACTIVE (единственный)** — компилируется в `docs/adr/` |
| `SESSIONS.md` | Журнал сессий (до M5) | FROZEN — архив; история — Git |
| `OPEN_QUESTIONS.md` | Открытые вопросы | FROZEN — архив; актуальные — `docs/questions/` |
| `CHANGELOG.md` | История изменений (до M5) | FROZEN — архив; история — Git |

## Обязательные правила (v2, с Сессии 120)

1. **В начале каждой сессии** прочитать L0: `AGENTS.md` + `knowledge.md`; по scope —
   `docs/adr/`, `docs/wiki/`, `docs/questions/`, `docs/state/NOW.md`; если нужно —
   legacy `memory/DECISIONS.md` и `memory/OPEN_QUESTIONS.md` как архив.
2. **В конце каждой сессии** обновлять v2-артефакты: решения — `memory/DECISIONS.md`
   (компиляция в `docs/adr/`), новые знания — `docs/wiki/`, факты — `memoryctl facts`,
   история — Git commit. Legacy `memory/SESSIONS.md` / `STATUS.md` / `CHANGELOG.md` **не
   дописываются** (frozen).
3. **Не дублировать** содержимое `AGENTS.md` и `tracker-spec.md` в memory-файлах —
   ссылаться на них.
4. **Фиксировать сразу:** решение, принятое в середине сессии, записывается в `DECISIONS.md`
   в тот же момент, а не «потом, в конце».
5. Записи короткие и точные: факты, решения, ссылки. Без воды.
6. Статусы решений: `принято` / `отложено` / `отклонено`.
7. Рабочий preflight: `memoryctl bootstrap` → `sentinel` (обязателен для code-commit),
   `impact` — advisory. Запуск агента — `bin/practice-agent`.
