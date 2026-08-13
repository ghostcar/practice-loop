# Practice Loop — план внедрения Memory v2

> Статус: RFC-план. Выполнение начинается только после принятия архитектуры и ADR.  
> Версия: 0.2 от 2026-08-13.  
> Исходная точка RFC: `main` `4ed5eec` (S96); перед каждым milestone используется актуальный HEAD.  
> Этот файл не разрешает автоматически менять продуктовые решения или существующую память.

## 1. Стратегия перехода

Переход выполняется аддитивно и обратимо. Сначала появляются schema, validator и новый retrieval,
затем проводится параллельная проверка с memory v1, и только после доказанной эквивалентности старые
агрегаты исключаются из startup. Массовое перемещение `memory/*` в первом PR запрещено.

Каждый milestone — отдельная ветка/PR с собственным rollback. Миграция памяти не совмещается с
изменением runtime-функциональности, схемы БД или продуктового scope.

## 2. Условия старта

Перед любой реализацией:

1. дождаться завершения и push активной Freebuff-сессии;
2. получить новый `origin/main`, зафиксировать HEAD и проверить diff с базой RFC;
3. убедиться, что нет незакоммиченных пересекающихся изменений;
4. проверить единственный Alembic head и текущий CI;
5. пересчитать inventory и размеры `memory/*`;
6. зафиксировать решение о Memory v2 отдельной ADR;
7. подтвердить владельцем вопросы из раздела 10.

Если текущая сессия продолжает менять `AGENTS.md`, `DOCUMENTATION_MAP.md` или `memory/*`, milestone
с этими файлами не начинается. Новые RFC-файлы могут существовать отдельно.

## 3. Порядок milestone

### M0 — принять RFC и измерить baseline

**Результат:** согласованная архитектура и воспроизводимая точка сравнения.

Работы:

- review `MEMORY_ARCHITECTURE.md`, `MEMORY_SCHEMA.md` и этого плана;
- ADR «Adopt layered project memory v2» со статусом proposed → accepted владельцем;
- скрипт read-only inventory: размер startup files, число документов, ссылки и противоречия;
- набор 10–15 исторических задач разных типов для benchmark;
- baseline: время поиска, прочитанные bytes, найденные релевантные файлы, пропущенные зависимости;
- privacy review уже опубликованной memory v1 без переписывания Git history.

Gate:

- ADR принята явно;
- benchmark-набор и ожидаемые релевантные источники сохранены;
- RFC не противоречит `DOCUMENTATION_MAP.md` и продуктовым решениям;
- runtime diff отсутствует.

Rollback: удалить только RFC-ветку; действующий workflow не менялся.

### M1 — добавить schema, lint и безопасные локальные каталоги

**Результат:** можно создавать Memory v2 artifacts, не меняя startup Freebuff.

Новые элементы:

- `tools/memoryctl/` с командами `inventory`, `lint` и `facts`;
- schema/tests для форматов из `MEMORY_SCHEMA.md`;
- `.agent-runtime/` и `.memory-local/` в `.gitignore`;
- `.codebuffignore` и `.cbmignore` с denylist;
- `docs/state/FACTS.json` и `docs/state/NOW.md`, генерируемые из текущего HEAD;
- CI job `memory-lint`, пока informational/non-required.

Правила реализации:

- стандартная библиотека Python, если зависимость не доказана необходимой;
- генерация идемпотентна и имеет `--check`;
- timestamps передаются через clock abstraction для стабильных тестов;
- manifest никогда не утверждает, что тесты прошли, если команда не была выполнена;
- dirty tree отражается явно;
- scanner работает только по allowlist и не читает secret paths.

Gate:

- unit tests на valid/invalid schema, stale HEAD, duplicate ID и denylist;
- повторная генерация не создаёт diff;
- `memoryctl facts --check` распознаёт смену HEAD;
- secret scan не находит новые чувствительные данные;
- текущие test/lint/migration checks остаются зелёными.

Rollback: удалить новые paths и CI job; memory v1 продолжает работать.

### M2 — построить каноническую wiki и атомарные ADR

**Результат:** решения и устойчивые знания извлекаются точечно.

Работы:

- создать `docs/adr/` и перенести каждую запись `memory/DECISIONS.md` в отдельную ADR без смены ID;
- сформировать generated `docs/adr/README.md`;
- создать атомарные `docs/wiki/` pages из нормативных и инженерных документов;
- создать `docs/questions/` только для активных вопросов;
- добавить корневой и domain-local `knowledge.md`;
- проставить `source_refs`, `status`, `authority`, `supersedes` и verification HEAD;
- запустить двустороннюю проверку: каждая active legacy ADR отображена в новом формате и наоборот.

Компиляция выполняется по модели raw sources → draft pages → lint → human review → publish.
LLM не может менять source document и не может выставлять `accepted` продуктовой ADR.

Gate:

- 100% действующих ADR имеют уникальный файл и provenance;
- все ссылки разрешаются, циклы `supersedes` отсутствуют;
- safety/privacy pages проверены отдельно;
- root + local always-on knowledge укладывается в 10 KiB;
- по benchmark новый retrieval не пропускает обязательные решения.

Rollback: startup всё ещё читает v1; новые `docs/*` можно убрать без потери источника.

### M3 — добавить hybrid retrieval и память кода

**Результат:** `memoryctl bootstrap` собирает контекст задачи с доказуемой свежестью.

Базовая реализация:

- metadata filter + точный path/symbol search;
- `rg`/лексический или BM25-поиск по allowlisted docs;
- Git diff/history для изменяемых областей;
- существующий Tree-sitter code map Freebuff;
- context pack и sentinel по schema.

Code retrieval реализуется по `CODE_MEMORY_DESIGN.md`:

- parser режет исходники по AST/symbol units, а не по фиксированному числу tokens;
- `codebase-memory-mcp` даёт definitions/imports/calls/impact graph;
- Qdrant local mode хранит vectors и фильтруемый metadata payload; BM25/dense fusion может
  выполняться в `memoryctl`, если pinned local mode не поддерживает нужный hybrid query;
- exact, BM25, graph и vectors объединяются через объяснимый rank fusion;
- top candidates расширяются связанными tests/migrations/callers;
- найденный vector candidate подтверждается точным path/symbol read;
- manifest привязан к HEAD, parser, embedding revision и ignore hash;
- agent может только читать через `memoryctl`, индексатор — отдельный controlled process.

Пилоты и feature flags:

- QMD только для hybrid document retrieval;
- `codebase-memory-mcp` для symbols/imports/calls/impact;
- Qdrant local collection в `shadow` mode: результаты логируются для benchmark, но не обязательны;
- локальный cache, ключ `(repository_id, HEAD, indexer_version, ignore_hash)`.

При росте репозитория решение о переходе с local mode на Qdrant server принимается по latency,
размеру индекса и стабильности incremental update. Количество файлов само по себе не является gate.

Benchmark-варианты:

1. текущий workflow;
2. Memory v2 без embeddings/code graph;
3. Memory v2 + code graph;
4. Memory v2 + graph + code vectors;
5. Memory v2 + QMD, если документный поиск остаётся слабым.

Предлагаемые пороги допуска обязательной зависимости:

- обязательные sources в top-5 не хуже baseline и целевой recall не ниже 90%;
- median context pack не больше 12 KiB;
- меньше лишних полных file reads;
- все известные call sites в impact-задачах найдены;
- vector recall@5/MRR измерены отдельно для русских task prompts и англоязычного кода;
- vector-only false positives не попадают в impact без exact/graph evidence;
- stale индекс всегда отклонён;
- дополнительное время preflight приемлемо и измерено.

Инструмент, не прошедший benchmark, остаётся optional или удаляется.

Rollback: отключить feature flag и удалить regenerable cache; canonical memory сохраняется.

### M4 — сделать preflight обязательным для стандартного Freebuff

**Результат:** поддерживаемый агент не начинает разработку без свежего context pack.

Новые элементы:

- `.agents/skills/project-memory/SKILL.md`;
- `.agents/practice-loop.ts` с детерминированным первым шагом;
- `bin/practice-agent` как documented launcher;
- `.agents/mcp.json` с минимальными per-agent profiles;
- pre-commit check sentinel;
- required CI `memory-lint` после периода наблюдения.

Сценарий launcher:

1. проверяет repo root и установленную/pinned версию Freebuff;
2. принимает task text или файл задачи;
3. запускает `memoryctl bootstrap`;
4. проверяет `ready`, HEAD, task hash и denylist report;
5. запускает `freebuff --agent practice-loop`;
6. после изменений вызывает impact/verification stage;
7. завершает сессию через `memoryctl close`.

Негативные тесты:

- отсутствующий sentinel;
- sentinel для другого HEAD;
- изменённый task hash;
- повреждённая schema;
- индекс включает denied path;
- прямой commit после смены HEAD;
- недоступный optional MCP;
- конфликт authority;
- dirty tree с пересечением чужих изменений;
- попытка автоматически принять owner decision.

Недоступный QMD/code graph не блокирует работу: bootstrap переходит на exact-search fallback и
фиксирует degraded mode. Ошибка schema, stale HEAD или privacy violation блокируют commit.

Rollback: запуск обычного Freebuff остаётся технически возможен, но помечен unsupported; снять
required check можно отдельным revert без изменения code/data.

### M5 — заменить session logging на controlled close

**Результат:** сессия порождает только новые знания, а не четыре копии одного события.

`memoryctl close`:

- читает start/end HEAD и фактический diff;
- прикладывает выполненные команды и результаты;
- сохраняет raw episode локально;
- предлагает один из outcomes: no-memory-change, fact refresh, knowledge proposal, ADR proposal,
  active question или release note;
- запускает sanitization и secret scan;
- не коммитит proposal как accepted без требуемого review.

После параллельной работы минимум в 10 сессиях:

- `memory/SESSIONS.md` и `memory/CHANGELOG.md` замораживаются;
- `memory/STATUS.md` заменяется `docs/state/NOW.md` в startup;
- `memory/CONTEXT.md` исключается из mandatory reads;
- `AGENTS.md` сокращается и указывает на launcher/retrieval;
- `memory/README.md` объясняет границу frozen v1 / active v2.

Gate:

- 10 последовательных сессий имеют валидные packs и close reports;
- v2 воспроизводит все active decisions/questions;
- отсутствуют потерянные факты и новые raw transcripts в Git;
- размер startup снизился до целевого;
- владелец отдельно одобрил отключение v1 startup.

Rollback: вернуть ссылки v1 в `AGENTS.md`; frozen files сохранены.

### M6 — security и эксплуатационные интеграции

**Результат:** память не расширяет supply-chain и production risk.

CI добавляется последовательно, чтобы шум не скрывал реальные проблемы:

1. Gitleaks — secrets;
2. `pip-audit` или OSV-Scanner — Python dependencies;
3. Semgrep — SAST;
4. Trivy — filesystem/container;
5. CodeQL — более глубокий анализ на PR/schedule.

MCP-профили:

| Профиль | Разрешено | Запрещено |
|---|---|---|
| Scout | GitHub read, docs search, code graph read | Repo/DB writes |
| Builder | Локальные project tools и patch | Production и secrets |
| Verifier | Test runner, Playwright test environment | Изменение продукта |
| Incident | Sentry read при наличии | Resolve/delete без человека |

Подключение БД допускается только к dev/staging, read-only и с явным DSN scope. Production MCP не
входит в стандартный workflow. Codex Security или другой LLM-аудитор может использоваться для
triage, но merge gate остаётся за детерминированными scanners и review.

## 4. Миграционная карта memory v1

| Текущий файл | Действие | Целевой источник |
|---|---|---|
| `memory/README.md` | Переписать последним | Указатель на active v2 и frozen v1 |
| `memory/STATUS.md` | Сверить, затем freeze | Generated `docs/state/NOW.md` + `FACTS.json` |
| `memory/SESSIONS.md` | Freeze, больше не дописывать | Raw local episodes; Git/PR для истории |
| `memory/CHANGELOG.md` | Freeze | Git history и release notes |
| `memory/DECISIONS.md` | Split без смены ADR ID | `docs/adr/ADR-NNN-*.md` + generated index |
| `memory/OPEN_QUESTIONS.md` | Оставить только active при переносе | `docs/questions/*.md` |
| `memory/CONTEXT.md` | Извлечь актуальное, снять startup | `knowledge.md` и domain pages |
| `AUDIT_SESSION_37.md` | Freeze как evidence | Git history / archived v1 |
| `FRONTEND_AUDIT_SESSION_38.md` | Freeze как evidence | ADR/wiki только для устойчивых выводов |
| `FIX_SESSION_39.md` | Freeze как evidence | Git history |
| `DEFERRED_FIX_SESSION_40.md` | Разобрать active debt | Трекер/active question; остальное history |

Перемещение больших файлов ради эстетики не требуется: это увеличит diff и не удалит их из Git
history. Достаточно frozen headers, карты и исключения из retrieval по умолчанию.

## 5. Предлагаемая последовательность PR

1. `docs: propose layered project memory v2` — итоговый RFC-пакет.
2. `chore(memory): add schema validator and local boundaries` — M1.
3. `docs(memory): compile canonical knowledge and ADRs` — M2.
4. `feat(memory): add deterministic bootstrap and context packs` — M3 base.
5. `feat(memory): add shadow graph and code-vector retrieval` — M3 pilot.
6. `feat(agent): enforce memory preflight for Freebuff` — M4.
7. `docs(memory): freeze legacy session logs` — M5.
8. `ci(security): add staged deterministic scanners` — M6, лучше несколькими PR.

Не объединять M2 и M4: сначала retrieval должен доказать корректность, затем он становится gate.

## 6. Проверки на каждом PR

Минимум:

```bash
python -m tools.memoryctl lint
python -m tools.memoryctl facts --check
python -m tools.memoryctl test-fixtures
ruff check app/ cli.py tests/ seed_prod.py tools/
ruff format --check app/ cli.py tests/ seed_prod.py tools/
pytest tests/ -v --tb=short
alembic heads
```

Migration roundtrip и Docker build выполняются существующим CI. Если PR меняет только Markdown до
появления `memoryctl`, проверяются links, frontmatter examples, whitespace и отсутствие secrets.

## 7. Тестовый benchmark

Набор должен включать задачи:

- найти маршрут → handler → service → model → migration → tests;
- изменить exported symbol и найти все consumers;
- исправить day-boundary/timezone поведение;
- проверить LockTimer safety stop;
- оценить Social/Dynamics boundary;
- изменить LLM provider contract без чтения raw user data;
- выполнить UI изменение с локализацией и Playwright-проверкой;
- диагностировать Alembic head;
- найти superseded ADR;
- отличить roadmap item от реально реализованного факта;
- security review зависимостей;
- воспроизвести старую ошибку из Git без загрузки всего session log.

Для каждой задачи заранее фиксируются expected sources/symbols и запрещённые false positives.
Сравнение проводится одной версией агента и одинаковым prompt.

## 8. Риски и меры

| Риск | Мера |
|---|---|
| Wiki становится новой свалкой | Atomic pages, size lint, provenance, no session prose |
| Компилятор «придумывает» решение | Draft-only output; accepted только человеком |
| Граф устарел | HEAD-bound key; hard fail/rebuild |
| Vector search даёт убедительный шум | Authority hard filter; exact-source confirmation |
| MCP расширяет права | Per-agent profile, read-only default, pinned version |
| Hook обходят | Required CI и protected branch |
| Параллельный agent переписывает memory | Отдельные PR; sync перед M2/M5; stop при overlap |
| Public repo раскрывает личное | Raw local-only, denylist, secret/PII scan |
| Migration теряет ADR | Bidirectional coverage report и frozen source |
| Memory tooling блокирует разработку | Exact-search degraded mode; canonical files остаются читаемыми |

## 9. Definition of Done всей миграции

- стандартный Freebuff запускается через project agent и всегда создаёт свежий context pack;
- прямой commit без валидного preflight отклоняется локально и/или required CI;
- `DOCUMENTATION_MAP.md` остаётся непротиворечивой картой authority;
- active ADR/questions представлены атомарно и полностью;
- live facts генерируются и привязаны к HEAD;
- кодовый индекс локальный, воспроизводимый и не является источником истины;
- always-on context ≤ 10 KiB, task pack ≤ 12 KiB;
- новые raw sessions, secrets и user data не появляются в Git;
- старые агрегаты frozen и не входят в startup;
- benchmark показывает неухудшение recall и измеримое снижение лишнего чтения;
- CI, migrations и runtime tests остаются зелёными;
- rollback каждого слоя описан и проверен.

## 10. Решения владельца перед M1–M4

Нужно явно принять или отклонить:

1. Memory v2 и целевые лимиты 10/12 KiB.
2. Локальное хранение raw episodes с политикой retention.
3. Допустимость LLM compiler только для draft knowledge.
4. Пилот `codebase-memory-mcp` и его pinned version.
5. Qdrant local mode для shadow code-vector index и политика local-only embeddings.
6. Embedding profile после benchmark на русских запросах и Python/Jinja/JS коде.
7. Пилот QMD только для docs и только после baseline/BM25.
8. Required launcher + pre-commit/CI enforcement.
9. Момент freeze session logs после 10 параллельных сессий.
10. Набор security jobs и допустимый уровень false positives.
