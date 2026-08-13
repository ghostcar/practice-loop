# Задание Freebuff-агенту: внедрение Memory v2

> Статус: исполнимая спецификация, но не разрешение выполнять все milestone одним PR.  
> Владелец принимает архитектуру и запускает каждый milestone отдельно.  
> До cutover действующие `AGENTS.md` и `memory/*` продолжают выполняться.

## 1. Цель

Построить для `ghostcar/practice-loop` воспроизводимую многоуровневую память, которую стандартный
Freebuff-агент использует перед каждым изменением кода. Система должна масштабироваться вместе с
Personal-first продуктом и будущими Personal/Social/Dynamics/mobile областями, не загружая всю
историю проекта в context window.

Архитектура:

- короткий always-on contract;
- canonical wiki/ADR с provenance;
- generated facts текущего HEAD;
- hybrid code retrieval: exact/BM25 + AST/graph + local vectors;
- raw episodes только локально;
- deterministic bootstrap/impact/close;
- launcher, custom agent, hook и CI gates.

## 2. Обязательные входные документы

До планирования прочитать полностью:

1. `MEMORY_ARCHITECTURE.md`;
2. `CODE_MEMORY_DESIGN.md`;
3. `MEMORY_SCHEMA.md`;
4. `MEMORY_IMPLEMENTATION_PLAN.md`;
5. `DOCUMENTATION_MAP.md`;
6. действующий `AGENTS.md` и обязательные legacy memory files;
7. актуальные `PRODUCT_DECISIONS.md`, `PRODUCT_VISION.md`, `CURRENT_STATE.md`, `ROADMAP.md` в объёме,
   заданном `DOCUMENTATION_MAP.md` для текущего milestone.

Не считать этот файл новым источником продуктовой истины. При конфликте использовать действующую
authority map и остановить конфликтующую часть.

## 3. Режим выполнения

В одной сессии выполняется только один milestone или его явно ограниченный sub-step. Начальный
разрешённый объём после принятия RFC: **M0 + M1**, без freeze/migration legacy memory.

Перед изменениями:

1. `git fetch origin` и определить реальный `origin/main`;
2. показать `git status -sb`, текущую ветку и HEAD;
3. проверить, не работает ли другой agent с пересекающимися файлами;
4. создать ветку от актуального main;
5. зафиксировать scope и список новых/изменяемых файлов;
6. проверить Alembic heads и CI baseline, но не менять runtime/DB;
7. выполнить read-only inventory memory v1.

Если `AGENTS.md`, `DOCUMENTATION_MAP.md` или `memory/*` меняются параллельно, не редактировать их.
Синхронизироваться после push и повторить inventory.

## 4. Жёсткие ограничения

- Не менять продуктовую функциональность, API, модели БД, миграции или deploy в memory PR.
- Не создавать второй repo, frontend, auth stack, deployable или Alembic history.
- Не переопределять Personal-first границы, safety stop, privacy и owner decisions.
- Не принимать ADR/PQ за владельца и не выводить acceptance из кода.
- Не удалять и не перемещать legacy `memory/*` до M5 gate.
- Не сокращать действующий `AGENTS.md` до доказанного parallel run.
- Не коммитить raw transcripts, context packs, graph, vectors, model cache или source snippets cache.
- Не индексировать `.env*`, uploads, dumps, logs, backups, user/raw LLM data, vendor/minified/binary.
- Не отправлять исходники внешнему embedding API без отдельной privacy/security ADR.
- Не давать main agent прямой write access к Qdrant или graph store.
- Не использовать vector similarity как доказательство полного impact.
- Не продолжать при unsafe overlap, divergent Alembic heads, schema/privacy failure или stale index.

## 5. M0 — baseline и ADR

Создать read-only inventory/report, который фиксирует:

- текущий full HEAD и branch;
- размеры/lines обязательного startup context;
- все memory files, их роли и дублирующиеся claims;
- ссылки между docs и dangling refs;
- active/superseded ADR и open questions;
- фактические test/CI/migration evidence без копирования старых цифр;
- denylist audit;
- 10–15 benchmark tasks и expected source set.

Подготовить proposed ADR о Memory v2. Не менять status на accepted без решения владельца.

M0 done, когда report воспроизводим, не содержит sensitive data и не изменяет runtime/legacy flow.

## 6. M1 — schema, validator и local boundaries

Реализовать минимально:

```text
tools/memoryctl/
  __init__.py
  __main__.py
  inventory.py
  lint.py
  facts.py
  schemas.py
tests/memory/
.codebuffignore
.cbmignore
```

Обновить `.gitignore` только для:

```text
.agent-runtime/
.memory-local/
```

Команды:

```bash
python -m tools.memoryctl inventory
python -m tools.memoryctl lint
python -m tools.memoryctl facts
python -m tools.memoryctl facts --check
```

Требования:

- stdlib-first; новые dependencies только с обоснованием;
- deterministic JSON/Markdown serialization;
- генерация атомарна и идемпотентна;
- `--check` не пишет;
- full SHA и source command для каждого generated fact;
- test result записывается только после реального run;
- schema из `MEMORY_SCHEMA.md` покрыта positive/negative tests;
- scanner разрешает только repo-root paths после realpath;
- secret/PII patterns дают error до записи artifact;
- CI memory-lint сначала informational.

На M1 не создавать wiki/ADR split, vector index, custom agent или hooks.

## 7. M2 — canonical knowledge

Начинать только после M1 green и принятой ADR.

- split `memory/DECISIONS.md` без смены IDs;
- generated ADR index и bidirectional coverage report;
- active questions как атомарные pages;
- wiki pages по одному устойчивому contract;
- root/domain `knowledge.md` в size budget;
- source refs и supersedes graph;
- drafts от compiler проходят human review;
- legacy files продолжают обновляться параллельно до M5.

Нельзя переписывать продуктовую цель или исправлять историческую ADR «по смыслу» во время split.

## 8. M3 — bootstrap и hybrid code memory

Реализовать сначала exact-only bootstrap, затем graph/vector shadow sub-step.

### M3a: exact baseline

- task classification;
- authority-aware docs selection;
- exact path/symbol + `rg`/BM25;
- Git diff/history;
- context pack/sentinel;
- stale/conflict/denylist handling;
- benchmark baseline.

### M3b: structural graph

- pinned `codebase-memory-mcp` read-only profile;
- root allowlist и local cache;
- coverage/freshness check;
- definitions/imports/calls/impact;
- project links route/template/test/migration;
- exact source confirmation.

### M3c: vector shadow index

- storage adapter с Qdrant local mode;
- AST/symbol code units из `CODE_MEMORY_DESIGN.md`;
- local-only embedding adapter, model пока configuration;
- manifest/profile/content-addressed IDs;
- full/incremental/check/rebuild/shadow modes;
- add/modify/delete/rename и dirty overlay tests;
- hybrid retrieval с score explanation;
- vector results не меняют обязательный pack до benchmark.

После 10–15 задач предоставить comparison report. Не переводить vectors в `assist/required`, не
выбирать embedding model и не поднимать Qdrant server без отдельного решения владельца.

## 9. M4–M6

Следовать `MEMORY_IMPLEMENTATION_PLAN.md`. Особо:

- custom agent использует `handleSteps` и всегда запускает bootstrap первым;
- write-tool gating проверяется на pinned Freebuff/Codebuff SDK, не предполагается;
- при отсутствии SDK gate обязательность дают launcher + sentinel + hook;
- CI проверяет schema/freshness/diff impact, но не притворяется доказательством того, что человек
  действительно прочитал контекст;
- raw close episode остаётся local-only;
- freeze legacy происходит только после минимум 10 успешных parallel sessions и owner approval;
- security jobs добавляются по одному с baseline/triage, а не одним шумным PR.

## 10. Обязательные tests

Покрыть минимум:

- unique/duplicate ID;
- kind/status/authority combinations;
- dangling/cyclic supersedes;
- stale HEAD and changed ignore hash;
- deterministic generation;
- path traversal/symlink escape;
- secret and denied path;
- false accepted owner decision;
- missing/failed test evidence;
- code-unit split and stable IDs;
- index incremental add/modify/delete/rename;
- model/parser revision rebuild;
- vector unavailable fallback;
- graph unavailable incomplete impact;
- stale/partial collection rejection;
- exact confirmation mismatch;
- context size limits and explicit waiver expiry.

Project regression suite, migration roundtrip и Docker build остаются обязательными существующими
checks; memory tooling не имеет права их ослаблять.

## 11. Stop conditions

Остановиться и сообщить владельцу, если:

- появились пересекающиеся uncommitted changes другого agent;
- authority sources одного уровня конфликтуют;
- migration потребует изменения продукта/runtime;
- secret/user data уже попали в candidate artifact;
- выбранный MCP/vector package требует избыточных прав или network egress;
- Freebuff API не поддерживает заявленный enforcement и нет безопасного wrapper fallback;
- benchmark не показывает пользу graph/vectors;
- safe decomposition требует массового изменения legacy memory в раннем milestone.

Оставить green mergeable checkpoint с feature flags `off`/`shadow`, без fake stubs.

## 12. Формат отчёта после каждого milestone

Сообщить:

1. base HEAD, branch и commits;
2. exact files changed;
3. что реализовано и что сознательно не реализовано;
4. schema/architecture deviations с причиной;
5. команды и фактические результаты checks;
6. memory/index size и timings;
7. privacy/security findings;
8. rollback procedure;
9. открытые решения владельца;
10. следующий milestone, но не начинать его автоматически.

## 13. Definition of Done

Итоговая система считается внедрённой только при выполнении DoD из
`MEMORY_IMPLEMENTATION_PLAN.md`. Наличие Qdrant collection, MCP server или красивой wiki само по себе
не означает готовность. Критерий — воспроизводимый свежий context pack, полный impact, компактный
контекст, отсутствие утечек и доказанное улучшение benchmark.

