# Practice Loop — контракт данных Memory v2

> Статус: RFC schema 0.2. Не применяется к legacy `memory/*` до миграции.  
> Формат примеров: YAML frontmatter + Markdown; generated facts/indexes/context pack используют JSON.  
> Все даты — ISO 8601 UTC, все Git revisions — полный SHA при машинной записи.

## 1. Общие правила

Каждый canonical Memory v2 документ:

- имеет глобально уникальный стабильный `id`;
- объявляет `kind`, `status`, `authority` и `scope`;
- содержит provenance до первичного источника;
- различает дату изменения текста и дату проверки факта;
- не становится authoritative только потому, что найден semantic search;
- не содержит секретов, raw user content или полной session transcript;
- при замене указывает `supersedes`, а заменённый документ — `superseded_by`;
- проходит `memoryctl lint` до merge.

## 2. Общий frontmatter

```yaml
---
schema_version: memory/v2alpha1
id: K-LOCKTIMER-SAFETY-STOP
kind: knowledge
title: Safety stop в LockTimer
status: active
authority: derived
owners:
  - project-owner
scope:
  - locktimer/core
applies_to:
  - app/locktimer/**
  - tests/locktimer/**
tags:
  - safety
  - state-machine
source_refs:
  - path: DOCUMENTATION_MAP.md
    anchor: Safety и privacy
    relation: defines
    ref: null
supersedes: []
superseded_by: null
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 0000000000000000000000000000000000000000
review_on: source-change
---
```

Нулевой SHA в примере — placeholder и запрещён validator в реальном active-файле.

### Обязательные поля

| Поле | Тип | Правило |
|---|---|---|
| `schema_version` | string | Для первой версии только `memory/v2alpha1` |
| `id` | string | Уникальный, неизменяемый после merge |
| `kind` | enum | Один из типов раздела 3 |
| `title` | string | Краткий, без статуса и даты |
| `status` | enum | Допустим для выбранного kind |
| `authority` | enum | Не наследуется автоматически от источника |
| `owners` | list[string] | Минимум один ответственный role/id |
| `scope` | list[string] | Минимум один нормализованный bounded scope |
| `source_refs` | list[object] | Может быть пуст только у draft question или local-only episode summary |
| `last_verified_at` | datetime/null | Обязателен для active/accepted |
| `last_verified_commit` | SHA/null | Обязателен для repo-derived active/accepted |
| `review_on` | enum/datetime | Событие или срок следующей проверки |

### Необязательные поля

`applies_to`, `tags`, `supersedes`, `superseded_by`, `aliases`, `security_classification`,
`expires_at`, `related_ids`. `review_on` принимает ISO date, `source-change`, `milestone:<id>` или
`never`; `never` допустим только для historical/archived content.

## 3. Допустимые типы и статусы

| `kind` | Назначение | Статусы |
|---|---|---|
| `contract` | Правила работы агента/области | `draft`, `active`, `superseded`, `archived` |
| `knowledge` | Устойчивое объяснение/ограничение | `draft`, `active`, `superseded`, `archived` |
| `adr` | Техническое или продуктовое решение | `proposed`, `accepted`, `rejected`, `superseded` |
| `question` | Требующее решения | `open`, `blocked`, `answered`, `cancelled` |
| `evidence` | Audit/test/research evidence | `current`, `stale`, `archived` |
| `episode_summary` | Sanitized итог сессии | `draft`, `reviewed`, `archived` |

Generated `fact_manifest`, `code_index_manifest`, `code_unit` и `context_pack` не являются
Markdown kinds и описаны отдельно.

### Authority

| Значение | Смысл |
|---|---|
| `normative` | Явно принятое продуктовое/safety решение |
| `technical` | Accepted ADR или действующий engineering contract |
| `factual` | Проверенный факт конкретного HEAD/run |
| `derived` | Сводка из других sources; никогда не сильнее их |
| `historical` | Контекст прошлого; не действует по умолчанию |

`authority: normative` разрешён только для accepted ADR/contract с явным owner approval и ссылкой
на нормативный источник. Agent-generated draft всегда `derived` или `technical` + `proposed`.

## 4. Идентификаторы

| Тип | Шаблон | Пример |
|---|---|---|
| Knowledge | `K-<SCOPE>-<SLUG>` | `K-LLM-PROVIDER-BOUNDARY` |
| Contract | `C-<SCOPE>-<SLUG>` | `C-ALEMBIC-SINGLE-HEAD` |
| ADR | Существующий формат `ADR-NNN` | `ADR-034` |
| Product question | Сохраняет текущий `PQ-NNN` | `PQ-006` |
| Engineering question | `EQ-NNNN` | `EQ-0001` |
| Evidence | `E-YYYYMMDD-<SLUG>` | `E-20260813-CI-MAIN` |
| Episode summary | `S-YYYYMMDD-<ULID>` | `S-20260813-01K...` |

Существующие ADR/PQ IDs при split не перенумеровываются. Filename может стать удобнее, но `id`
остаётся стабильным. Alias не может указывать на два active объекта.

## 5. Source reference

```yaml
source_refs:
  - path: PRODUCT_DECISIONS.md
    anchor: PD-017
    relation: defines
    ref: null
  - path: app/locktimer/services/session_service.py
    symbol: stop_session
    relation: implements
    ref: 0123456789abcdef0123456789abcdef01234567
  - path: tests/locktimer/test_session_service.py
    symbol: test_safety_stop_is_always_available
    relation: verifies
    ref: 0123456789abcdef0123456789abcdef01234567
```

Поля:

- `path` обязателен и должен быть repo-relative;
- ровно одно или ни одного из `anchor`/`symbol`;
- `relation`: `defines`, `supports`, `implements`, `verifies`, `refines`, `supersedes`, `origin`;
- `ref: null` означает «следить за текущей canonical веткой» только для normative documents;
- code/test/migration evidence в generated artifact всегда имеет полный `ref` и optional blob hash;
- URL допускается только как `external_url` вместе с названием и датой retrieval.

Нельзя ссылаться на semantic search result без исходного path/URL.

## 6. Knowledge page

Рекомендуемая структура после frontmatter:

```markdown
# Название

## Кратко

Два–пять предложений.

## Инварианты

- Проверяемые правила.

## Границы

- Что входит и явно не входит.

## Основные пути

- `path` — роль, без копирования исходника.

## Failure modes

- Типичная ошибка → как обнаружить.

## Проверка

- Команды или тесты.
```

Одна страница — одна тема. Целевой размер до 8 KiB; превышение 12 KiB требует split или явного lint
waiver. История изменений остаётся в Git, а не дописывается в body.

## 7. ADR

Дополнительные поля:

```yaml
decision_type: technical        # technical | product | safety | data
deciders:
  - project-owner
accepted_at: null
supersedes: []
superseded_by: null
```

Body:

1. Context — наблюдаемые условия, не пересказ сессии.
2. Decision — одно принятое решение.
3. Consequences — положительные, отрицательные и migration impact.
4. Alternatives — реально рассмотренные варианты.
5. Verification — как проверить соблюдение.
6. References — related IDs/paths.

Правила переходов:

```text
proposed -> accepted -> superseded
proposed -> rejected
```

Agent может создать `proposed`. `product`, `safety` и изменение scope требуют явного decider approval.
`accepted_at` и `deciders` нельзя заполнять по inference из кода или переписки без решения.

## 8. Active question

```yaml
schema_version: memory/v2alpha1
id: EQ-0001
kind: question
title: Нужен ли QMD после BM25 benchmark
status: open
authority: derived
owners:
  - project-owner
scope:
  - engineering/memory
blocking: milestone-M3
decision_deadline: null
options:
  - bm25-only
  - qmd-pilot
default_if_no_decision: null
source_refs:
  - path: MEMORY_IMPLEMENTATION_PLAN.md
    anchor: M3 — добавить retrieval и структурную память кода
    relation: origin
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 0000000000000000000000000000000000000000
review_on: milestone:M3
```

Вопрос без реального выбора не создаётся. Answered question получает `resolution_id` на ADR/decision,
после чего исключается из retrieval по умолчанию.

## 9. Generated fact manifest

`docs/state/FACTS.json` генерируется, форматируется стабильно и не редактируется вручную.
Повторный запуск на тех же inputs не меняет файл: `generated_at` сохраняется, если payload фактов
не изменился, либо берётся из воспроизводимого source event, а не обновляется от одного wall clock.

```json
{
  "schema_version": "memory/v2alpha1",
  "kind": "fact_manifest",
  "repository": "ghostcar/practice-loop",
  "generated_at": "2026-08-13T00:00:00Z",
  "generator_version": "0.1.0",
  "git": {
    "head": "0123456789abcdef0123456789abcdef01234567",
    "branch": "main",
    "dirty": false,
    "diff_hash": null
  },
  "alembic": {
    "heads": [],
    "command": "alembic heads",
    "checked_at": null
  },
  "tests": [],
  "ci": [],
  "artifacts": []
}
```

Test entry:

```json
{
  "command": "pytest tests/ -v --tb=short",
  "status": "passed",
  "passed": 610,
  "failed": 0,
  "skipped": 0,
  "started_at": "2026-08-13T00:00:00Z",
  "finished_at": "2026-08-13T00:01:00Z",
  "head": "0123456789abcdef0123456789abcdef01234567",
  "environment": "local-python-3.11"
}
```

Запись отсутствует, если команда не выполнялась. `status: passed` нельзя получить из Markdown,
commit message или количества в старом status. `NOW.md` всегда содержит generated banner и HEAD.

## 10. Context pack и sentinel

`.agent-runtime/context-pack.json`:

```json
{
  "schema_version": "memory/v2alpha1",
  "kind": "context_pack",
  "session_id": "01K...",
  "task_hash": "sha256:...",
  "created_at": "2026-08-13T00:00:00Z",
  "start_head": "0123456789abcdef0123456789abcdef01234567",
  "branch": "agent/example",
  "dirty": false,
  "mode": "normal",
  "classification": ["code", "locktimer/core", "safety"],
  "sources": [],
  "symbols": [],
  "impact_frontier": [],
  "risks": [],
  "required_checks": [],
  "excluded_paths": [],
  "size_bytes": 0,
  "status": "ready"
}
```

Source entry содержит `id` или `path`, `ref/hash`, `authority`, `status`, `reason`, `retriever` и
необязательные line/symbol hints. Pack не копирует длинные документы. `mode`:

- `normal` — все обязательные компоненты доступны;
- `degraded` — optional semantic/code graph недоступен, exact fallback успешен;
- `blocked` — stale HEAD, conflict, privacy/schema failure или unsafe overlap.

`.agent-runtime/session.json` — минимальный sentinel с `session_id`, `task_hash`, `start_head`,
`pack_hash`, `created_at`, `status`. Pre-commit требует `ready` или допустимый `degraded`, сверяет HEAD,
срок и pack hash. Runtime files всегда gitignored.

## 11. Episode summary

Raw transcript не имеет репозиторного schema и хранится локально. Sanitized summary может стать
candidate со структурой:

```yaml
schema_version: memory/v2alpha1
id: S-20260813-01K...
kind: episode_summary
title: Краткий технический итог
status: draft
authority: historical
owners: [agent]
scope: [engineering/memory]
start_commit: 0123456789abcdef0123456789abcdef01234567
end_commit: 89abcdef0123456789abcdef0123456789abcdef
changed_paths: []
checks: []
knowledge_candidates: []
adr_candidates: []
redaction_status: passed
source_refs: []
last_verified_at: 2026-08-13T00:00:00Z
last_verified_commit: 89abcdef0123456789abcdef0123456789abcdef
review_on: never
```

По умолчанию summary остаётся локальным. В Git публикуются сами устойчивые knowledge/ADR changes,
а не обязательная запись о каждой сессии.

## 12. Freshness

| Artifact | Freshness rule |
|---|---|
| `FACTS.json`, `NOW.md` | `artifact.head == git HEAD` и совпадает generator version |
| Code graph | Совпадают repo, HEAD, indexer version и ignore hash |
| Context pack | HEAD/task hash/pack hash совпадают; TTL не истёк |
| Accepted ADR | Действует до явного supersedes; source deletion вызывает lint error |
| Knowledge page | `source-change`, срок или изменение applies-to paths вызывает review |
| Evidence | Всегда привязано к run/commit; не переносится на другой HEAD автоматически |
| External source | Имеет `retrieved_at`; срок задаётся типом источника |

Новая commit после preflight не обязательно делает текущую рабочую сессию недействительной, если
это собственный linear commit. Однако получение/merge чужого commit требует пересборки impact pack.
Конкретное правило реализуется тестами, а не свободной интерпретацией агента.

## 13. Retrieval contract

Перед ранжированием применяются hard filters:

1. denylisted/security-classified source исключён;
2. `superseded`, `answered`, `archived`, `historical` исключены, если задача не про историю;
3. generated artifact другого HEAD marked stale и не используется как факт;
4. scope/path должен пересекаться с задачей либо быть mandatory contract;
5. conflict одинакового authority переводит pack в `blocked`.

Затем порядок сигналов:

1. mandatory safety/agent contract;
2. exact path/symbol/ADR ID;
3. applies-to и scope;
4. явные links и code graph adjacency;
5. lexical/BM25;
6. semantic similarity.

Числовые веса не фиксируются до benchmark, но каждый result обязан объяснить score components.
Embedding result без exact source reference не попадает в context pack.

## 14. Матрица разрешённых обновлений

| Объект | Agent генерирует | Agent публикует | Требуется человек |
|---|---:|---:|---|
| `FACTS.json`/`NOW.md` | Да, детерминированно | Да через `--check`/PR | Review обычного diff |
| Context pack/sentinel | Да | Нет, local-only | Нет |
| Code graph/index | Да | Нет, local-only | Нет |
| Knowledge draft | Да | Только как proposed PR | Review provenance/content |
| Technical ADR proposed | Да | Да как `proposed` | Acceptance decider |
| Product/safety ADR | Только draft | Не как accepted | Явное решение владельца |
| Active question | Да | Да, если выбор реален | Owner/decider для ответа |
| Raw episode | Да | Никогда | — |
| Legacy session log | Нет после freeze | Нет | Отдельное решение для исключения |

## 15. Privacy и index policy

### Allowlist по умолчанию

- `*.md` canonical docs после schema/size filter;
- `app/**/*.py`, `tests/**/*.py`, `alembic/**/*.py`;
- templates/static source, исключая generated/vendor/minified;
- конфигурация CI, Docker, dependencies и project tools;
- Git metadata, необходимая для diff/history, без auth config.

### Denylist по умолчанию

```text
.env*
.agent-runtime/**
.memory-local/**
uploads/**
examples/**
**/*.db
**/*.sqlite*
**/*.log
**/*dump*
**/*backup*
**/raw_llm_response*
app/static/fonts/**
app/static/**/tailwindcss.js
app/static/**/chart.umd.min.js
app/static/**/htmx.min.js
```

Ignore files могут расширять, но не ослаблять hard denylist без security ADR. Symlinks разрешаются
до проверки root; выход за repo root блокируется. Binary, minified и файл выше настроенного лимита
не отправляется embeddings/LLM.

## 16. Lint rules

`memoryctl lint` обязан проверять:

- schema и обязательные поля;
- уникальность IDs/aliases;
- допустимые kind/status/authority combinations;
- полный SHA в generated artifacts;
- существование paths, anchors/symbols где это возможно;
- dangling/cyclic `supersedes`, `related_ids`, `resolution_id`;
- соответствие `superseded_by` в обе стороны;
- наличие deciders/accepted_at у accepted ADR;
- запрет auto-accepted owner decisions;
- source refs для active derived pages;
- stale generated artifacts;
- size budgets и обоснованные waivers;
- denylist, symlink escape, secret patterns и подозрительные credentials;
- generated banner и стабильную сериализацию;
- отсутствие raw episode/context pack в tracked files.

Уровни:

- `error` — merge блокируется;
- `warning` — требует явного review/waiver;
- `info` — измерение, не влияет на exit code.

Waiver — отдельный небольшой YAML с owner, rule, reason и `expires_at`; бессрочные waivers запрещены.

## 17. Совместимость и эволюция

- `v2alpha1` допускает изменения только до первого active rollout;
- после rollout несовместимое изменение создаёт новый schema version и migration command;
- parser игнорирует неизвестное optional field, но отклоняет неизвестный `kind/status/authority`;
- generated files записываются атомарно и сортируются стабильно;
- legacy `memory/*` не обязаны соответствовать этой schema;
- compiler хранит mapping legacy ID → v2 ID для проверки полноты;
- schema и validator версионируются вместе, cache key включает обе версии.

## 18. Code index manifest и code unit

Полный retrieval contract находится в `CODE_MEMORY_DESIGN.md`. Здесь фиксируется минимальная
машинная форма. `.memory-local/code-index/manifest.json`:

```json
{
  "schema_version": "memory/v2alpha1",
  "kind": "code_index_manifest",
  "repository": "ghostcar/practice-loop",
  "worktree_id": "sha256:...",
  "head": "0123456789abcdef0123456789abcdef01234567",
  "indexer_version": "0.1.0",
  "parser_profile": "python-ast+tree-sitter-v1",
  "embedding_profile": {
    "provider": "local",
    "model": "candidate-model",
    "revision": "pinned-revision",
    "dimensions": 768,
    "normalization": "l2"
  },
  "ignore_hash": "sha256:...",
  "collection": "practice_loop_code_v1",
  "unit_count": 0,
  "indexed_at": "2026-08-13T00:00:00Z",
  "status": "ready"
}
```

Каждая индексируемая единица до embedding имеет canonical record:

```json
{
  "schema_version": "memory/v2alpha1",
  "kind": "code_unit",
  "id": "sha256:path+symbol+content-hash",
  "path": "app/example.py",
  "blob_sha": "0123456789abcdef0123456789abcdef01234567",
  "language": "python",
  "unit_kind": "function",
  "symbol": "package.module.function",
  "parent_symbol": "package.module",
  "start_line": 10,
  "end_line": 42,
  "content_hash": "sha256:...",
  "scope": ["personal/core"],
  "flags": ["source"],
  "retrieval_text_hash": "sha256:..."
}
```

Допустимые `unit_kind`: `module`, `class`, `function`, `method`, `route`, `model`, `migration`,
`template_block`, `javascript_function`, `test`, `config_section`. Большая единица делится только
по вложенным AST boundaries с `parent_symbol`; overlap фиксирован и детерминирован.

Qdrant payload содержит record без исходного body, плюс scalar fields для filters. Сам vector и
локальный retrieval text не коммитятся. Manifest обязан совпадать с текущим worktree HEAD, parser,
embedding revision и ignore hash; иначе index имеет status `stale` и не участвует в retrieval.

Validator дополнительно проверяет:

- line span и symbol существуют в указанном blob;
- unit ID воспроизводим из canonical inputs;
- generated/vendor/denied paths отсутствуют;
- удалённые/переименованные paths удалены после incremental update;
- смена embedding dimensions/revision создаёт новую collection;
- vector candidate в final context pack имеет exact `path`, `symbol`, `blob_sha` и confirmation mode.
