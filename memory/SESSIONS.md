## 2026-08-14 — Сессия 119b (Шаг 2 — LLM/media границы, весь личный контур)

- **Контекст**: личный контур = вся платформа (задачи, тренировки, диеты, точки, медиа, LLM-пайплайн, Telegram), не только Tracker+Timer. Шаг 2 из STAGE_PLAN закрывает три пункта аудита 2026-08-13:
- **P1-2 — weekly planner усилен** (`generate_weekly_tasks`): exact dates (только из запрошенного target-множества), уникальность (ровно одна задача на день), полнота (все requested days покрыты), entity ∈ allowed-набор + params валидны; **атомарный save** — при любом невалидном item весь план отклоняется (ValueError → UI redirect generation_failed), ничего не пишется (раньше невалидные молча skip'ались → частичный план). Промпт явно указывает допустимые даты.
- **P1-3 — media finalize owner-target check**: новый `app/services/media_registry.py` — registry owner-типов с `authorize_bind(db, owner_type, ref_id, user_id)` для всех 10 owner_type (activity_log, training_day, training_log_entry, inventory_item, diet, measurement, lock_session, lock_slot_occurrence, lock_task_occurrence, social_publication). `finalize_media` проверяет существование + принадлежность target (404 при чужом/отсутствующем), а не только владельца asset.
- **P1-7 — единый источник версии**: `app/version.py` (__version__ = 0.8.0) → FastAPI metadata + export full header (было 0.9.0 / 0.5.0 / 0.8.0 в трёх местах). pyproject/README уже 0.8.0 — синхронизированы.
- **Тесты**: `tests/test_audit_gateb.py` — 12 тестов (weekly: happy path, date outside, duplicate, incomplete, non-allowed entity, invalid params; media: own-ok, foreign-404, missing-404; version: pyproject match, FastAPI match, export match).
- **Проверки**: 755/755 ✅ (+12), ruff ✅, format ✅.

## 2026-08-14 — Сессия 119 (границы LLM для личного контура — ADR-070; Шаг 1 Gate A)

- **Стратегия владельца**: личный контур — первая очередь; социальные/общедоступные функции — вторая очередь (зафиксировано в STAGE_PLAN.md). LLM в личном контуре — полностью: Omniroute первым источником, подбор моделей, harness, инструменты.
- **Интервью по границам LLM → ADR-070** (расширение ADR-030/034):
  1. Гибрид сохраняется (каталог + opt-in), режим названий per-provider через llm_mode (full/abstract — уже реализован);
  2. Параметрическая генерация через промпт-шаблоны (пользователь создаёт шаблон с параметрами, сохраняет, LLM генерирует по нему);
  3. LLM-верификация медиа — истина в последней инстанции для соло-игр (подтверждение кодов, закрытие пояса верности; Q13 без OCR);
  4. Приватная база знаний LLM для промптов (векторный индекс + Omniroute-эмбеддинги);
  5. Библиотека типовых промптов по функциональным блокам.
  Комплаенс-красная линия не снимается: никакого обхода safety-фильтров провайдеров и маскирования контента (ToS + блокировка ключа Omniroute/upstream). Реализация — шаги 6–7 STAGE_PLAN.
- **STAGE_PLAN.md**: добавлены шаги 6 (LLM harness: типовые промпты, промпт-шаблоны, приватная KB) и 7 (LLM-верификация медиа) + секция решения ADR-070.
- **Шаг 1 — Gate A остаток (безопасность, малые)**:
  - P1-1: innerHTML убран из locktimer/session_detail.html (validate-баннер строится через textContent/createElement) + XSS regression тесты (шаблон без innerHTML; validate возвращает payload как plain strings);
  - P2-3: /healthz/readiness больше не раскрывает str(exc) — клиенту «not ready», детали в server log (logger.warning exc_info);
  - P1-6: security headers middleware — nosniff, X-Frame-Options DENY, Referrer-Policy strict-origin-when-cross-origin, Permissions-Policy (camera/mic/geolocation off), HSTS на https, CSP report-only (enforcing — на Gate C);
  - tests/test_audit_gatea.py — 6 тестов.
- **Проверки**: 743/743 ✅ (+6), ruff ✅, format ✅.

## 2026-08-14 — Сессия 118b (реальный A/B вектор-пилота через Omniroute — ADR-069 amended)

- **Решение владельца (в ходе прогона)**: это VPS с ограниченными ресурсами — локальные модели не запускать; для LLM-нужд использовать Omniroute (локальный LLM-прокси на том же хосте, ~2800 моделей, 47 embedding). В .env добавлены `OMNIROUTE_HOST=llm.gorbunovr.ru` и `OMNIROUTE_API_KEY` — эти же параметры позже будут использоваться порталом.
- **Провал локального подхода**: BGE-M3 не поддерживается fastembed нативно (qdrant/fastembed#348 — патч); multilingual-e5-large (2.24 ГБ fp32) OOM-нула 15 ГБ RAM на единственном batch-прогоне (процесс убит, индекс не записан). Локальные модели на этом VPS невозможны.
- **Переключение на Omniroute**: `Embedder` переписан на remote `/v1/embeddings` (OpenAI-compatible, httpx); модель `openrouter/openai/text-embedding-3-small` (1536-dim, мультиязычная RU→EN, ~$0.02/1M токенов). Проверено на проде: работает. Qdrant остаётся локальным (лёгкое хранилище, не модель). fastembed/onnxruntime удалены из optional-группы `memory` (pyproject) и деинсталлированы; numpy остался (транзитивная зависимость, не используется кодом).
- **Реальный A/B** (`index-code --mode full` + `benchmark --vectors`): индекс 2167 units ≈ 4 мин, ~$0.01. **recall@5 0.24 → 0.37 (+0.13), MRR 0.356 → 0.496 (+0.14), pack ≤12 KiB, 0 forbidden.** Прирост именно на RU→EN задачах (T3 границы суток, T4 safety-stop, T5 social/D-s, T8 alembic-head); T6/T10/T11 остались ≈0 (semantic не покрывает: raw_llm_response, OCR, «почему 500 на Postgres»). Ни одного негативного delta. Gate STAGE_PLAN пройден → **пилот admit (shadow/assist)**.
- **ADR-069 amended**: строка таблицы + секция (embedding через Omniroute вместо BGE-M3), `adr compile` → 69 docs/adr/ + bidirectional check 69==69.
- **Тесты**: +3 (omniroute_settings из .env, env-override, blocked без конфига); 32/32 memory-таргетных ✅. Полный suite — перегоняю повторно.

## 2026-08-13 — Сессия 118 (M3 вектор-пилот по ADR-069)

- **Реализация вектор-пилота** (остаток Этапа 2, ADR-069) — код полностью готов, реальный A/B-прогон отложен (нужны optional `memory` deps + скачивание BGE-M3):
  - `tools/memoryctl/code_units.py` — stdlib-only структурный парсер code units (CODE_MEMORY_DESIGN.md §4): Python через `ast` (module/class/function/method/route/FastAPI `@router`/SQLAlchemy `__tablename__`/fixture/test), Alembic revision (`revision`/`down_revision` + upgrade/downgrade span), Jinja2 block/macro/form, JS handler/arrow/fetch, YAML/TOML section. Scope-деривация по префиксу пути; content-addressed `content_hash` (sha256 path+span+retrieval).
  - `tools/memoryctl/vectors.py` — lazy Qdrant-local + fastembed backend: `EMBEDDING_PROFILE` (BGE-M3, 1024-dim, normalization, RU/EN), `index_code` (extract→embed→upsert→HEAD-bound manifest, режимы full/check), `search_code` (dense ANN + лексический floor → клиентский RRF fusion + exact confirmation по content_hash), `is_available` graceful degradation.
  - `benchmark.py` — A/B: `score_ranked`, `evaluate_vectors`, `run_vectors_ab`; флаг `benchmark --vectors`; graceful «vectors unavailable»; `render_summary` показывает delta vs baseline.
  - `__main__.py` — subcommands `index-code` / `search-code` (lazy import, чёткий exit при недоступных deps).
  - `pyproject.toml` — optional dev-group `memory` (qdrant-client, fastembed, onnxruntime) изолирован от рантайма FastAPI (ADR-069).
- **Тесты**: `test_code_units.py` (13) + `test_vectors.py` (11) + A/B shape в `test_benchmark.py` (2). Полный suite **734/734 ✅** (+25), ruff ✅, format ✅.
- **Gate (открыт)**: реальный A/B (recall@5/MRR vs baseline 0.26/0.356, pack ≤12 KiB) требует `pip install -e '.[memory]'` + скачивание BGE-M3 в `.memory-local/` — решение admit/shadow/off после прогона (STAGE_PLAN Этап 2).

## 2026-08-13 — Сессия 117 (M4 preflight — Этап 3)

- **Этап 3 (M4 preflight)** выполнен — сделать preflight обязательным для поддерживаемого workflow:
  - `tools/memoryctl/sentinel.py` + CLI `memoryctl sentinel [--ttl-hours N]`: проверка свежего preflight — `kind=session_sentinel`, `status ∈ {ready,degraded}`, `start_head` — предок/равен HEAD (линейный commit агента не инвалидирует, расхождение — fail), `pack_hash` = sha256(байт pack) (integrity), опциональный TTL. Fail-closed.
  - `tools/memoryctl/impact.py` + CLI `memoryctl impact` (advisory, rail 5): changed paths (git status porcelain) vs `impact_frontier` последнего pack; код вне frontier → `out_of_scope` (сигнал перезапустить bootstrap), новые файлы — `new_files`, docs/config — всегда in-scope.
  - `bin/practice-agent` — launcher: `memoryctl bootstrap` → отказ без ready-sentinel → `exec` агента (PRACTICE_AGENT_BIN, default freebuff).
  - `.agents/skills/project-memory/SKILL.md` — единый workflow (preflight → read-don't-trust → impact → pre-commit → close), kind=contract id=C-ENGINEERING-MEMORY.
  - `.githooks/pre-commit` (opt-in: `git config core.hooksPath .githooks`) — блокирует code-commit без свежего sentinel; docs/memory-only commit проходит; bypass `--no-verify`.
  - RUNBOOK.md §12 — как пользоваться; STAGE_PLAN.md — Этап 3 отмечен.
- **Багфикс в bootstrap.py**: `write_sentinel` считал `pack_hash` без trailing newline, а `write_pack` писал с ним → integrity-проверка всегда падала. Вынесен единый `_serialize_pack()` (байты записи == байты хэша).
- **Тесты**: `test_sentinel.py` (6) + `test_impact.py` (5) — git-repo fixture, ok/stale/bad-status/pack-mismatch/TTL + classification. Полный suite **709/709 ✅** (+11), ruff ✅, format ✅.
- **Отложено (зафиксировано в STAGE_PLAN)**: `.agents/practice-loop.ts` (требует pinned Freebuff SDK), `.agents/mcp.json` (MCP не подключён, M6), required CI memory-lint (после периода наблюдения), M5 freeze legacy-логов (после 10 сессий).

## 2026-08-13 — Сессия 116 (решение по M3 пилотам — ADR-069)

- **Решение владельца по M3 пилотам** (после baseline recall@5 0.26 из Сессии 115), зафиксировано **ADR-069**:
  - **embedding**: BGE-M3 (multilingual, dense+sparse в одной модели, ONNX через fastembed, local-only) — закрывает доминирующий зазор RU→EN (code-specific его не решает).
  - **пилот**: только Qdrant local vectors (shadow mode) — единственный; QMD (docs) и codebase-memory-mcp (graph) отложены до доказательства нехватки.
  - code-specific второй named-вектор — только если BGE-M3 окажется слаб на коде.
  - зависимости (qdrant-client, fastembed/onnxruntime) — только optional dev-group, рантайм FastAPI не трогается; веса модели в `.memory-local/`.
- **RFC-контекст**: BGE-M3 — open-weight лидер multilingual (100+ языков, dense+sparse+multi-vector), подтверждено web-поиском; Qdrant local + fastembed — официальный путь hybrid search (dense+sparse), local-mode hybrid может требовать клиентской fusion (как и предписывает RFC §3/§8).
- **ADR-069**: добавлена строка в таблицу + секция в DECISIONS.md; `memoryctl adr compile` → 69 docs/adr/ + README; bidirectional check 69==69 ✅.
- **STAGE_PLAN.md**: Этап 2 дополнен — benchmark ✅, baseline ✅, решение ✅; следующее — реализация `index-code` + `search-code` + A/B.
- **Следующий шаг (Этап 2, остаток)**: реализовать пилот (структурные code units + hybrid dense+sparse + A/B против baseline), gate = прирост recall@5/MRR при pack ≤12 KiB.

## 2026-08-13 — Сессия 115 (Memory v2 M3 benchmark — harness + baseline)

- **Этап 2 (M3 benchmark)** выполнен: `tools/memoryctl/benchmark.py` — harness по 12 задачам из `docs/memory-rfc/BENCHMARK_TASKS.md` с machine-readable ground truth (expected_code / expected_docs / forbidden, glob-паттерны).
- **Метрики**: recall@5 (code), recall (code/docs/all), MRR, размер pack (детерминированный, лимит 12 KiB), extra reads, forbidden hits; пороги допуска из RFC §7/§12.
- **Отчёт**: `docs/state/BENCHMARK.json` (HEAD-bound, детерминированный: session_id + head-anchored now) + CLI `memoryctl benchmark [--json]`.
- **Baseline (M3 base exact/lexical, честный замер)**:
  - recall@5 (code) = **0.26** (порог 0.9); recall code/docs/all = 0.51 / 0.58 / 0.38; MRR = 0.356.
  - pack median/max = 7.7 / 9.0 KiB (< 12 ✅); forbidden hits = 0 ✅.
  - Главный вывод: **лексический fallback находит код по английским символам (T1/T2/T4/T6/T12), но ~0 recall на чисто русских запросах к англ. коду (T3/T8/T10)** — ровно тот зазор, под который RFC закладывает semantic/vector-поиск.
  - Docs-recall ограничен границей L0/L1: legacy-доки (PRODUCT_DECISIONS.md, memory/DECISIONS.md, OPEN_QUESTIONS.md, CURRENT_STATE.md, alembic.ini) вне корпуса (M5-split) и вне scope search_code.
- **Нюанс ground truth (T2)**: спек закладывает `app/timeutils.py` + `tests/test_timeutils.py` как потребителей `list_sessions_by_date_range`, но они держат `local_day_bounds` (зависимость, не consumer); все 3 literal-потребителя найдены — зафиксировано в `notes`.
- **Тесты**: `tests/memory/test_benchmark.py` — 4/4 (pattern-matching, evaluate_task code/forbidden+docs, структура + детерминированность отчёта). Полный suite **698/698 ✅** (+4), ruff ✅, format ✅.

## 2026-08-13 — Сессия 114 (Memory v2 M3 base — memoryctl bootstrap + план на 3 этапа)

- **План работ на 3 этапа вперёд** зафиксирован в `docs/memory-rfc/STAGE_PLAN.md` (по запросу владельца — чтобы не прыгать): Этап 1 = M3 base (эта сессия), Этап 2 = M3 benchmark + пилоты (Qdrant/vectors/graph — только с доказательством, решение по embedding/пилотам у владельца), Этап 3 = M4 preflight (SKILL.md + practice-agent launcher + sentinel CI). Параллельно (не в плане) — P1/Gate B–D аудита.
- **M3 base — `tools/memoryctl/bootstrap.py`** (stdlib-only, детерминированный exact-fallback, MEMORY_ARCHITECTURE.md §7):
  - `classify_task` — детерминированные эвристики → classes (security/data/ui/deploy/product/fact/code) + scopes (locktimer/social/llm/tracker/platform-*/tests/engineering-memory).
  - `collect_docs` — L0 always-on (AGENTS.md + knowledge.md root/domain, scope-filtered) + L1 (docs/adr, docs/wiki, docs/questions) по scope + keyword + symbol scoring; exclude superseded/answered/archived/cancelled.
  - `search_code` — exact/lexical поиск по app/tests/alembic (symbols×3 + terms×1).
  - `build_impact_frontier` — тесты/миграции/call sites для топ-символов.
  - `risks`/`required_checks` — по scope/class (safety stop, EQ-0014, moderation gate, no safety bypass, CHALLENGE_HMAC_KEY, single Alembic head…).
  - `bootstrap`/`write_pack`/`write_sentinel` — context pack + sentinel в `.agent-runtime/` (references only, не копирует тела; pack ~6–8 KiB < лимита 12).
- **CLI**: `python -m tools.memoryctl bootstrap --task "..." [--runtime-dir DIR] [--session-id ID] [--limit N]`; сводка mode/head/classification/sources/risks/checks.
- **Тесты**: `tests/memory/test_bootstrap.py` — 13/13 (classification/dedupe/root-always-on/impact-frontier/checks/determinism/pack-size/sentinel). Полный suite **694/694 ✅** (+13), ruff ✅, format ✅.
- **Фикс ревью**: `_doc_reason` — keyword-reason теперь считает по body, а не только title (раньше `meta.get("body")` = frontmatter → всегда пусто).

## 2026-08-13 — Сессия 113 (аудит P0-1 + P0-2 — Gate A блокеры)

- **P0-1 (приватный /uploads)**: удалён публичный `StaticFiles` mount `/uploads` в `app/main.py`. Новый авторизованный `GET /uploads/{path:path}` (`app/api/uploads.py`): auth (cookie JWT) + owner reverse-lookup (Attachment.file_path / InventoryItem.image_path / MediaAsset.file_path|thumbnail_path) + hard containment (traversal/absolute/backslash → 404). Аноним → 401, cross-user/несуществующий → 404 (без утечки существования). Universal media по-прежнему дублируется `/api/v2/media/{id}` (уже был авторизован).
- **P0-2 (CHALLENGE_HMAC_KEY fallback)**: убран `default-challenge-key` fallback в `compute_code_hmac` (пустой ключ → RuntimeError fail-closed). Отдельный placeholder `_PLACEHOLDER_CHALLENGE` + добавлен в production gate `_reject_placeholders_in_production` (пустой/placeholder/<32 → startup fail).
- **Доки**: `.env.example` + `RUNBOOK.md` — `CHALLENGE_HMAC_KEY` обязателен (отдельный от JWT/ENCRYPTION).
- **Тесты**: `tests/test_upload_serving.py` (11: containment 5 + API owner/cross-user/anon/missing 6) + 2 config-теста challenge-gate. **681/681 ✅**, ruff ✅.
- **⚠️ Дефолт**: следующий `docker compose up` на VPS упадёт на startup, пока в `.env` не задан `CHALLENGE_HMAC_KEY` (≥32 chars). Смена ключа инвалидирует активные challenges (короткий TTL — приемлемо).

## 2026-08-13 — Сессия 112 (Memory v2 M2 — полный gate + P2-4)

- **P2-4 (аудит)**: разделил index-denylist и secret-denylist. `DENYLIST_GLOBS` (index, исправлены мёртвые minified-глобы `app/static/**/htmx.min.js` → `app/static/htmx.min.js` на реальные плоские пути); новый `SECRET_DENYLIST_GLOBS` (настоящие секреты/приватные данные) + `ALLOWLIST_GLOBS` (`.env.example` с provenance). `memoryctl lint` сходится к **0 warnings** (было 3: .env.example + 2 Inter-шрифта).
- **ADR-компилятор** `tools/memoryctl/adr.py`: `adr compile` (split `memory/DECISIONS.md` → 68 файлов `docs/adr/ADR-NNN.md` + `README.md`) и `adr check` (двусторонняя сверка legacy == generated). Исправлен парсер таблицы: pipe внутри решения ADR-048 (`tracker|timer|combined`). decision_type: product/safety/technical (эвристика, human-refine); статусы принято→accepted, отложено→proposed (ADR-012/013/019).
- **L0**: `knowledge.md` (root, C-PRACTICE-LOOP) + 5 domain-local (`app/locktimer/`, `app/platform/social/`, `app/llm/`, `alembic/`, `tests/` — kind contract, C-*).
- **L1**: `docs/questions/` PQ-005 (оплата), PQ-006 (рейт-лимиты), EQ-0013 (OCR), EQ-0014 (penalty HTTP); `docs/wiki/` 5 страниц (K-SAFETY-HYBRID-GENERATION, K-LOCKTIMER-SAFETY-STOP, K-DEVICE-TZ-BUCKETS, K-PERSONAL-FIRST, K-TRACKER-STATUS-MACHINE).
- **Проверка**: 669/669 ✅ (45 memory), ruff ✅, `adr check` 68==68 ✅, `lint` 0 errors/0 warnings (до регенерации facts).

## 2026-08-13 — Сессия 110 (Memory v2 M0+M1)

- **Встроена Memory v2-архитектура (RFC от владельца, examples/LT/memory)**: принято владельцем M0 + M1 (ADR-068, accepted), без freeze legacy memory/.
- **M0**: RFC-файлы → `docs/memory-rfc/` (5 файлов + BENCHMARK_TASKS.md — 12 benchmark-задач на реальных путях), ADR-068 (принято), строка в DOCUMENTATION_MAP.md, дозаполнена таблица ADR-061…068 в DECISIONS.md (таблица отставала от секций).
- **M1**: `tools/memoryctl` (stdlib-only): schemas.py (frontmatter-subset парсер + валидация), facts.py (FACTS.json + NOW.md, детерминированные, якорь = последний коммит НЕ трогающий docs/state), inventory.py, lint.py (denylist/секреты/stale-facts/размеры/дубликаты id), __main__.py CLI.
- **Тесты**: 37/37 в tests/memory/ (schemas/facts/lint/inventory). Полный suite **661/661 ✅**, ruff ✅, format ✅.
- **Инфраструктура**: .gitignore (+.agent-runtime/, .memory-local/), .codebuffignore/.cbmignore, docs/state/ сгенерирован, CI job `memory-lint` (informational, continue-on-error).
- **Code review** (deepseek-flash): применены все фиксы — dead code parse_size_limit, типизация frontmatter_raw, int с ведущими нулями, скаляр с ':' в списках, dir-relative резолв ссылок в inventory, порядок validate-then-add в lint, якорная дата generated_at/checked_at.
- Финальная валидация: 661/661 ✅, 37/37 memory ✅, facts fresh, lint 0 errors/3 warnings (ожидаемые denylist: .env.example + Inter-шрифты), inventory baseline: 68 ADR, 12 benchmark-задач, 0 dangling refs.

## 2026-08-13 — Сессия 109 (чекпоинт перед перерывом)

- **Чекпоинт зафиксирован**: `memory/CHECKPOINT_S108.md` — сделано / осталось / не делали + с чего продолжить. Краткий перерыв на сервисные задачи.
- Ключевое для продолжения: 3 незапушенных коммита (S107–S108); долги Q14 (penalty не в HTTP), on-time slot open UX, Q13 (OCR); allowlist на проде пуст; S8 keyholder / публичный доступ — после личного контура.

## 2026-08-13 — Сессия 108 (prod timer smoke + фикс open слота)

- **Smoke активной таймер-сессии на проде** (tracker.gorbunovr.ru): throwaway-юзер → draft → tz=UTC → slot-rule (every_n_days, future time_of_day, allow_late_open, max_late_seconds=3600) + 2 task-rule (daily) → validate (valid=True, ~89 slots/178 tasks) → start → probe open до окна (409 expected) → open → close с биркой SMOKE-001 → verify-tag match/mismatch (violation) → task reveal/complete/skip → safety-stop → негативные (extend-horizon 409, open после stop 409) → overview/calendar 200.
- **Найден баг**: `POST /slot-occurrences/{id}/open` всегда 409 на проде — `api_add_slot_rule` игнорировал `max_late_seconds` (Form-поля не было) → `eligible_until == planned_open` (окно open = 0 сек) → ни один real-time запрос не может открыть слот (на SQLite-тестах не видно: сервисные тесты передают точное время). UI-чекбокс «Allow late open» был мёртвым.
- **Фикс**: `api_add_slot_rule` принимает `max_late_seconds: int = Form(default=3600)` и пробрасывает в `add_slot_rule`; в форму session_detail добавлен инпут «Late window (sec)» (default 3600); i18n en/ru (`locktimer_max_late_seconds`). Редеплой + повторный smoke: **0 фейлов** — DB-проверка: slot closed c SMOKE-001, 1 completed + 1 skipped, 1 violation, session safety_stopped.
- **Долг (Q14)**: LockTimer penalty не проброшен в HTTP — `apply_penalty` (ADD_TIME/BLOCK_NEXT_SLOT/MARK_TASK_FAILED/POINTS, idempotency, cap max_end_at) не вызывается нигде в app (LLM-tool apply_penalty — трекер-домен); UI «Skip this task? Penalty may apply» вводит в заблуждение.
- Чистка: 4 smoke-юзера удалены (0 осталось, owner цел). 624/624 ✅, ruff ✅, 33/33 locktimer ✅.

## 2026-08-13 — Сессия 107 (prod front smoke + фикс 500 на /locktimer)

- **Smoke-тест прода (tracker.gorbunovr.ru через nginx)**: регистрация+логин временного юзера, обход 22 страниц, charts/balance JSON, статика, POST /locktimer/new (черновик) — Chrome на VPS нет, поэтому curl+urllib с cookie-jar (Secure-cookie работает через HTTPS-домен).
- **Найден и исправлен баг**: `GET /locktimer` и `GET /locktimer/calendar` → 500 на Postgres: `operator does not exist: timestamp with time zone <= character varying` — `list_sessions_by_date_range` сравнивал timestamptz-колонки (`started_at`/`effective_end_at`) с ISO date-строками (asyncpg биндит str как VARCHAR). SQLite (тесты) был снисходителен — 619 тестов проходили.
- **Фикс**: новый `app.timeutils.local_day_bounds(day)` → [start, next-day-00:00) как aware UTC (client_tz ContextVar, UTC-фолбэк, как local_today/local_date); `list_sessions_by_date_range` парсит `date.fromisoformat` и сравнивает `started_at < end_utc` / `effective_end_at >= start_utc`. Семантика стала корректнее: старый `<= end_date`-строками неявно исключал всё после полуночи последнего дня.
- **Тесты**: +5 (3 в test_locktimer_services.py: overlap/wide-range/tz-bucketing 16:30 UTC = 08-06 Tokyo; 2 в test_timeutils.py: local_day_bounds UTC+Tokyo). **624/624 ✅**.
- **Повторный smoke после деплоя: 0 фейлов** — все 22 страницы 200 (включая /locktimer, /locktimer/calendar, /locktimer/templates, /api/v2/measurements/page, /api/v2/inventory/page, /api/v2/schedule/page, /entities/my). 4 «фейла» первого прогона были неверными URL теста (страницы живут под /api/v2, my-entities → /entities/my), не багами. Admin → 403 ожидаемо.
- **Очистка**: оба smoke-юзера удалены из БД (cascade lock_*), владелец цел (1 юзер).

## 2026-08-13 — Сессия 106 (деплой правок S103 на VPS)

- **`docker compose up -d --build`**: образ пересобран, контейнер app пересоздан и поднят; `healthz` 200 ok, `readiness` ready, контейнеры healthy (app + db).
- В проде теперь: форматирование alembic-миграций + locktimer_ui.py (косметика, поведение идентично) и фикс pre_deploy_check.sh.
- Лог старта чистый (только pre-existing pydantic warning про protected namespace `model_name`).

## 2026-08-13 — Сессия 105 (финальный счётчик тестов)

- **Полный `pytest tests/`**: **619/619 ✅** (284s) — подтверждён после всех правок S97–S104 (tz, графики, доки, форматирование, pre_deploy_check). Изменений кода в S103–S104 не было, счётчик не изменился.

## 2026-08-13 — Сессия 104 (сверка §17 social-таблиц)

- **FUNCTIONAL.md §17**: список social-таблиц сверен с `app/platform/social/models.py` — 15/15 совпадает (MISSING none, EXTRA none; единственный «лишний» — слово `social_` из заголовка). Поправлен заголовок: «все с префиксом social_» → «в app/platform/social/models.py, 15 шт.», moderation_* вынесены отдельно (у них нет префикса social_).
- Docs-only, тесты не трогались.

## 2026-08-13 — Сессия 103 (pre_deploy_check зелёный после tz/рефакторинга)

- **`./pre_deploy_check.sh`** — полный прогон: [1/8] git warning (незакоммиченные правки) → [2/8] 619/619 ✅ → [3/8] ruff check + format чистые (весь репо) ✅ → [4/8] секретов нет ✅ → [5/8] .env OK ✅ → [6/8] docker build ✅ → [7/8] единый alembic head ✅ → [8/8] social privacy audit ✅. Вердикт: **Ready to deploy**.
- **Найден и устранён долг**: `ruff check .` падал на 10 ошибках в alembic-миграциях (7×I001 импорты, 3×E501 длинные строки в 030/032) + 2 файла не отформатированы (028, locktimer_ui.py). Исправлено: `ruff check --fix alembic/versions/` + ручные wrap 3 строк + `ruff format` 2 файлов — всё косметика, DDL не тронут (проверено diff + alembic single head).
- **pre_deploy_check.sh**: путь `app/platform/social/api.py` → `app/platform/social/api/` (после рефакторинга S87 файл стал пакетом — grep давал «No such file»); фильтры `strip`/`expose` → case-insensitive `-i` (false-positive на docstring «Strips: raw_llm_response…» в adapters.py).
- Тесты: 619/619 ✅, ruff ✅, format ✅.

## 2026-08-13 — Сессия 102 (тест category-breakdown)

- **`tests/test_charts_tz.py`**: +1 тест `test_category_breakdown_groups_by_category` — покрывает 5-й chart-эндпоинт (группировка по Entity.category, не day-bucketed): 2 entities (cardio×2, strength×1), проверка labels/values/total (count desc).
- Тест-only, ruff ✅, 6/6 в файле.

## 2026-08-13 — Сессия 101 (документация TG_AUTO_ANALYSIS_TZ)

- **`.env.example`**: добавлен `TG_AUTO_ANALYSIS_TZ` (IANA, default UTC), убран жёсткий «UTC» из комментария `TG_AUTO_ANALYSIS_TIME`.
- **`README.md`**: строка `TG_AUTO_ANALYSIS_TZ` в env-таблице; `TG_AUTO_ANALYSIS_TIME` — «HH:MM» без «UTC».
- **`RUNBOOK.md`**: пункт в §1 pre-deploy checklist.
- **`DEPLOY_VPS.md`**: строки `TG_AUTO_ANALYSIS_TIME`/`TG_AUTO_ANALYSIS_TZ` в шпаргалке env-ключей.
- Docs-only, тесты не трогались.

## 2026-08-13 — Сессия 100 (полный список таблиц в FUNCTIONAL.md §15)

- **FUNCTIONAL.md §15** переписан: полный перечень 54 таблиц `app/models/*` (проверено скриптом: 54/54, без пропусков и лишних). Исправлен typo `user_entity_opt_in`→`user_entity_opt_ins`, раскрыт `diet*` (5 таблиц), добавлены справочные/link-таблицы update2.md (8) и lock_* (14).
- Тесты не трогались.

## 2026-08-13 — Сессия 99 (сверка FUNCTIONAL.md / PRODUCT.md с текущим состоянием)

- **FUNCTIONAL.md**: §1 — добавлены Lock Timer + Social; §2 — i18n 403→687 ключей, строки «Время» и «API» (всё под `/api/v2`); §4 — `category_id` FK → `activity_categories` (16 категорий) + `penalty_enabled`; §6 — статус-машина 11 состояний (ADR-040); §15 — добавлены `activity_categories`, `activity_task_history`; §16 — честная терминология «Lock Timer (chastity, ADR-062)»; **новый §19 «Дата и время»** + §20 «Реализованные решения и направление развития» (ADR-035…042 ✅, направление: ADR-063/064/065 + Q13 OCR).
- **PRODUCT.md**: дата обновления; «Таймер самодисциплины» → «Таймер замка (Lock Timer, chastity)»; подраздел «Время и часовые пояса»; строки в таблице готовности (tz устройства, рефакторинг API v2).
- Свип устаревших терминов — чисто. Тесты не трогались (618/618).

## 2026-08-13 — Сессия 98 (тесты chart-эндпоинтов: device-tz бакетирование)

- **`tests/test_charts_tz.py`** (новый, 5 тестов): проверка, что 4 daily-series эндпоинта (activity/points-trend/xp-history/completion-rate) бакетируют по device-календарному дню, а не по UTC-дню БД.
- **Freeze-фикстура** `freeze_clock`: monkeypatch `datetime.now` в `app.timeutils` + `app.api.points.charts` на замороженный инстант `FROZEN_NOW=2026-08-13 16:30 UTC`.
- **Сценарий**: запись в 16:00 UTC — это 13 авг по UTC, но 14 авг в Asia/Tokyo (UTC+9); с `client_tz=Asia/Tokyo` попадает в «сегодня» (Aug 14), без cookie — в UTC-день (Aug 13). Проверены labels + completed/stopped/planned, balance+breakdown, values, rates/overall_rate.
- Cookie собирается строкой (`auth_headers["Cookie"] + "; client_tz=..."`), не через httpx `cookies=` (не теряет access_token).
- **Тесты**: 618/618 ✅, ruff ✅, format ✅.

## 2026-08-13 — Сессия 97 (tz фонового job: training/scheduler)

- **`app/config.py`**: `tg_auto_analysis_tz` (IANA, default "UTC") — tz для времени срабатывания и границы суток автоанализа.
- **`app/timeutils.py`**: `resolve_tz(name)` — ZoneInfo с UTC-фолбэком (missing/invalid/None); `client_tzinfo` не тронут.
- **`app/training/scheduler.py`**: «сегодня» = `datetime.now(resolve_tz(settings.tg_auto_analysis_tz)).date()` (был `date.today()`); `_scheduler_loop` резолвит `analysis_tz` один раз, триггер и once-per-day dedup — в этом tz; лог показывает tz. `cleanup_expired_raw_responses` остаётся `datetime.now(UTC)` (TTL — инстант, не граница суток).
- **ADR-067**: фоновые задачи берут day-boundary из конфиг-tz, не из request `client_tz`/`User.timezone`.
- **Тесты**: +3 `resolve_tz` (valid/invalid/None). **613/613 ✅**, ruff ✅, format ✅.

## 2026-08-13 — Сессия 96 (финиш tz: device-local дневные бакеты графиков)

- **`app/api/points/charts.py`**: 4 daily-series эндпоинта переведены с SQL `func.date(created_at)` (UTC-день БД) на Python-бакетирование через `local_date(created_at)` (device-календарный день) — бары больше не сдвигаются на день для пользователей вблизи UTC-полуночи относительно подписей `local_today()`. `category-breakdown` не затронут (группировка по category, не по дню).
- **Убран** `case()/else_/func.sum/group_by` из daily-эндпоинтов; `breakdown` points-trend сохранил прежний cutoff-scope (исходный `type_result`-запрос был cutoff-bounded — проверено по git HEAD).
- **Гард** `txn_type or "other"` в breakdown (None-ключ в JSON), по аналогии с `row.category or "other"`.
- **Тесты**: 610/610 ✅, ruff ✅, format ✅.

## 2026-08-13 — Сессия 95 (границы суток в tz устройства)

- **`app/timeutils.py`**: request-scoped `ContextVar _client_tz` + `set/reset/get_client_tz`, `client_tzinfo()` (ZoneInfo с UTC-фолбэком при отсутствии/ошибке), `local_today()` (device-local «сегодня»), `local_date(dt)` (stored UTC datetime → device-календарная дата).
- **`app/main.py`**: middleware `client_tz_middleware` читает cookie `client_tz` → ContextVar (reset в finally).
- **`app.js`**: `Intl.DateTimeFormat().resolvedOptions().timeZone` → cookie `client_tz` (1y, SameSite=Lax).
- **Замена day-boundary** `date.today()`/`datetime.now(UTC).date()` → `local_today()`: dashboard, tasks, training (_get_today), calendar, diets (2), points/charts (4, вынесено из циклов), locktimer_ui (календарь), locktimer/repositories (weekly compliance), gamification xp+handler (streaks через `local_date(last_activity_date)`), llm/context_builder (2), llm/pipeline/diet (2), llm/pipeline/generate, importers/training.
- **Оставлен UTC** (фоновый job, нет request-контекста): `training/scheduler.py`.
- **`tzdata==2026.3`** в pyproject.toml + requirements.txt (ZoneInfo в slim-образах; проверено python:3.11-slim).
- **Тесты**: +5 в test_timeutils.py (local_today fallback/with-tz, local_date naive/with-tz, invalid tz). **610/610 ✅**, ruff ✅, JS ✅.

## 2026-08-13 — Сессия 94 (финиш по датам: locktimer + achievements + JS)

- **LockTimer**: `_serialize_session/_serialize_slot_occ/_serialize_task_occ` + tag_violations + templates — теперь передают datetime-объекты (были `.isoformat()` строки); `_serialize_session` нормализует `effective_end` через `as_utc()` для `effective_end_ts` (`.timestamp()`) и `remaining_seconds` (aware-vs-aware).
- **Шаблоны locktimer** (overview/session_detail/tag_violations/templates): сырое `[:19]/[:16]/[:10]` и `{{ x }}` → `localtime(x, fmt)`.
- **Achievements**: `obtained_at` теперь datetime (был серверный `.strftime("%Y-%m-%d")`) → `localtime(x, "%Y-%m-%d")` в dashboard.py + achievements.html.
- **JS**: `window.localDateISO(iso)` (device-local YYYY-MM-DD, документировано ожидание ISO с offset); points.js/diets.js `toLocaleDateString()` → `localDateISO()`.
- **Финальный свип**: в шаблонах/JS не осталось `[:19]/[:16]/[:10]`, `strftime`, `toLocale*`, `isoformat` (кроме date-only `today` в training.html и `snapshot_hash` в social/feed). **605/605 ✅**, ruff ✅, JS ✅.

## 2026-08-13 — Сессия 93 (отображение дат в tz устройства)

- **Jinja-глобал `localtime(value, fmt)`** (templates_setup.py): рендерит `<time datetime="...(+00:00)" data-tz-fmt="...">fallback</time>`; naive→UTC через as_utc; экранирование; None→пусто.
- **JS** (app.js): `formatLocalTime()` (%Y %m %d %H %M %S через локальные getters Date) + `applyLocalTimezones()` на DOMContentLoaded + htmx:afterSwap (title = UTC-инстант).
- **15 вызовов strftime → localtime()**: sessions/tasks/dashboard_v2/notifications + social/{relationships,subjects,profile,moderation,feed}.
- **LockTimer-карточка дашборда**: started_at/effective_end_at теперь datetime-объекты → localtime (было сырое [:19] UTC); +i18n `dashboard_timer_started` (EN/RU), рендер «Закрыт/Разблокировка».
- **Фикс UTC-off-by-one в дефолтах «сегодня»**: `window.localTodayISO()`/`localNowLocalInput()` в app.js → measurements.js (meas-date), calendar.js (check-dt), diets.js (consumed_date).
- **Тесты**: +3 теста localtime в test_timeutils.py. **605/605 ✅**, ruff ✅, JS-синтаксис ✅.

## 2026-08-13 — Сессия 92 (финиш по датам/времени)

- **naive `datetime.now()` → `datetime.now(UTC)`** (now всегда UTC): importers/activity_logs.py, importers/points.py (default created_at), points/schedule.py (weekday), tasks.py (is_available), import_data.py + cli.py (exported_at).
- **Materializer EXACT_DATETIME**: `SLOT_RULE_EXACT_DATETIME` + `TASK_SCHED_EXACT_DATETIME` — `datetime.fromisoformat(dt_str)` → `as_utc(...)` (planned_open_at/appears_at/due_at теперь aware, единообразно с остальными типами).
- **Аудит-вывод (без изменений)**: gamification/xp.py `should_reset_streak` и handler.py сравнивают `.date()` (tz-безопасно); context_builder/charts — SQL-уровень `created_at` (БД сама обрабатывает tz); references/search_tasks date_from/date_to — SQL-binding наивного ISO-midnight.
- **602/602 ✅, ruff ✅, format ✅**.

## 2026-08-13 — Сессия 91 (tz-хелпер + аудит сравнений дат)

- **Новый `app/timeutils.py`** — `as_utc(dt)`: aware → passthrough, naive → `replace(tzinfo=UTC)` (приложение UTC-only, naive считается UTC).
- **Рефакторинг 4 дублей** `if x.tzinfo is None: x.replace(tzinfo=UTC)` → `as_utc`: verification.py (2× expires_at), social/repositories/verification.py (deadline_at), social/api/relationships.py (cooldown_until).
- **Фикс латентного сравнения** telegram/bot.py: `telegram_link_code_expires < now(UTC)` → через `as_utc` (колонка timezone=True; на SQLite naive → TypeError).
- **Аудит locktimer** (тот же класс TypeError): execution.open_slot — нормализация now + eligible_from/eligible_until/planned_open_at; materializer — нормализация now + session.effective_end_at (local effective_end) в _materialize_session/_generate_*, window_start/end в FLEXIBLE_WINDOW_ONCE.
- **Тесты**: tests/test_timeutils.py (3), test_locktimer_services.py — tz-agnostic assert + новый регресс aware-now vs naive occurrence. **602/602 ✅, ruff ✅, format ✅**.
- **Замечание на потом**: naive `datetime.now()` в importers (activity_logs.py:37, points.py:38) для created_at — не сравнение, но неконсистентно с UTC-конвенцией.

## 2026-08-12 — Сессия 90 (Полный ре-экспорт + аудит сплитов + utcnow)

- **Полный ре-экспорт** `llm/pipeline/__init__.py` (S88 заузил поверхность): prompt-константы (DIET_EVALUATE/GENERATE/TRAINING_SYNERGY_SYSTEM, ANALYZE_DAY_SYSTEM, PLAN_DAY_SYSTEM, SUGGEST_NEXT_DAY_SYSTEM, SYSTEM_PROMPT_TEMPLATE), модели (ActivityLog, Diet/DietConsumption/DietEvaluation/DietItem/DietTrainingReview, LLMProviderConfig, TaskBodyTarget, TaskInventoryUsage, TaskLocationUsage, TrainingDay), repair/tools/validator (JsonRepairError, parse_llm_json, TOOLS, get_allowed_ids, validate_llm_response, validate_params_against_schema), cross-модули (call_llm, build_context, format_context_*).
- **Аудит остальных 6 сплитов** (AST-сравнение исходной поверхности vs пакета): execution-фасад восстановил 5 моделей + get_session/get_active_session; import_data — PointsProfile; social/repositories — 15 model-классов; references/points_v2/social-api — только `router` снаружи (no-op).
- **utcnow → datetime.now(UTC)** в 8 social-файлах (все DateTime(timezone=True)); убраны хаки `__import__("datetime").timedelta`; нормализация tz (`replace(tzinfo=UTC)` при naive) перед сравнением cooldown_until (api/relationships) и deadline_at (repositories/verification) — SQLite возвращает naive, PG — aware.
- **Проверки**: 598/598 ✅, ruff ✅, format ✅, ревью (Nit Pick Nick) учтено.

## 2026-08-12 — Сессия 89 (Фикс 17 LLM-тестов после сплита pipeline)

- **Корень**: НЕ cryptography/fernet на Py3.13 (ошибочный диагноз из S88). Причина — S88-сплит сломал monkeypatch: суб-модули делали `from app.llm.client import call_llm` (связывание на import-тайме), поэтому patch `app.llm.pipeline.call_llm` (и `app.llm.client.call_llm`) не доходил до вызовов → тесты уходили в реальный HTTP (`APIConnectionError`).
- **Фикс**: late-binding в generate/training/diet — `from app.llm import client, context_builder, validator` + вызовы `client.call_llm(...)` / `context_builder.build_context(...)` / `validator.get_allowed_ids(...)` на call-тайме.
- **__init__.py**: добавлен ре-экспорт `filter_automation_eligible` (его импортирует тест), удалены 3 мёртвых shim-ре-экспорта (call_llm/build_context/get_allowed_ids), поправлен docstring.
- **Тесты**: 21 patch-таргет переведён на source-модули (app.llm.client.call_llm / app.llm.context_builder.build_context / app.llm.validator.get_allowed_ids) в 3 файлах.
- **Проверки**: 598/598 ✅, ruff clean.

## 2026-08-12 — Сессия 88 (Финал рефакторинга + API v1→v2)

- **Шаг 7**: pipeline.py (953) → llm/pipeline/{generate(369), training(252), diet(355)}. __init__.py — ре-экспорт + backward-compat shims (call_llm, build_context, get_allowed_ids). 581/581 ✅.
- **API v1→v2**: 67 замен в 11 файлах (app: media/locktimer_commands/locktimer_proposals/verification/capabilities/main.py; templates: locktimer/session_detail+ templates; tests: 3 файла). Все роуты под /api/v2.
- **REFACTORING.md — ВСЕ 7 ШАГОВ ЗАВЕРШЕНЫ** ✅: execution(1409→525), import_data(988→486), references(817→пакет), points_v2(940→пакет), repositories(1070→пакет), api(1011→пакет), pipeline(953→пакет).

## 2026-08-12 — Сессия 87 (Рефакторинг, шаг 6: api.py → пакет social/api/)

- **Сплит** api.py (1011 строк, 25 роутов): 7 суб-роутеров — profile(136, 7: profile+consent+privacy+`_check_social_access`+`CURRENT_CONSENT_VERSION`), subjects(59, 2), relationships(317, 11: invites+blocks+grants+notifications), feed(131, 3: feed+publish+withdraw), verification(95, 3), comments(84, 4), moderation(199, 5: reports+actions+`_check_moderator`). __init__.py — агрегатор (prefix="/social", include_router).
- **Фиксы**: SocialProfile импорт добавлен (profile.py), мёртвые datetime/templates убраны.
- **Проверки**: 22/22 social-тестов, полный прогон 598/598 ✅, ruff clean.

## 2026-08-12 — Сессия 86 (Рефакторинг, шаг 5: repositories.py → пакет social/repositories/)

- **Сплит** repositories.py (1070 строк, 55 функций): 9 модулей — profile(64, 5), consent(38, 3), subjects(67, 5), relationships(254, 17: invites+blocks+grants+`_is_blocked`+`INVITE_COOLDOWN_HOURS`), notifications(56, 3), publications(130, 5: feed+CRUD), verification(140, 5), comments(95, 5), moderation(192, 11). __init__.py — явный ре-экспорт 52 имён (noqa:F401).
- **Потребители**: api.py (52 импорта) + 2 тестовых файла — пути импортов не изменились.
- **Циклов импортов нет**: модули импортируют только models; __init__ импортирует все 9.
- **Мёртвые `datetime`** убраны из consent/notifications.
- **Проверки**: 22/22 social-тестов, полный прогон 598/598 ✅, ruff clean.

## 2026-08-12 — Сессия 85 (Рефакторинг, шаг 4: points_v2.py → пакет api/points/)

- **Сплит** points_v2.py (940 строк, 35 эндпоинтов): 10 модулей — helpers(18: `_get_progress`), config(52), balance(82), profiles(83), redemptions(113), schedule(72), measurements(92), inventory(179: 8 эндпоинтов + `_ReorderPayload`), charts(228: 5 chart-эндпоинтов с lazy-импортами), pages(75: 4 HTML-страницы).
- **Префикс-паттерн**: суб-роутеры без префикса (только tags), агрегатор с `prefix="/api/v2"` — идентично шагу 3 (references). Первая версия имела двойной префикс (суб-роутеры тоже с `/api/v2`) → 404 на всех /api/v2/* эндпоинтах — исправлено.
- **main.py**: `from app.api.points import router` (было `points_v2`) — переменная `points_router`.
- **Замечания ревьюера**: `uuid` мёртвый в 3 модулях (charts/measurements/pages) — удалён.
- **Проверки**: 112 релевантных тестов, полный прогон 598/598 ✅, ruff clean.

## 2026-08-12 — Сессия 84 (Рефакторинг, шаг 3: references.py → пакет api/references/)

- **Сплит** references.py (817 строк): 4 суб-роутера — body_parts(111, 4 роута), locations(217, 7 роутов + CRUD), categories(25, 1 роут), task_targets(460, 11 роутов). __init__.py — агрегатор через include_router (23 роута под /api/v2).
- **Пакет-vs-модуль**: директория app/api/references/ затенила одноимённый модуль — решение: удалить модуль, агрегатор в __init__.py (from app.api.references import router продолжает работать).
- **AST-извлечение** с фиксом decorator_list; исправлены пропущенные импорты User (3 модуля) и дубль exists (task_targets).
- **Проверки**: 58 релевантных тестов + полный прогон 598/598 ✅, ruff clean, деплой ✅, /api/v2/body-parts отвечает на VPS.

## 2026-08-12 — Сессия 83 (Рефакторинг, шаг 2: import_data.py → пакет api/importers/)

- **Сплит** `app/api/import_data.py` (988 строк): api/importers/base.py (126: `_import_csv`/`_import_json` dispatch + `_json_handlers()` с lazy-импортами + `_float_or_none`) + 10 модулей-импортёров (measurements 49, inventory 47, entities 65, schedule 56, points 76, training 31, activity_logs 57, body_parts 48, locations 54, categories 41). import_data.py → 486 строк: роутер (7 роутов) + TEMPLATES/EXPORT_TYPES + экспорт.
- **Метод**: AST-извлечение тел (побайтово); для декорированных роут-функций пришлось учитывать decorator_list — `ast.get_source_segment` их пропускает (первая сборка потеряла декораторы, пересобрано из git HEAD с исправленным извлечением + assert-стража `'@router.' in seg`).
- **Циклы импортов**: нет — handlers импортируют base на уровне модуля (measurements → `_float_or_none`), base импортирует handlers только внутри функций (lazy).
- **Контракт зафиксирован**: импортёры живут в app.api.importers, из import_data.py их больше не импортировать (docstring + REFACTORING.md).
- **Тесты**: +6 HTTP-тестов dispatch (tests/test_importers_dispatch.py): /import/upload (measurements/inventory/unknown-400), /import/api (measurements/locations/unknown-400) — проверяют и ответ, и данные в БД. **598/598 ✅**, ruff ✅.
- **Замечания ревьюера учтены**: контракт в docstring, +HTTP-тесты на dispatch; logger-метки (app.api.importers.*) — осознанное изменение.

## 2026-08-12 — Сессия 82 (Рефакторинг, шаг 1: execution.py → пакет services/)

- **Сплит** `app/locktimer/services/execution.py` (1409 строк) по REFACTORING.md: drafts(233: create/update draft + правила + reorder), materializer(261: генерация occurrence), session(256: start + safety_stop + _cancel_future), jobs(104: outbox + очередь), tags(123: verify/lookup/audit пломб), execution(525: C5-ядро open/close/tasks/penalty + ре-экспорт-фасад).
- **Метод**: скрипт на AST (ast.get_source_segment) — тела функций извлечены побайтово, каждый модуль провалидирован ast.parse; `__all__` из 33 имён подавляет F401 и сохраняет все исторические пути импортов (locktimer_commands, locktimer_proposals, locktimer_ui, extras lazy-импорты, тесты).
- **Правки ревьюера**: tags.py вынесен отдельно (execution.py 628→525 строк); `LockSession` возвращён в импорты execution.py (apply_penalty); `uuid` добавлен в tags.py (type-hint).
- **Замечания зафиксированы**: `_now` продублирован в 5 модулях (приемлемо, при 6-м — вынести в _util); фасад execution.py остаётся точкой входа потребителей (follow-up — миграция на точные модули).
- **Проверки**: ruff format/check ✅, полный прогон **592/592 ✅**, деплой на VPS ✅.

## 2026-08-12 — Сессия 81 (Личный контур: честный фронт + нормализация + план рефакторинга)

- **Честный фронт (ADR-062)**: решения владельца зафиксированы ранее — lock = chastity, таблицы не меняем. Реализовано: i18n EN/RU (значения, ключи не тронуты, паритет 0 расхождений): `locktimer_title` → "Lock Timer"/"Таймер замка", `locktimer_session_label` → "Lock Session", `locktimer_slot_occurrences` → "Unlock Windows"/"Окна разблокировки", `locktimer_slot_rules` → "Unlock Rules", `locktimer_tag_number` → "Seal #"/"Пломба #", `locktimer_verify_tag` → "Verify Seal", audit → "Seal Audit".
- **Шаблоны**: кнопки Open→Unlock, Close→Lock, placeholder Tag #→Seal #; JS verifyTag — seal-тексты; confirm/empty-state — lock-тексты; base.html навигация (десктоп + мобильная) через `t.nav_timer` (было хардкод "Timer"); добавлен недостающий ключ `locktimer_slot` (tag_violations рендерил пусто).
- **Линт-нормализация**: `ruff format` — 19 файлов переформатировано, 130 уже ок; `ruff check` чистый; полный прогон **592/592 ✅**.
- **REFACTORING.md**: утверждённый план декомпозиции 7 файлов >800 строк (execution.py 1409 → services/{drafts,session,materializer,execution,jobs}; import_data → importers/*; references, points_v2, social repositories/api, pipeline) — механический перенос с re-export, ≤500 строк, шаг = файл + полный pytest.
- **OCR/LLM верификация** зафиксирована как Q13 (отложено, без сроков).

## 2026-08-12 — Сессия 80 (Housekeeping)

- **Git**: 47 непушедших коммитов → origin/main (bf1fd7f..033494f); удалена влитая ветка feat/product-composition-locktimer-core; рабочее дерево чистое.
- **Дубль list_templates**: extras.py теперь импортирует из repositories (было две идентичные реализации — риск расхождения зафиксирован и устранён).
- **TODO закрыт**: locktimer_proposals.py — `applied_at` теперь `datetime.now(UTC).isoformat()` (был None).
- **STATUS.md**: S78/S79 строки расцеплены (S79 содержала хвост S78).
- 101 locktimer-тест ✅, ruff ✅, задеплоено, healthz ok.

## 2026-08-12 — Сессия 79 (Timer): drag&drop переупорядочивание шаблонов

- **Данные**: миграция 035 — `sort_order` (INTEGER, NOT NULL, default 0) на `lock_timer_templates`.
- **Репозитории**: оба `list_templates` (repositories.py + extras.py) сортируют по `(sort_order, updated_at.desc())`.
- **Сервисы**: `save_template` добавляет новые шаблоны в конец списка (max+1); `reorder_templates` — точная валидация набора (empty/duplicate/foreign), archived-шаблоны исключены из обязательного набора.
- **API**: `POST /api/v1/locktimer/templates/reorder` — `template_ids` (comma-separated), 400 на ошибки, 303 redirect.
- **UI** (templates.html): нативный HTML5 drag&drop — ручка ⠿, draggable-карточки, подсветка ring, оптимистичный reorder + fetch, `location.reload()` при ошибке. Хинт переиспользует `locktimer_drag_hint`.
- **Тесты**: +9 (6 service, 2 API, 1 UI) — всего 25 в test_locktimer_reorder.py. **592/592 ✅**, ruff ✅, задеплоено (миграция 035 применена).

## 2026-08-12 — Сессия 78 (Timer): drag&drop переупорядочивание слотов

- **Данные**: миграция 034 — `sort_order` (INTEGER, NOT NULL, default 0) на `lock_slot_rules` и `lock_task_rules`. Модели LockSlotRule/LockTaskRule обновлены.
- **Репозитории**: `list_slot_rules`/`list_task_rules` сортируют по `(sort_order, created_at)`.
- **Сервисы**: `add_slot_rule`/`add_task_rule` автоматически добавляют новые правила в конец (max(sort_order)+1); `reorder_rules` — draft-only, точная валидация набора (нет missing/foreign/duplicate ids), audit-событие `locktimer.slot_rules.reordered` / `locktimer.task_rules.reordered`.
- **API**: `POST /api/v1/locktimer/sessions/{id}/slot-rules/reorder` и `.../task-rules/reorder` — на вход `rule_ids` (comma-separated), 400 на ошибки валидации, 303 redirect.
- **UI** (session_detail.html): нативный HTML5 drag&drop только в draft — ручка ⠿, draggable-строки, подсветка ring, оптимистичное перемещение в DOM + fetch для сохранения. Хинт «drag to reorder» / «перетащите для порядка» (i18n).
- **Тесты**: `tests/test_locktimer_reorder.py` — 16 тестов (service: порядок, валидация, audit; API; UI-атрибуты draft/active). **583/583 ✅**, ruff ✅, задеплоено.

# Журнал сессий

Формат: `дата — Сессия N: тема` → что обсуждали → результаты/договорённости → артефакты.
Новая запись добавляется **в конце каждой сессии**.


## 2026-08-12 — Сессия 76 (Q12): Deferred Timer items closed

- **Tag audit UI**: GET /locktimer/tag-violations/{session_id} — HTML-страница с карточками нарушений (mismatch/missing бейджи, expected vs provided tag, timestamp, ссылка на слот). Переиспользует существующий list_tag_violations сервис. Template: locktimer/tag_violations.html. +8 i18n keys EN/RU.
- **Timer standalone smoke test**: tests/test_timer_standalone.py — 7 тестов (overview, new draft, templates, tag violations page, API endpoints, capabilities endpoint, route isolation — no raw_llm_response/penalty_details leaks)
- **OPEN_QUESTIONS.md**: Q12 marked ✅ closed
- **567/567 ✅**, ruff ✅, deployed

## 2026-08-12 — Сессия 75 (S4+S6+S5+S7+docs): Social verification + comments, Tracker adapter, moderation, hardening, docs

- **S4 — Verification & Comments**: 5 new tables (verification_policies, verification_requests, verification_votes, social_comments, social_encouragements). Quorum-based verification (min_approvals→verified, max_rejections→review_required, deadline→no_quorum). Comments CRUD with edit support. Encouragement (4 types). 8 API endpoints. /social/verification page.
- **S6 — Tracker Adapter**: TrackerSocialAdapter (14 protocol methods: authorize, projection, capabilities, grant validation). TimerSocialAdapter skeleton. Registered at startup via composition flags.
- **S5 — Moderation**: moderation_reports (7 reason codes, 4 states), moderation_actions (append-only audit, 6 action types). Admin-only /social/moderation page with queue + action form.
- **S3 — Publications & Feed**: social_publications (immutable redacted snapshots, SHA-256 hash, 3 visibility levels), cursor-based feed (block-aware, accepted-relationship gated, namespace filter). /social/feed page.
- **S7 — Hardening**: 11 social concurrency tests (double-accept, invite+block race, feed after hide, grant idempotency, block propagation, cross-user isolation). 11 privacy audit tests (all social routes scanned for email/password_hash/raw_llm_response/penalty_details/ip_address/user_prompt leaks). pre_deploy_check.sh §8. DEPLOY_VPS.md §15 Social Ops Runbook.
- **Docs**: FUNCTIONAL.md §17 expanded (S3-S7), PRODUCT.md updated (Social section complete, status table all ✅).
- Миграции 031-033. i18n: +77 keys EN/RU across all S phases.
- **567/567 ✅**, ruff ✅, deployed.

## 2026-08-12 — Сессия 74 (S2): Platform Social — Relationships & Grants

- social_relationships: invitation lifecycle (pending→accepted/declined/expired/revoked), display_role presets (viewer/coach/mentor/curator), cooldown 24h
- social_blocks: cross-product block, unique pair, immediate shutdown
- social_grants: subject/module/global scope, JSON caps, propose→accept/revoke lifecycle, requires accepted relationship
- social_notifications: outbox (9 types), payload JSON, read status
- Миграция 030 (4 таблицы). API: 14 эндпоинтов (invite by alias, accept/decline/revoke, block/unblock, grant CRUD, notification read)
- UI: /social/relationships — 4 секции (pending, send form, active+grants, blocks+notifications)
- i18n: +13 keys EN/RU. Fix: 029 migration revision → hash convention
- **538/538 ✅**, ruff ✅, deployed

## 2026-08-12 — Сессия 73 (S0+S1): Platform Social — Foundation + Subject Registry

- app/platform/social/ package (models, repos, API — не импортирует Tracker/Timer)
- social_profiles: alias-based identity (3-80 chars, case-insensitive unique), bio, discoverable/show_in_feed
- social_consents: versioned, IP hash, /social/consent/accept
- social_subjects: opaque registry для domain adapters
- SocialSubjectAdapter Protocol + adapter registry (register_adapter/get_adapter_registry)
- /social/profile (CRUD), /social/privacy (public page), /social/subjects, /social/api/capabilities
- nav_social в base.html guarded by composition.social_operational
- SOCIAL_ENABLED + adapter flags в docker-compose.yml + .env
- Миграция 029 (3 таблицы). i18n: +38 keys EN/RU
- Deferred: Q12 (tag audit UI, timer-only deploy)
- **538/538 ✅**, ruff ✅, deployed

## 2026-08-12 — Сессия 72 (Tag mechanics): Numbered tags for timer

- close_tag_number на LockSlotOccurrence, require_tag на LockSlotRule
- lock_tag_violations: запись расхождения при verify
- close_slot(tag_number) — валидация дубликата + require_tag
- verify_tag → match ✅ / mismatch → violation + audit
- lookup_tag, list_tag_violations
- Миграция 028. UI: tag field в close form + verify button
- +20 tag mechanics tests. **538/538 ✅**

## 2026-08-12 — Сессия 71 (Timer extras): Countdown, validation, horizon, templates

- JS countdown timer (HH:MM:SS) на active sessions
- POST /validate — pre-start conflict check (slots overlap, task distribution)
- POST /extend-horizon — materialize +90 days
- LockTimerTemplate: save draft as template, instantiate, archive
- /locktimer/templates page. +12 i18n keys. **518/518 ✅**

## 2026-08-12 — Сессия 70 (Timer interactivity): Interactive actions

- locktimer_commands.py: 12 endpoints (start/safety-stop, slot open/close, task reveal/complete/skip, draft add/delete rules, PATCH metadata)
- Session detail page: action buttons for each state
- Dashboard timer card: quick Start/Edit links
- +16 i18n keys. **518/518 ✅**

## 2026-08-12 — Сессия 69 (Timer UI fixes): Frontend fixes + dashboard integration

- Fix active_nav mismatch: 'timer' → 'locktimer' in templates
- POST /locktimer/new → creates draft + redirects
- LockTimer active session card on dashboard (amber theme, duration/slots/tasks)
- dashboard.py fetches locktimer session via composition.timer_operational
- Fix: /body-parts/page route ordering (before /{body_part_id})

## 2026-08-11 — Сессия 68 (C9): Hardening — concurrency tests, secret scan, runbook, owner allowlist

- **Concurrency tests** (tests/test_concurrency.py): 11 сценариев из 13_TEST_PLAN.md §5 — double start (only one active), double open/close (idempotent), open+stop, submit vs skip, penalty idempotency (duplicate→None, 1 row), job idempotency (1 row), outbox uniqueness (distinct events), cross-user safety stop (404), complete idempotency, recovery after stop (new draft allowed). Все 11 ✅.
- **Secret scan**: grep по hardcoded password/api_key/JWT — ничего не найдено. `.env` в .gitignore (7 строк). Fake test keys (gsk_test123, encrypted-key) — в тестовых фикстурах, безопасны.
- **Dependency audit**: pip-audit/safety не установлены (PEP 668 system python). pip freeze → 80+ пакетов, критические CVEs не проверены (отложено до CI-интеграции).
- **Owner allowlist**: `locktimer_owner_allowlist` (comma-separated emails) в config.py → gate в locktimer_ui.py (`_check_owner_allowlist`). Пустая строка = без ограничений.
- **RUNBOOK.md**: 11 разделов — pre-deploy checklist, deploy, migration runbook, rollback (6 сценариев), backup/restore (daily cron + quarterly drill), health checks, incident playbooks (5 сценариев), monitoring commands, feature flag reference, variant reference, SLOs.
- **pre_deploy_check.sh**: 7 шагов (git status, pytest, ruff, secret scan, config .env, docker build, alembic heads).
- **Readiness**: `/healthz/readiness` с DB-проверкой (SELECT 1, 503 на ошибке).
- **ADR**: ADR-057 (C9 hardening).
- **Тесты**: **518/518 ✅** (+11 concurrency), ruff ✅, format ✅.
- **Артефакты**: 4 новых файла (tests/test_concurrency.py, RUNBOOK.md, pre_deploy_check.sh, +readiness endpoint). Изменены: main.py, config.py, locktimer_ui.py, capabilities.py.

## 2026-08-11 — Сессия 67: Universal media + verification (platform C6, без OCR)

- **Решение владельца**: универсальная медиа-система (не только для Timer), OCR отложен.
- **media_assets** (app/models/media.py): owner-scoped (owner_id/owner_type/owner_ref_id), staged→ready→archived pipeline, MIME+magic-bytes validation, SHA-256, dimensions (Pillow), thumbnail generation (JPEG 400x400), CHECK constraints (size 0-200MB, state enum).
- **verification_challenges** (app/models/media.py): one-time codes, HMAC-SHA256 stored (plaintext never), alphabet без O0I1l, constant-time comparison (hmac.compare_digest), TTL, max_attempts, auto-expire, new challenge invalidates previous. Code returned exactly once at creation.
- **app/services/media.py**: save_media (validation pipeline), _get_dimensions (Pillow, max 12000px), _make_thumbnail (LANCZOS resize→JPEG 80%), delete_media_file (path traversal hardened), generate_verification_code, compute_code_hmac, verify_code_constant_time.
- **API media** (app/api/media.py): POST upload (multipart, max 15MB), POST finalize (staged→ready, bind to owner_ref), GET serve (authorized, nosniff+no-store headers), GET thumbnail, DELETE (staged only), GET list (owner_type/ref_id/state filters).
- **API verification** (app/api/verification.py): POST create challenge (code returned once), POST verify (constant-time, state machine: active→consumed/failed/expired), GET status (code NEVER returned, auto-expire on read).
- **Config**: challenge_hmac_key, media_max_upload_bytes (15 MB).
- **Routes**: media+verification всегда регистрируются (platform-level).
- **SQLite tz fix**: expires_at comparison с naive→aware нормализацией.
- **Тесты**: +19 (test_media_verification.py — code gen, HMAC, constant-time, model CRUD, API upload/list/delete, create/verify/wrong/max-attempts/invalidate/status). **507/507 ✅**, ruff ✅, format ✅.
- **ADR**: ADR-056 (universal media+verification).
- **Артефакты**: 6 новых файлов (models/media.py, services/media.py, api/media.py, api/verification.py, migration 027, tests/test_media_verification.py). Изменены: config.py (+2 настройки), main.py (+2 роутера), conftest.py (MediaAsset+VerificationChallenge в imports).

## 2026-08-11 — Сессия 66 (C7+C8): LockTimer LLM integration + Timer UI pages

- **C7 — LLM Proposals**: `lock_llm_proposals` таблица (kind, status, items JSON, usage tracking, raw_response_encrypted) + миграция 026. `app/locktimer/llm_context.py` — timer-aware контекст-билдер (build_timer_context + format_timer_prompt с user_brief). `app/api/locktimer_proposals.py` — POST create (LLM call через app.llm.client, JSON repair, item validation), GET proposal, apply item (slot_rule→add_slot_rule, task_rule→add_task_rule, только draft), reject item.
- **C8 — Timer UI**: `app/api/locktimer_ui.py` — SSR страницы: GET /locktimer (overview: active session + upcoming slots/tasks + drafts + history), GET /locktimer/sessions/{id} (detail: info grid, slot/task rules, occurrences with state badges, LLM proposals). `templates/locktimer/overview.html` + `session_detail.html` — full pages extending base.html.
- **Routes in main.py**: роуты регистрируются при composition.timer_operational (LOCKTIMER_CORE_ENABLED=true).
- **Tests**: `LOCKTIMER_CORE_ENABLED=true` в conftest (setdefault до импорта app). test_audit_s57 bottom-nav: 4→5 ссылок (Timer в nav). +9 C78 тестов (context/prompt, модель, cross-user, overview/auth/session-page). **488/488 ✅**, ruff ✅, format ✅.
- **ADR**: ADR-055 (C7+C8 LLM+UI).
- **Артефакты**: 6 новых файлов (locktimer/llm_context.py, api/locktimer_proposals.py, api/locktimer_ui.py, templates/locktimer/overview.html, session_detail.html, tests/test_locktimer_c78.py), миграция 026, +23 i18n ключей. Изменены: models/locktimer.py, main.py, conftest.py, test_audit_s57.py.

## 2026-08-11 — Сессия 65 (C3+C4+C5): LockTimer execution services — draft/start, materializer, slot/task/penalty/safety-stop

- **C3 — Draft + Start**: `create_draft`/`update_draft`, `add_slot_rule`/`add_task_rule`/delete, `start_session` (atomic conditional UPDATE+rowcount, canonical snapshot+hash, materializer chaining).
- **C4 — Materializer**: 5 slot schedule types (every_n_days, exact_datetime, recurring_from_date, flexible_window_once, after_previous_close placeholder) + 6 task schedule types (daily, every_n_days, recurring_from_date, exact_datetime, anytime_before_end, deterministic_random). Rolling horizon (90 days default, capped by session max_end).
- **C4 — Job Runner**: `enqueue_job` (idempotent by job_key), `claim_jobs` (SELECT FOR UPDATE SKIP LOCKED, lease).
- **C5 — Slot execution**: `open_slot` (eligibility window check + late-open extension with rule.extend_on_late_open), `close_slot`. Audit on every transition.
- **C5 — Task execution**: `reveal_task` (scheduled→visible state transition), `submit_task`, `complete_task` (idempotent), `skip_task`. Audit trail.
- **C5 — Penalty**: `apply_penalty` (allowlisted types + idempotency key, add_time with cap/max_end via `apply_extension`, capped_noop when max exceeded). Event flushed before write_audit.
- **C5 — Safety Stop**: `safety_stop` (active→safety_stopped, cancel future slot+task occurrences, audit).
- **C5 — Outbox**: `emit_outbox_event` (transactional domain events, pending state).
- **SQLite compat fix**: all `update().returning()` replaced with `update()` + `flush()` + `select()`/`db.get()` (avoid ResourceClosedError on async SQLite).
- **reveal_task fix**: scheduled→visible state transition (was only setting content_visible=True).
- **late_open fix**: `_started_session_with_slot` helper missing `extend_on_late_open=True` → extension_applied_seconds was 0.
- **penalty flush fix**: penalty event flushed before write_audit to assign id.
- **Тесты**: 29 service integration tests (`tests/test_locktimer_services.py`) — draft/start/slot/task/penalty/safety-stop/outbox/job-runner/materializer. **479/479 ✅**, ruff ✅, format ✅.
- **ADR**: ADR-054 (C3+C4+C5 execution services).
- **Артефакты**: `app/locktimer/services/__init__.py`, `app/locktimer/services/execution.py` (800+ lines), `tests/test_locktimer_services.py`; изменены tests/conftest.py (import cleanup), alembic/versions/025 (JSONB→JSON), app/models/locktimer.py (JSONB→JSON).

## 2026-08-11 — Сессия 64 (C1+C2): LockTimer domain + persistence — 12 таблиц, state machines, repositories

- **C1 — Pure domain** (`app/locktimer/`):
  - `app/locktimer/enums.py`: 6 session states + transitions (draft→validating→active→completed/safety_stopped), 7 slot states + transitions (pending→eligible→open→closed), 10 task states + transitions (scheduled→visible→submitted→…→completed/review/failed), 5 slot rule types, 6 task schedule types, 4 penalty types + event states.
  - `app/locktimer/domain.py`: `apply_extension(clamp, max_end)`, `canonical_json` (sorted keys), `sha256_hex`, `deterministic_random(seed, rule_id, index)` → [0,1), `generate_random_seed`/`compute_seed_commitment`, `make_occurrence_key`, `validate_safety_stop_reason`.
- **C2 — Persistence** (`app/models/locktimer.py`):
  - 12 таблиц: `lock_timer_templates` (owner-scoped, config+sha256, archived_at), `lock_sessions` (state/duration_type/timezone/started_at/effective_end_at/max_end_at/merge_gap/random_seed/row_version/safety_stop), `lock_session_snapshots` (immutable canonical_config+sha256), `lock_inner_periods` (rule_type+rule_data, client_key), `lock_slot_rules` (5 types, duration/grace/late checks, schedule JSONB), `lock_slot_occurrences` (occurrence_key, planned_open/close, eligible window, state, extension), `lock_task_rules` (6 schedule types, source_entity FK, media/verification/penalty/availability policies), `lock_task_occurrences` (appears_at/due_at, content_visible, snapshot, state), `lock_penalty_events` (allowlist types, idempotency_key unique), `lock_audit_events` (actor/correlation/versions, append-only), `lock_job_receipts` (job_key unique, lease, attempts), `lock_outbox_events` (aggregate, payload, state).
  - Named constraints: ck_lock_sessions_merge_gap, ck_lock_slot_rules_duration/late/grace, ck_lock_task_rules_window, partial unique uq_lock_sessions_active_owner (WHERE state='active').
- **Миграция 025**: PG15 up/down/up ✅ (12 CREATE TABLE + indexes + constraints + partial unique index).
- **Repositories**: `app/locktimer/repositories.py` — owner-scoped queries (get_session, get_active_session, list_sessions, list_slot_rules/task_rules, list_slot/task_occurrences), `transition_session` (conditional UPDATE with row_version increment), `write_audit` (append-only).
- **Тесты**: +31 domain unit test (`tests/test_locktimer_domain.py`) — states/transitions, duration/extension, canonical JSON, deterministic random, seed generation, occurrence keys, safety stop. **450/450 ✅**, ruff ✅, format ✅.
- **ADR**: ADR-053 (C1+C2 domain+persistence).

## 2026-08-11 — Сессия 63 (C0): Platform Foundation + composition root + три варианта приложения

- **Пакет**: `/examples/LT/LockTimer-Agent-Pack` v1.1 (20 файлов, 93 требования, 66 сценариев).
- **Решение владельца**: «Всё сразу (Core + Social)», но порядок: Core сначала → Social после gate, медиа пока без.
- **C0 (Platform Foundation + composition)**:
  - `app/config.py`: `APP_PRODUCT_VARIANT` (tracker|timer|combined, default combined), `LOCKTIMER_CORE_ENABLED` + 6 feature flags (all default off). Валидация: timer без core → maintenance mode gate.
  - `app/platform/composition.py`: `ProductComposition` (immutable dataclass), `_resolve_enabled_modules()`, `build_product_composition()`, module-level singleton.
  - `app/platform/capabilities.py`: `GET /api/v1/platform/capabilities` — variant, modules, social_stage, timer_stage, api_versions.
  - `app/platform/__init__.py`: package doc — platform MUST NOT import domain modules.
- **User.timezone** (ADR-051): колонки `timezone` (default UTC) + `timezone_confirmed_at`; миграция 024 (up/down/up готово).
- **main.py**: composition строится при импорте (через module-level singleton); Tracker routers регистрируются только при `tracker_active`; Timer routes — placeholder для C1-C8; capabilities всегда доступен; CSRF exempt для `/api/v1/platform`; homepage получает `composition` в контекст.
- **templates_setup.py**: `_composition_context` processor — инжектирует `composition` во все шаблоны.
- **base.html**: desktop + mobile nav — Tracker ссылки обёрнуты в `{% if composition.tracker_active %}`, Timer nav (placeholder) в `{% if composition.timer_operational %}`.
- **i18n**: +8 ключей EN/RU (nav_timer, locktimer_title/subtitle/coming_soon).
- **ADR**: +6 (047–052) в DECISIONS.md.
- **Результат**: **419/419 тестов ✅**, ruff ✅, format ✅, compile ✅.
- **Артефакты**: +4 файла (platform/__init__.py, composition.py, capabilities.py, миграция 024); изменены config.py, models/user.py, main.py, templates_setup.py, base.html, i18n/en.py, i18n/ru.py, memory/DECISIONS.md.

## 2026-08-11 — Сессия 62 (финал): открытые вопросы закрыты (Q2/Q4/Q8/Q11)

- **Запрос владельца**: «Закрывай открытые вопросы».
- **Q2 (30+ задач)**: проверено — `SEED_ENTITIES` в app/seed.py = ровно 30 задач, идемпотентный seed, расширяется личными сущностями → **закрыт**.
- **Q4 (Telegram-тексты)**: базовый формат реализован (Markdown-уведомления всех типов + inline-клавиатуры) → **закрыт**.
- **Q8 (backend audited defects)**: дублирует Q10, все закрыты в S40+S55+S57 → **закрыт**.
- **Q11 (новая модель активностей)**: полный цикл S58–S62 (Phase 1+2+остаток, update2.md, Phase 3 UI, Phase 4) → **закрыт**.
- Оставлены отложенными только Q5 (оплата/тарифы) и Q6 (рейт-лимиты) — зависят от открытия публичного доступа.
- **Артефакты**: memory/OPEN_QUESTIONS.md переписан (таблица + итоговый статус Q11).

## 2026-08-11 — Сессия 62: всё по порядку — коммит, PG15, деплой-проверка, Phase 2 остаток

- **Запрос владельца**: «давай всё по порядку» (из followup: финальный прогон + память → PG15 + деплой → Phase 2 остаток → коммит кода).
- **Коммит кода 59–61** (`c0d30a5`, 37 файлов): update2.md + Phase 3 UI зафиксированы в git.
- **PG15-валидация миграции 023** (конвенция S54–58): временный postgres:15-alpine, upgrade 001→023, ORM-вставка/чтение всех 9 новых таблиц + InventoryItem, downgrade 023→022, повторный upgrade — всё ✅; контейнер удалён.
- **Деплой**: seed-кнопки в админке проверены (seed-entities включает категории, seed-references — body_parts/locations/inventory_categories), Dockerfile копирует app/ целиком; VPS-команды: git pull → up -d --build → alembic upgrade head → seed-кнопки.
- **Phase 2 остаток**: scheduler в transition API (set_next_due/set_retry_block, с идемпотентностью), валидация actual_parameters против схемы, actual_parameters в LLM-контексте (build_context + оба формата промпта), геймификация по actual (intensity + points v2 бонусы).
- **Ревью**: 3 фикса (идемпотентность планировщика, JS-коэрция чисел, реальный тест handler'а вместо тавтологического).
- **Результат**: 419/419 тестов ✅ (+5: next_due/retry_block/валидация/контекст/handler-XP), ruff ✅, node ✅.
- **Артефакты**: изменены task_flows.py / context_builder.py / handler.py / tasks.js / test_phase3_task_ui.py.

## 2026-08-11 — Сессия 61 (update.md Phase 3 UI): каталог-категории, форма параметров, быстрые действия, карточка выполнения

- **Запрос владельца**: «что дальше?» → выбрал update.md Phase 3 UI (Q11): каталог с фильтрами по категориям, динамическая форма параметров, список задач с быстрыми действиями, карточка выполнения, статистика.
- **Каталог (ADR-035)**: фильтры переведены на иерархическую таблицу `ActivityCategory` (дерево root+children, подкатегории активной категории, фильтр с потомками), legacy `?category=` сохранён; `create_entity` +`category_id`.
- **Форма параметров (ADR-041)**: partial `partials/params_form.html` рендерит поля по типам DSL (enum+allow_custom_value, multi_enum checkboxes, number/textarea/boolean, reference selectors data-selector); `GET /tasks/params-form?entity_id=&prefix=`, `POST /tasks/create` (planned, validate_params, title_gen).
- **Быстрые действия (ADR-040)**: серверно рендерится граф `next_actions`, кнопки-переходы в карточках; completed/partial открывают карточку выполнения с actual_parameters + completion_comment (TransitionIn расширен, completed_at).
- **Статистика**: `status_stats` чипы (7 статусов + total) на tasks.html.
- **JS**: tasks.js переписан (загрузка формы, селекторы в динамических формах, fetch-переходы с CSRF, карточка выполнения), фикс бага исходного `selInv`.
- **Ревью**: custom enum value, аннотация _coerce_param, i18n reactivate — исправлены.
- **Результат**: **414/414 тестов ✅** (+13), ruff ✅, node --check ✅.
- **Артефакты**: `partials/params_form.html` (новый), `tests/test_phase3_task_ui.py` (новый, 13 тестов); изменены entities.py / tasks.py / task_flows.py / catalog.html / tasks.html / tasks.js / i18n en+ru.

## 2026-08-11 — Сессия 60 (update2.md, финал): селекторы, фильтры, полный прогон тестов

- **Запрос владельца**: «давай селекторы и фильтры» → селекторы в форме задачи, фильтры истории; затем «запусти тесты и прочее, и обнови память».
- **Селекторы (Preferences) в форме генерации** (`tasks.html` + `tasks.py` + `pipeline.py`): секция body_part / location / inventory; значения уходят в `/tasks/generate`; `generate_task()` принимает `body_part_id`/`location_id`/`inventory_item_id` — предпочтения инжектятся в промпт LLM, после создания ActivityLog создаются link-записи (`TaskBodyTarget`/`TaskLocationUsage`/`TaskInventoryUsage`).
- **Фильтр-бар истории** (`tasks.html` + `tasks.py`): статус / зона / место / предмет → query-параметры → SQL-фильтрация через exists-подзапросы по link-таблицам.
- **JS-модули (DESIGN §15.4)**: `tasks.js` (новый), `body_parts.js`, `locations.js` — инлайн-скрипты вынесены, `test_no_inline_scripts_in_pages` ✅.
- **Тест-фиксы**: системные локации → 404 (owner-фильтр), slug'и зон сверены с seed.
- **Результат**: **401/401 тестов ✅** (полный прогон, 130s), ruff ✅, format ✅ (переформатирован import_data.py), compile ✅. Новых ADR нет — реализация ADR-046/043/044/045.
- **Артефакты**: `static/js/pages/tasks.js` (новый), изменены tasks.html / tasks.py / pipeline.py / i18n (en/ru, +14 ключей) / body_parts.js / locations.js / body_parts.html / locations.html.

## 2026-08-11 — Сессия 59 (update2.md): справочники BodyPart / TaskLocation / InventoryCategory — полный цикл

- **Анализ `examples/update2.md`**: спецификация справочников (BodyPart, TaskLocation, InventoryCategory) + связей (TaskBodyTarget, TaskLocationUsage, TaskInventoryUsage) + DSL-селекторов. Сверка с текущей архитектурой.
- **Решения владельца (интервью)**: оставить оба измерения статусов инвентаря (shopping + operational); таблицы требований + DSL (оба подхода); отдельные таблицы для категорий инвентаря; имя таблицы TaskLocation; DSL-типы + валидация.
- **Phase 1 — Модели** (ADR-043…046): `BodyPart` (40 seed, иерархия), `TaskBodyTarget`, `TaskLocation` (25 системных + пользовательские, privacy_level), `TaskLocationUsage`, `InventoryCategory` (16 категорий), `TaskInventoryUsage`, `ActivityBodyPartRequirement` / `ActivityLocationRequirement` / `ActivityInventoryRequirement`. `InventoryItem` — +inventory_category_id FK, +inventory_status (available/in_use/…). Миграция 023 (9 таблиц + 2 колонки).
- **Phase 2 — DSL + API**: расширение `app/params.py` (+3 типа: inventory_selector, body_part_selector, location_selector); `app/schemas/references.py` (Pydantic-схемы); `app/api/references.py` (23 эндпоинта — CRUD справочников, batch-links, inventory/available, tasks/search с 11 фильтрами). Роутер зарегистрирован в main.py, модели в alembic/env.py.
- **Phase 3 — Тесты**: `tests/test_references.py` (34 теста) + обновление `conftest.py` для новых моделей. Seed (иерархия, идемпотентность), API (CRUD, batch-replace, snapshot, cross-user 404, archive 409), search (6 фильтров), inventory available, DSL selectors, совместимость.
- **Phase 4 — UI + импорт**: `body_parts.html` (дерево, поиск, фильтр), `locations.html` (CRUD, архив, delete), доработка `inventory.html` (динамические фильтры категорий, бейджи статусов), +2 карточки в админке. Импорт/экспорт: 3 новых типа (body_parts/locations/inventory_categories) + handler'ы, инвентарь-расширение. i18n: +48 ключей EN/RU.
- **Владелец**: «продолжай», «давай тесты», «давай UI», «продолжай и не забудь импорт», «доделывай всё».
- **Результат**: **388/388 тестов ✅**, ruff ✅, compile ✅.
- **Артефакты (20 файлов)**: 9 новых Python-файлов (4 модели + 2 схемы/API + 3 seed), 3 HTML-шаблона, 1 миграция, +4 memory (ADRs). Изменены: models/__init__.py (все модели перечислены), models/life.py, params.py, api/admin.py, api/import_data.py, schemas/points_v2.py, main.py, alembic/env.py, conftest.py, templates/admin.html, templates/inventory.html, static/js/pages/inventory.js, i18n/en.py, i18n/ru.py, memory/*.

## 2026-08-11 — Сессия 58 (Phase 2): backend новой модели — DSL параметров, title-генератор, API переходов статусов

- **Типизированный DSL параметров (ADR-041)** — `app/params.py`: `normalize_schema()` принимает обе формы (legacy map — правила без type инференсятся: min/max→decimal, enum→enum+options, min_length→string; required по умолчанию True как в старом LLM-контракте; структурированный список — key/title/type/required/options/min/max/unit_group/visible_when/allow_custom_value, required по умолчанию False). 8 типов: string/text/integer/decimal/boolean/enum/multi_enum/duration. `validate_params()` — чисто декларативная валидация, **без eval** (whitelist типов, bounds, enum, min/max_length). Ошибки конфигурации схемы (неизвестный тип) возвращаются как `UNKNOWN_PARAM_TYPE`, а не падают. `COMMON_PARAMETERS` — 13 переиспользуемых параметров из update.md (tool, target_area, count, unit, duration, intensity 1–5, position, role, modifiers, clothing, restraint, timing, notes). LLM-валидатор `validate_params_against_schema` теперь делегирует в DSL (мёртвый код `_TYPE_VALIDATORS`/`_validate_one_param` удалён).
- **Title-генератор (ADR-042)** — `app/title_gen.py`: priority chain title_override → manual_title → template → param list → activity title → «Free task: [manual title]». Пустые части шаблона пропускаются и артефакты вычищаются. Лейблы i18n EN/RU (tool→инструмент, zone→зона, intensity→интенсивность, free task→Свободная задача…), интенсивность выводится как N/5, enum-option titles из схемы. В pipeline при генерации задачи создаётся `title_override` с авто-заголовком (locale-aware); `task_template` добавлен в entity-словари `build_context` (раньше никогда не достигал генератора — ревью-фикс).
- **API переходов статусов (ADR-040)** — `app/api/task_flows.py`: `POST /api/v2/tasks/{id}/transition` (to_status + comment; валидация через `can_transition`, нелегальный → 409; completed → on_task_completed (награда), stopped → on_task_interrupted (штраф), остальные статусы — без наград/штрафов по ADR-038) + `GET /api/v2/tasks/transitions` (граф для UI). `security.transition_once` — атомарный UPDATE + ActivityTaskHistory; предыдущий статус захватывается ДО update (synchronize_session="evaluate" мутирует объект — баг из тестов, ревью-фикс); cross-user → 404. В `STATUS_TRANSITIONS` добавлен planned→stopped (ADR-029: прерывание планированной задачи несёт штраф).
- **Тесты**: +19 в `tests/test_phase2_task_flows.py` — нормализация обеих форм схемы, отказ от bad schema, валидация без eval, legacy-совместимость (optional, enum→options, unknown type), COMMON_PARAMETERS, title (override/template/fallback/RU-i18n/enum-titles), transitions (skipped/cancelled с аудитом, нелегальные 409, награда за completed, штраф за stopped, неизвестный статус 400, граф, cross-user 404). **354/354 ✅**, ruff ✅.
- **Артефакты**: `app/params.py`, `app/title_gen.py`, `app/api/task_flows.py`, `security.transition_once`, pipeline-хук, обновлённый validator.py.

## 2026-08-11 — Сессия 58: новая модель активностей — Phase 1 (ADR-035…042): категории, статус-машина 11, аудит, эволюция моделей

- **Анализ `examples/update.md`**: предложенная система хранения активностей сверена с v0.8 — философия «базовая активность + шаблон + экземпляр» уже реализована; выявлены пробелы (ActivityCategory, 11 статусов, аудит, planned/actual параметры, title-генератор) и конфликты (ADR-029 vs «не запрещать остановку», Training, геймификация). Решения владельца зафиксированы в ADR-035…042 (см. DECISIONS.md). Создан `FUNCTIONAL.md` — читаемый обзор текущего функционала.
- **Phase 1 — модели**: `ActivityCategory` (slug/title/description/sort_order/is_active/parent_id, иерархия); `Entity` → Activity (+slug, short_title, role_tags, task_template, category_id FK, penalty_enabled, updated_at); `ActivityLog` → ActivityTask (+title_override, scheduled_at, planned_comment, completion_comment, actual_parameters, updated_at; статусы 3 → 11); `ActivityTaskHistory` (аудит переходов: prev/new status, snapshot, comment, actor); `ActivitySession` (+title, notes, planned_start_at/end, accepted_at).
- **Статус-машина** (`app/models/task_status.py`): 11 статусов, `STATUS_TRANSITIONS` (draft→planned→in_progress→completed/partially_completed/stopped; planned→skipped/cancelled/substituted/not_applicable/review_needed), `can_transition()`, `normalize_status()` (legacy pending→planned, interrupted→stopped). Константы используются в security.py (complete_once/interrupt_once теперь атомарно пишут ActivityTaskHistory; interrupt разрешён из planned И in_progress).
- **Миграция 022** (PG15 up/down/up ✅): таблицы activity_categories + activity_task_history; колонки entities/activity_logs/activity_sessions; ремап статусов pending→planned, interrupted→stopped; backfill категорий из legacy-строк entities.category (транслит-slug, idempotent).
- **Seed**: `app/seed_categories.py` — 16 категорий с подкатегориями из update.md; `seed_categories()` идемпотентна, вызывается из /admin/seed-entities; seed.py добавляет slug.
- **Код-обновление статусов**: pipeline, context_builder (stats keys → stopped), points_v2 (chart SQL label/response → stopped/planned + JS dashboard/sessions), training (счётчики), telegram/bot (planned/stopped), i18n (11 статусов EN/RU). Ревью-фиксы: match.interrupted AttributeError в charts/activity, interrupt из in_progress, JS-контракт data.stopped/data.planned, косметика.
- **Тесты**: +12 (`tests/test_phase1_task_model.py`) — категории/seed, статус-машина (переходы, legacy), колонки эволюции, аудит, сессии, penalty_enabled, slugify. **335/335 ✅**, ruff ✅, node --check ✅.
- **Артефакты**: `FUNCTIONAL.md`, ADR-035…042, миграция 022, 6 новых/изменённых моделей, seed_categories.
- ⚠️ **VPS**: `git pull && docker compose up -d --build` — миграция 022 применится автоматически (статусы задач переименуются).

## 2026-08-11 — Сессия 57: «делай всё» — закрыты все deferred Q9/Q10 (risk_level, typed DSL, Inter font, bottom nav, JS modules)

- **risk_level на Entity (REM §5.2)**: колонка (default not_assessed) + миграция 021 (PG15 up/down/up ✅); схемы (EntityCreate/Update/Response, pattern), Form-поле с санитизацией; seed-каталог → `low` (curated pre-assessed); `filter_automation_eligible()` в context_builder (low всегда, elevated только с allow_elevated, not_assessed/high никогда) — подключён в generate_task и generate_daily_plan; бейджи risk в catalog.html и my_entities.html.
- **Typed gamification DSL (P2)**: `app/gamification/dsl.py` — валидатор условий (whitelist операторов >,<,>=,<=,==,!=; field regex; value: число/true/false/короткая кавычка) + `eval_condition`/`find_param_key` (без eval); `validate_penalty_condition` (missed/partial/late); Pydantic-валидаторы в BonusCondition и PenaltyLevel (схемы); points_v2 engine переведён на DSL; тест-гард «нет eval».
- **Subtask/risk gate тесты (REM §7.1)**: test_generate_plan_sanitizes_subtasks (cap 20, длина 500, коэрция строк, whitespace-drop) + test_generate_plan_risk_gate_blocks_unassessed.
- **Inter self-hosted (DESIGN §7.1)**: `app/static/fonts/InterVariable{,-Italic}.woff2` (rsms.me), @font-face + font-family на html, `.tabular-nums`; CDN-ссылок нет.
- **Mobile bottom nav (DESIGN §4.4)**: 4 пункта (Dashboard/Tasks/Training/Catalog), 64px + safe-area-inset, md:hidden; desktop-nav скрыт на mobile (hidden md:flex), тумблеры locale/theme + logout-иконка видны на всех; хардкод `Tasks` → `t.nav_tasks`.
- **JS-hoist в ES modules (DESIGN §15.4)**: `app/static/js/app.js` (CSRF-обёртка fetch, HTMX config, escapeHtml) + 10 page-модулей в `app/static/js/pages/`; i18n/данные — через `<script type="application/json" id="page-i18n">` (не inline JS!); `window.*`-экспорты для onclick-хендлеров; все 11 файлов прошли `node --check`.
- **Ревью-фиксы**: (1) diets JSON-блок сериализовал ORM-объект active_config → утечка api_key_encrypted в DOM — заменено на `active_config is not none`; (2) дублирование навигации на mobile — desktop-nav скрыт; (3) хардкод Tasks → i18n.
- **Миграция 021** проверена на PG15 (upgrade 001→021, downgrade 021→020, повторный upgrade).
- **Тесты**: +16 (tests/test_audit_s57.py) — 323/323 ✅, ruff ✅, node --check ✅.

## 2026-08-10 — Сессия 56: Диеты v3 — история, синергия диет↔тренировки, фичи
- **История оценок диет**: `diet_evaluations` (каждая оценка сохраняется), UI-кнопка «История» в карточке.
- **Синергия диет и тренировок**: `diet_training_reviews` + LLM `analyze_diet_training_synergy` — взаимное влияние (питание→тренировки и наоборот), корреляции + корректировки; секция на странице диет с историей.
- **Фичи**: inline-редактирование позиций диет (клик → форма, Enter сохраняет), фото диет через attachments (owner_type=diet).
- **Исправления по ревью**: showHistory рендерил в первую карточку вместо нажатой; стабильный порядок истории (created_at в Python, а не server_default — func.now() в одной SQLite-транзакции одинаковый).
- Артефакты: миграция 020 (PG15 up/down/up), +6 тестов, 297/297 ✅.

## 2026-08-10 — Сессия 55: Внешний аудит (P0) + диеты с LLM-контролем
- **P0-блокеры устранены**: httpx 0.28.1+openai 1.39 несовместимы → pyproject pin `httpx<0.28`, requirements.txt/lock перегенерированы (openai==1.59.9, httpx==0.27.2, lock без системного мусора); CSRF login→dashboard (dashboard перевыпускал cookie после рендера → `ensure_csrf_cookie` только при отсутствии); safety gate LLM (промпт subtasks 3-5 смягчён, abstract-контекст больше не раскрывает имена из истории, `entity_name` заменяется каноническим серверным).
- **Целостность**: `GET /` больше не 500 (get_optional_user при прямом вызове); schedule rule с UUID entity_id; interrupted training-задачу нельзя завершить (+XP) — `complete_once` атомарный `UPDATE...WHERE status='pending'` + unique-индекс ledger (миграция 019); `activity_logs.completed_at` добавлена (импорт).
- **Cross-user**: `/points/balance` не отдаёт чужие thresholds; импорт Entity ищет по имени с учётом owner/public.
- **Ops**: Secure-куки в production, logout только POST (форма в base.html), TTL-очистка raw payload (scheduler, каждые 6ч), переключатели llm_mode (full/abstract) + store_raw в UI конфигов, Dockerfile включает seed/cli, runbook → /register /login, CI: ruff==0.5.7 pin + docker build job.
- **Диеты v2 (LLM)**: `Diet.direction` (направление), журнал фактического потребления `diet_consumptions` (CRUD), LLM-генерация диеты (`POST /diets/api/generate`), LLM-оценка adherence + корректировка плана (`POST /diets/api/{id}/evaluate`, add/modify/remove по имени, score 0-100).
- **Найден и починен латентный баг**: `SYSTEM_PROMPT_TEMPLATE` с неэкранированными `{}` падал при `.format()` — generate_task всегда бы крашился.
- Артефакты: миграция 019 (PG15 upgrade/downgrade/ORM проверены), tests/test_audit_s55.py (+17), 291/291 тестов, ruff ✅.

## 2026-08-06 — Сессия 1: Интервью (базовое)
- Обсуждали: скоуп, пользователи, язык UI, деплой, LLM, провайдеры, ошибки LLM, штрафы, тесты, UI, админка, приватность, геймификация, каталог, уведомления, AGENTS.md, подписки, сессии, бэкапы, логи.
- Артефакты: `tracker-spec.md`.

## 2026-08-06 — Сессия 2: Открытые вопросы
- Решения: aiogram 3.x, Omniroute+Groq+OpenRouter, простая регистрация, кастомная геймификация, locale.
- Артефакты: разделы «Решённые/Осталось открытым» в спеке.

## 2026-08-06 — Сессия 3: AGENTS.md + Telegram-бот
- AGENTS.md переработан, бот: 6 команд, вебхук, уведомления, код-привязка.
- Артефакты: новый AGENTS.md, раздел 8 спеки.

## 2026-08-06 — Сессия 4: Сессии/штрафы, каталог, доска достижений
- Детализация механик: сессии created/active/ended, штрафы с эскалацией, комбо, челленджи, каталог 30+, доска.
- Артефакты: разделы 9–11 спеки.

## 2026-08-06 — Сессия 5: Система памяти
- Созданы memory/*, правила чтения/обновления.
- Артефакты: 7 memory-файлов, правка AGENTS.md.

## 2026-08-06 — Сессия 6: Phase 1 — Фундамент
- Проект, Docker, FastAPI, User, Alembic, JWT, i18n, темы, шаблоны, тесты.
- Артефакты: 40 файлов.

## 2026-08-06 — Сессия 7: Phase 2 — Каталог и конфиги
- Entity, OptIn, LLMProviderConfig, шифрование, CRUD, seed, админка.
- Артефакты: +14 файлов (всего 56).

## 2026-08-06 — Сессия 8: Phase 3 — LLM-пайплайн
- ActivitySession, ActivityLog, Context Builder, OpenAI-клиент, JSON repair, tool calling, /tasks.
- Артефакты: +12 файлов (всего 68).

## 2026-08-07 — Сессия 9: Phase 4 — UI, сессии, геймификация
- UserProgress, Achievement, Notification, XP-движок, дашборд v2, доска, уведомления, сессии, приватность, Telegram-бот.
- Артефакты: +16 файлов (всего 84).

## 2026-08-07 — Сессия 10: Тесты и линтинг
- Ruff 181→0 ошибок, 73 теста, JSONB→JSON, pyproject.toml.
- Артефакты: +7 тестовых файлов.

## 2026-08-07 — Сессия 11: Training (тренировки)
- TrainingDay, subtasks, LLM-промпты, pipeline, геймификация training mode.
- Артефакты: +6 файлов.

## 2026-08-07 — Сессия 12: Points v2 + Measurements + Inventory + Schedule + Import
- Points v2 engine, gamification_config JSON, PenaltyConfig, ScheduleRule, BodyMeasurement, InventoryItem, Import module, Seed v2, 100 тестов.
- Артефакты: +15 файлов (всего 105).

## 2026-08-07 — Сессия 13: Import/Export + Charts + Layout fix
- Import/export: 8 типов шаблонов, CSV/JSON upload, API-push, full backup, CLI, веб-страница
- Charts: 2 новых API (category-breakdown, completion-rate), 4 графика на дашборде, графики на training/sessions/achievements
- Layout: компактная вёрстка всех страниц (chart heights ÷2, padding сокращён)
- Docker: исправлены миграции, nginx.conf, порты 8080/8443, SSL-сертификаты
- Git: инициализирован, 3 коммита запушены на GitHub
- Артефакты: +3 файла (import_data.html, cli.py), изменены 10+ шаблонов

## 2026-08-07 — Сессия 14: Calendar + Schedule Timeline + Интеграция
- Calendar: 3 модели (CalendarTemplate, AvailabilityWindow, CalendarOverride), Entity.intensity
- API: CRUD + `/calendar/check` + `is_available()` + `get_day_schedule()`
- LLM-интеграция: календарь в context_builder → промпт
- Веб: `/calendar` с timeline-баром, `/tasks` с индикатором доступности
- Schedule: weekly timeline chart (горизонтальные бары по дням)
- Миграция 007
- Тесты 105/105
- Артефакты: +5 файлов (calendar модель, схема, API, шаблон, миграция), изменены 6 файлов

## 2026-08-07 — Сессия 15: Penalty & Points v2 — штрафы и баллы
- PenaltyRedemption: модель + миграция 008 — отслеживание отработок штрафов
- Redemption API: список pending, complete (возврат баллов), skip
- Handler: авто-создание PenaltyRedemption при прерывании задачи
- PointsProfile: CRUD + назначение на сущность + удаление
- Threshold effects: уведомления при пересечении порогов (negative/warning/good)
- Gamification editor: PUT /entities/{id}/gamification
- Points page: redemption list с Complete/Skip, профили, назначение
- Тесты 105/105, ruff 0 ошибок
- Артефакты: +1 модель, +1 миграция, изменены handler, API, шаблон

## 2026-08-07 — Сессия 16: Telegram Bot v2 — реальный бот
- Полный реврайт app/telegram/bot.py: 8 команд с реальной логикой
- /next вызывает LLM-пайплайн (generate_task), показывает карточку с inline-кнопками
- /done и /interrupt интегрированы с gamification handler (XP, streak, points, PenaltyRedemption)
- /stats показывает реальную статистику из БД (XP, level, streak, points)
- /session показывает статус активной сессии
- /settings переключает язык (inline EN/RU кнопки)
- Привязка аккаунта: 6-значный код через /profile/telegram-link-code, /link CODE
- User.telegram_chat_id, telegram_link_code, telegram_link_code_expires (миграция 009)
- Уведомления: send_telegram_notification() + хук _send_tg_notifications в gamification handler
- Webhook: авто-регистрация при старте (setup_webhook в lifespan)
- Дашборд: карточка «Link Telegram» с JS (generateLinkCode, checkTelegramStatus)
- config: tg_bot_username, tg_webhook_base_url
- Тесты 105/105, ruff 0 ошибок
- Артефакты: +1 миграция, переписан bot.py, изменены handler, dashboard, main, config, user model, dashboard шаблон

## 2026-08-07 — Сессия 17: Polling-режим бота
- Добавлен tg_polling флаг в config (True = локальная разработка, False = production webhook)
- start_polling(): удаляет webhook, запускает dp.start_polling() как фоновую asyncio задачу
- stop_polling(): graceful cancel при shutdown приложения
- lifespan: автоматический выбор webhook/polling по флагу
- Использование: tg_polling=true + tg_bot_token=xxx в .env
- Артефакты: изменены bot.py, main.py, config.py

## 2026-08-07 — Сессия 18: Auto-Analysis Scheduler
- Фоновый триггер авто-анализа тренировок: asyncio loop, проверяет время каждую минуту
- В `tg_auto_analysis_time` (по умолчанию 23:00 UTC) сканирует все TrainingDay со статусом active/planned
- Для каждого вызывает `analyze_training_day` (LLM-анализ + генерация плана на завтра)
- Без внешних зависимостей (без APScheduler) — чистый asyncio
- Запуск/остановка в lifespan: `start_auto_analysis()` / `stop_auto_analysis()`
- Артефакты: +1 файл (scheduler.py), изменены config.py, main.py

## 2026-08-07 — Сессия 19: v0.7 Аудит и интервью (R0)
- Прочитаны REMEDIATION_SPEC.md (внешний аудит, 18 дефектов) и AGENTS_.md (новая инструкция)
- Интервью по 6 ключевым архитектурным решениям:
  1. Штрафы — оставить как есть (ADR-029)
  2. LLM-режимы — full + abstract, настраивается в провайдере (ADR-030)
  3. Entity — оставить единой моделью (ADR-031)
  4. Training — оставить отдельной страницей (ADR-032)
  5. Вторичные модули — оставить в главном меню (ADR-033)
  6. raw_llm_response — опциональное хранение + usage-метрики отдельно (ADR-034)
- AGENTS.md обновлён: приоритет документов, LLM-режимы, актуальные фазы
- AGENTS_.md удалён
- DECISIONS.md: +6 ADR (029–034)
- CONTEXT.md: убран «код не написан»
- STATUS.md: секция v0.7 Audit & Interview
- Артефакты: изменены AGENTS.md, DECISIONS.md, CONTEXT.md, STATUS.md, SESSIONS.md; удалён AGENTS_.md

## 2026-08-07 — Сессия 20: R1 — воспроизводимость (часть 1)
- pyproject.toml: единый источник зависимостей, bcrypt<4.1, python-dotenv
- requirements.txt: перегенерирован из pyproject.toml
- Версия: 0.5.0 → 0.7.0 (pyproject.toml + main.py)
- create_all: оставлен с предупреждением (Alembic для production)
- Артефакты: изменены pyproject.toml, requirements.txt, main.py
- CI: .github/workflows/ci.yml (ruff lint + pytest на PostgreSQL 15)
- Миграции: subtasks String→JSON, next_day_suggestion Text→JSONB — расхождения зафиксированы, не блокируют (create_all создаёт правильные типы)

## 2026-08-07 — Сессия 21: R2 — Безопасность и авторизация
- CSRF: двойная кука (csrf_token), HTMX auto-include X-CSRF-Token, meta tag в base.html
- Идемпотентность: complete_once/interrupt_once в app/security.py, применены в /tasks
- Отдельный ключ шифрования: CREDENTIALS_ENCRYPTION_KEY ≠ JWT_SECRET_KEY
- Безопасные cookies: HttpOnly для access_token, path=/, очистка при logout
- OwnershipChecker: хелпер для проверки владельца объекта (создан, ждёт применения)
- base.html: добавлен блок scripts (требование DESIGN.md)
- Артефакты: +1 файл (security.py), изменены auth, tasks, config, encryption, dashboard, main, base.html

## 2026-08-07 — Сессия 22: R3 — Роли, object-level auth, scheduler
- User.role + миграция 010 (user/moderator/admin), require_admin() dependency
- OwnershipChecker применён: tasks, training, sessions, achievements, notifications
- /admin защищён — обычный пользователь получает 403
- unacceptable → strong_aversion: model, schemas, pipeline, tests
- Soft scheduler: app/services/scheduler.py — get_due_practices, set_next_due, set_retry_block
- UserEntityOptIn: next_due_at, retry_not_before_at (миграция 011)
- Tasks: показаны due practices, авто next_due/retry после complete/interrupt
- Артефакты: +4 файла (2 миграции, scheduler, services/__init__), изменены 9 файлов

## 2026-08-07 — Сессия 23: R4 — LLM planner + фиксы типов
- LLMProviderConfig.llm_mode (full/abstract) — переключается в настройках провайдера
- context_builder: format_context_abstract() для opaque-режима (только ID и категории)
- app/llm/validator.py: валидация entity_id в allowed set, схемы параметров
- Pipeline: авто-выбор формата по llm_mode, валидация после парсинга
- Deterministic fallback: /tasks/generate-deterministic — выбор из due practices без LLM
- tasks.html: список due practices с цветовой кодировкой, кнопка fallback
- Миграция 012: subtasks String→JSON, next_day_suggestion Text→JSONB — типы исправлены
- Артефакты: +2 файла (validator.py, миграция 012), изменены 4 файла

## 2026-08-07 — Сессия 24: R5 — Frontend shell
- active_nav: переменная во всех шаблонах, подсветка текущей страницы в навигации
- Навигация упрощена: dashboard, tasks, training, catalog, points, admin
- CSRF hidden поля в формах переключения языка/темы
- innerHTML аудит: всё использование — рендеринг серверных данных (безопасно)
- scripts блок в base.html
- active_nav проброшен в dashboard, tasks, training
- Артефакты: изменены base.html, dashboard.py, tasks.py, training.py

## 2026-08-07 — Сессия 25: R6 — Object-level auth для вторичных модулей
- security.py: require_entity_owner() — хелпер проверки владельца Entity (owner_id)
- points_v2.py: update_gamification_config + assign_profile_to_entity — проверка владельца
- calendar.py: create_override — проверка владельца template
- Полный аудит всех эндпоинтов: остальные уже фильтруют по user_id
- Тесты 105/105, ruff 0, Docker smoke OK
- Артефакты: изменены security.py, points_v2.py, calendar.py

## 2026-08-07 — Сессия 26: DESIGN.md compliance — дашборд, графики, вёрстка
- DESIGN.md — 600+ строк дизайн-системы (уже существовал, переименован из DESING.md)
- base.html: убраны градиенты, emoji из навигации, animate-fade-in из main
- dashboard_v2.html: полный редизайн — 4 графика, solid индикаторы, SVG иконки, DESIGN.md палитра
- training.html: SVG checkmark, solid progress ring, компактный график
- sessions.html/schedule.html: timeline без градиентов, light mode
- measurements/calendar/points/inventory: light+dark тема, semantic токены
- Убраны дубликаты Chart.js CDN из 4 шаблонов
- 522 insertions, 704 deletions — чистое сокращение кода
- 105 тестов, ruff 0, Docker smoke ok
- Артефакты: изменены 9 шаблонов HTML

## 2026-08-07 — Сессия 27: R0-R6 переаудит — критические исправления
- Внешний аудит выявил оставшиеся P0-дефекты после R0-R6
- CSRF: verify_csrf header-less bypass исправлен (было: if header AND mismatch; стало: if NO header OR mismatch)
- CSRF: подключена как HTTP middleware в main.py (вне lifespan)
- CSRF: пропускает запросы без access_token cookie
- create_all(): полностью удалён из lifespan — Alembic единственный путь
- requirements.lock: 102 пакета, pip freeze
- Миграция 014: subtasks String→JSONB, meta→JSONB, boolean defaults 0/1→false/true
- Object-level auth: get_gamification_config + toggle_opt_in (is_public|owner_id), delete_window (JOIN template.user_id)
- Идемпотентность: training complete_training_task теперь проверяет статус
- XSS: escapeHtml() в base.html, экранирование в inventory/schedule/points/calendar/measurements
- HTMX listener: document.addEventListener('DOMContentLoaded', ...)
- CDN: FIXME-комментарии, план на локальную сборку
- conftest.py: auth_headers включает csrf_token cookie + X-CSRF-Token header
- main.py: очищены неиспользуемые импорты (engine, Base, logger)
- training.py: next_day_suggestion Text→JSON, pipeline хранит dict
- opt_in.py: UniqueConstraint(user_id, entity_id)
- Миграция 013: training_days FK, opt-in unique, active session partial index
- 105/105 тестов с CSRF, ruff 0, format clean, Docker ok
- Артефакты: +2 миграции, +requirements.lock, изменены 12 файлов

## 2026-08-07 — Сессия 28: Cross-user auth тесты + README
- test_cross_user_auth.py: 22 теста межпользовательской авторизации
  - Entity gamification config: чтение/обновление приватных практик → 404
  - Entity opt-in: нельзя подписаться на приватную практику → 404
  - Calendar: удаление чужих окон/шаблонов, создание override на чужом шаблоне → 404
  - Schedule rules: удаление чужих правил → 404
  - Inventory: обновление/удаление чужих предметов → 404
  - Points profiles: удаление чужих профилей → 404
  - Penalty redemptions: завершение чужих отработок → 404
  - Sessions: старт/стоп чужих сессий → 303 (status unchanged)
  - Notifications: отметка чужих уведомлений → 303 (is_read unchanged)
  - LLM configs: удаление чужих конфигов → 404
  - Training: завершение/переключение чужих задач → 404
  - Tasks: complete/interrupt чужих логов → 404
  - Admin: не-админ GET /admin/ → 403, POST /admin/seed-entities → 403
  - CSRF: POST без X-CSRF-Token → 403
- CSRF middleware fix: HTTPException → JSONResponse (try/except в main.py)
  - Раньше HTTPException из verify_csrf пропагировался необработанным
  - Теперь возвращает JSONResponse с кодом 403
- SQLite-совместимость в тестах: time(9,0) вместо "09:00", /admin/ с trailing slash
- README.md: полная документация (описание, структура, установка, архитектура, API, конфигурация, разработка)
- 127/127 тестов, ruff 0, format clean, Docker ok
- Артефакты: +1 тестовый файл, +README.md, изменены main.py, STATUS.md

## 2026-08-07 — Сессия 29: CDN → локальные статические файлы
- 3 CDN-ссылки в base.html заменены на локальные /static/... файлы:
  - `https://cdn.tailwindcss.com` → `/static/tailwindcss.js` (407 KB)
  - `https://unpkg.com/htmx.org@2.0.0` → `/static/htmx.min.js` (49 KB)
  - `https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js` → `/static/chart.umd.min.js` (205 KB)
- Dockerfile уже копирует app/ → static-файлы автоматически в образе
- Нет внешней сетевой зависимости во время работы приложения
- Проверка: curl -sk /static/* → HTTP 200 для всех трёх, главная страница — 0 CDN refs
- 127 тестов, ruff 0, Docker ok
- Артефакты: +3 статических файла в app/static/, изменён base.html

## 2026-08-07 — Сессия 30: Интеграционные тесты + Обновление зависимостей
- test_scheduler.py (8 тестов):
  - _parse_time: 6 параметризованных кейсов (23:00, 00:00, 12:30, 06:05, leading spaces, overflow 25:99)
  - Scheduler lifecycle: start/stop без ошибок, double-start идемпотентен
  - Training day lifecycle: создание через API (не 404), статусы, связь с ActivityLog
  - Multiple training days: несколько дней на одного пользователя
  - Auto-analysis: noop когда нечего анализировать, находит active дни
  - Cross-user isolation: запрос анализа не смешивает пользователей
- test_telegram_bot.py (10 тестов):
  - POST /profile/telegram-link-code → 6-символьный код, сохраняется в БД
  - Expiry: 25-35 минут, SQLite naive datetime
  - GET /profile/telegram-status: linked false/true
  - Bot get_user_by_chat: found/not found (прямой SQL без импорта из bot.py)
  - _require_user логика: linked user найден, unlinked → None
  - Webhook: без секрета → bot not configured
  - send_telegram_notification: False когда бот не настроен
  - Кросс-пользовательская изоляция кода привязки
- requirements.txt + requirements.lock: перегенерированы (102 пакета)
- 153/153 тестов, ruff 0, format clean, Docker ok
- Артефакты: +2 тестовых файла, обновлены requirements.txt + requirements.lock

## 2026-08-08 — Сессия 31: CI GitHub Actions — переработка
- pyproject.toml: добавлен [build-system] (setuptools + wheel) для `pip install .[dev]`
- CI переработан: 3 job'а вместо 2:
  - **lint** — ruff check + format check для app/, cli.py, tests/, seed_prod.py
  - **test** — pytest с SQLite (был PostgreSQL-сервис, но тесты его не использовали)
  - **migrations** — Alembic upgrade → downgrade → upgrade на PostgreSQL 15
- seed_prod.py: ruff fix (unused `pts` → `_pts`)
- 153/153 тестов, ruff 0, format clean
- Артефакты: изменены .github/workflows/ci.yml, pyproject.toml, seed_prod.py

## 2026-08-08 — Сессия 32: CI fix — зелёные job'ы
- CI запущен, lint ✅, но test ❌ и migrations ❌
- **test**: 3 теста repair падали — `json_repair` на Python 3.11 успешно «чинил» plain text в JSON-строку, тесты ожидали исключение
- **migrations**: downgrade 014 — `SET DEFAULT 0` на boolean колонке, PostgreSQL требовал `false`
- Исправления:
  - `app/llm/repair.py`: добавлена проверка типа результата (dict/list) после каждой стратегии repair
  - `alembic/versions/014`: boolean defaults `0`→`false`, `1`→`true` в downgrade
- Все 3 job'а зелёные: lint ✅ test ✅ migrations ✅
- Артефакты: изменены app/llm/repair.py, alembic/versions/014_fix_migration_types.py

## 2026-08-09 — Сессия 33: Обновление статических файлов
- HTMX: 2.0.0 → 2.0.10 (51KB, +2KB) — bugfix release
- Chart.js: 4.4.0 → 4.5.1 (209KB, -27KB) — минорное обновление
- TailwindCSS: v3 → v4.3.3 (282KB, -125KB) — мажорная версия (@tailwindcss/browser@4)
  - Убран `tailwind.config = { darkMode: 'class' }` — v4 использует `class`-стратегию по умолчанию
  - Шаблоны совместимы: нет deprecated opacity-утилит, @apply, @layer
  - CSS-first конфигурация (@theme) не требуется для текущего использования
- 153/153 тестов, ruff 0
- Артефакты: обновлены 3 статических файла в app/static/, изменён base.html

## 2026-08-09 — Сессия 34: Подготовка релиза 0.8.0 + Docker smoke-test + README
- Версия: 0.7.0 → 0.8.0 (pyproject.toml + main.py)
- `.env.example`: добавлены CREDENTIALS_ENCRYPTION_KEY, TG_BOT_TOKEN, TG_WEBHOOK_SECRET, TG_WEBHOOK_BASE_URL, TG_BOT_USERNAME, TG_POLLING, TG_AUTO_ANALYSIS_TIME
- `docker-compose.yml`: добавлены все недостающие env vars, nginx — опциональный профиль `full`, app порт 8000 проброшен на хост, depends_on заменён на pg_isready wait-loop, postgresql-client добавлен в Dockerfile
- `seed_prod.py`: argparse (--email, --database-url), читает DATABASE_URL из env
- `docker-compose.override.yml`: dev-окружение (SQLite, hot-reload, polling Telegram, без postgres/nginx)
- **Docker smoke-test**: db + app подняты, все эндпоинты проверены:
  - `/healthz` → 200 "ok"
  - `/static/htmx.min.js` → 200, 51KB
  - `/static/chart.umd.min.js` → 200, 209KB
  - `/static/tailwindcss.js` → 200, 282KB
  - `/` → 200, 7.6KB HTML
- **README**: секция Deployment — хост-nginx + certbot + docker compose, бэкапы pg_dump, seed
- 153/153 тестов, ruff 0, format clean
- Артефакты: +1 docker-compose.override.yml, изменены 8 файлов

## 2026-08-09 — Сессия 35: Деплой на VPS + Seed тренировки
- Остановлен старый nginx-контейнер, запущены db + app (port 8000 → host)
- Host nginx: конфиг для tracker.gorbunovr.ru создан в `/tmp/practice-loop-nginx.conf` (ждёт sudo reload)
- Training day: создан в БД с полным расписанием гидратации (воскресенье, 24ч график, микро-сливы, ночной блок)
- Обнаружен пробел: нет inline-полей для ввода реальных данных (объёмы, временные интервалы, секунды микро-сливов)
  - ActivityLog.subtasks — только чекбоксы (is_done), нет value-полей
  - ActivityLog.selected_params — только LLM-параметры, не для ручного ввода
  - ActivityLog.planned_value/actual_value — строковые поля, не используются в training UI
  - BodyMeasurement — только физические замеры (вес, обхваты)
- 153/153 тестов, CI зелёный
- Артефакты: +1 скрипт seed_training.py, конфиг nginx

## 2026-08-09 — Сессия 40: Deferred-фиксы (P0 production gate, bif, JS i18n) — В ПРОЦЕССЕ

Цель: закрыть оставшиеся deferred пункты из Сессій 37 + 39.

### Этап 2 ✅ — AGENTS.md bif-комментарий
Добавлена секция 0 «Архитектурный bif v0.8-actual ↔ v0.7-spec» в AGENTS.md: явная таблица 6 пунктов расхождения + ссылки на ADR-029, ADR-031, ADR-032, ADR-033, ADR-034. Зафиксировано требование «при работе следуй коду; при пересмотре — отмена ADR явно».

### Этап 3 ✅ — Production gate в config.py
`app/config.py`: добавлен `app_env` + `@model_validator`, который в production отвергает `change-me-...` placeholder-ы и секреты длиной <32. TG_WEBHOOK_SECRET проверяется только если установлен TG_BOT_TOKEN.

`docker-compose.yml`: `APP_ENV: ${APP_ENV:-production}` — то есть по умолчанию в compose-сборке включён gate.

`docker-compose.override.yml`: принудительно `APP_ENV: development` для dev-окружения.

Новый файл `tests/test_config.py`: 11 тестов:
- `TestAppEnv`: default development, нормализация регистра/пробелов
- `TestProductionGate`: dev принимает placeholders, production отклоняет JWT/ENCRYPTION/TG_WEBHOOK, length ≥32 enforced, error message перечисляет все нарушители

Все 11 проходят ✅.

### Этап 4 ✅ — store_raw_response flag (REM §7.5)
- `alembic/versions/016_add_store_raw_response.py`: миграция добавила поле `llm_provider_configs.store_raw_response BOOLEAN DEFAULT TRUE` + `activity_logs.raw_response_expires_at TIMESTAMPTZ NULL` + индекс на expires_at.
- `app/models/llm_config.py`: добавлено поле `store_raw_response` (default True, как ADR-034 сохраняет backwards-compat).
- `app/models/activity_log.py`: добавлено поле `raw_response_expires_at` (nullable, indexed).
- `app/llm/pipeline.py`: helper `_resolve_raw_response(config, raw)` возвращает `(raw, expires)` в зависимости от `store_raw_response` + TTL 30 дней (константа `RAW_RESPONSE_TTL_DAYS`). Применён во все 3 точки сохранения ActivityLog.
- `app/schemas/llm_config.py`: добавлен `store_raw_response: bool = Field(default=True)` в `LLMConfigCreate` / `LLMConfigUpdate` / `LLMConfigResponse`.
- `app/api/llm_configs.py`: form принимает `store_raw_response` (true/false/on/1/yes parsing).
- `app/templates/llm_configs.html`: показывает LLM mode и store_raw_response; 🤖 emoji заменён на SVG.
- Новый файл `tests/test_llm_raw_response_policy.py`: 5 тестов (сохраняем с TTL, дроп при отключении, дроп при отсутствии атрибута, дроп для empty raw, sanity TTL в [7,90] дней).
- Все 5 тестов ✅.

### Этап 5 ✅ — Расширение LLM validator (REM §7.4)
- `app/llm/validator.py`: новая функция `validate_params_against_schema(params, schema)` — рекусивно проверяет:
   - тип (`number` / `integer` / `string` / `boolean`);
   - диапазоны min/max для number+integer;
   - длины min_length/max_length для строк;
   - `enum` для строк (whitelist значений);
   - `optional` для всех ключей (default false);
   - `PARAMS_NOT_DICT` для неправильных типов контейнера;
   - `UNKNOWN_PARAM_TYPE` для опечаток в schema.
- В `app/llm/pipeline.py` после `validate_llm_response` (top-level) вызывается `validate_params_against_schema`, используя `params_schema` из `context[allowed_entities]`.
- Новый файл `tests/test_llm_validator.py`: 32 теста (4 на top-level + 28 параметризованных на schema validation).
- Все 32 ✅.

### Этап 6 ✅ — dashboard_v2 refactor (DESIGN §11 ≤2 графика)
- `app/templates/dashboard_v2.html` (368→ранее): теперь 4 графика → 2 канваса (Weekly Activity + Points Trend) + 2 compact summary cards (categories + completion).
- Ровно 2 chart-elements per viewport согласно DESIGN.md §11.
- Completion Rate сжат в одну карточку: «big number + цвет» + пару строк completed/total.
- Categories сжаты в top-3 bar list с %.
- Все capture-JS используют переводы через `t.*` + escapeHtml в JS (mini-SSR escape).
- `app/i18n/en.py` + `app/i18n/ru.py`: +37 ключей (nav_training/tasks/sessions/import/calendar/points/inventory/notifications/achievements, dashboard_points/xp/streak/days_suffix/done/level_label/active_session/loading/link/no_categories/browse_catalog/others/completion_completed/total/see_history/chart_weekly/chart_points_trend/chart_categories_title/chart_completion_title/chart_last_7/chart_last_30/chart_done/chart_stop/chart_pending/telegram_connected/code_ready/not_linked/link/code_valid/code_hint/new_code/open_bot, notifications_title, achievements_title).
- Шаблон рендерится (28 KB), синтаксис в порядке.

### Этапы 7+8 ✅ — calendar.html & inventory.html JS async i18n
- `app/templates/calendar.html`: заменены все hardcoded EN тексты → `{{ t.calendar_* }}` ключи (today's legend, header titles, intensity select, day-of-week selector, policy selector); JS использует инжектированный `I18N` dict + `POLICY_LABEL` map; все user-controlled values проходят через `escapeHtml()`; новый `calendar_btn_delete` = «Удалить»/«Delete».
- `app/templates/inventory.html`: аналогично — All/Clothing/Equipment/Cosmetics/Shopping List → `t.inventory_filter_*`; status badges используют `STATUS_LABEL` map; placeholder'ы, кнопки и labels → i18n; новый блок `inv_*` ключей с RU переводами; `STATUS_LABEL` + `I18N` инжектируются Jinja из статических переводов (безопасны).
- Добавлены ключи в en.py + ru.py: `inventory_filter_shopping_list`, `inv_btn_add`, `inv_btn_add_new_item`, `inv_btn_save`, `inv_btn_delete`, `inv_ph_category/name/qty/qty_needed/priority`, `inv_shopping_list`, `inv_chart_breakdown`, `inv_qty_label`, `inv_priority_label`, `inv_empty`, `inv_mark_shopping`, `inv_items_counter_suffix`, `inv_status_need/ordered/bought/built/other`. 31 ключ.
- Шаблоны рендерятся (calendar 20 KB, inventory 19 KB), синтаксис OK.

### Этап 9 ✅ — import_data.html: localhost:8443 → config + i18n + emoji removal
- `app/api/import_data.py`: добавлен `app_url` в контекст шаблона — `str(request.url_root).rstrip("/")`.Проиходит из `request`, deployments не привязаны к localhost.
- `app/templates/import_data.html`:
     - hardcoded `https://localhost:8443` заменены на `{{ app_url }}` в clipboard-button и в curl-примере;
     - hardcoded EN/RU тексты → `t.import_*` ключи (`import_title`, `import_subtitle`, `import_data_types`, `import_section_templates`, `import_section_upload`, `import_section_export`, `import_drop_hint`, `import_or`, `import_file_label`, `import_autodetect_hint`, `import_submit`, `import_full_backup`, `import_download_all`, `import_api_title`, `import_api_desc`, `import_api_example_title`, `import_api_types_line`).
     - Все эмодзи 📦📥📤📁🚀🔄⬇️🔌 заменены на SVG-иконки (DESIGN.md 6.3).
     - Градиент `from-indigo-50 to-purple-50` → solid `bg-indigo-50`.
     - aria-live на upload-result, aria-label на copy-URL, type="button" на всех кнопках (CSRF-safe).
- 17 новых ключей в en.py + ru.py.
- Шаблон рендерится (16 KB), синтаксис OK.

### Этап 10 ✅ — XSS-fixture тесты (REM §A14)
- Новый файл `tests/test_xss_fixtures.py`: 24 XSS-защитных теста в 4 фазах:
   1. **Jinja autoescape**: подтверждена, что `{{payload}}` в HTML-аттрибуте/content рендерит контент безопасно;
   2. **escapeHtml** (mirror base.html): 8 параметризованных тестов на OWASP payloads (script tag, img onerror, mouseover, javascript URI, unicode, None, int, двойное экранирование);
   3. **end-to-end**: `calendar.html` / `inventory.html` рендер враждебного ввода через Jinja autoescape — `<script>` всегда заменяется на `&lt;script&gt;`;
   4. **регрессия**: 10 известных payload-ов из OWASP cheat sheet (svg/onload, iframe/src, body/onload, input/autofocus, ERB/Jinja/JS-инъекции).
- Все 24 ✅.

### Этап 11 ✅ — финальная валидация
- `ruff check app/ cli.py tests/ seed_prod.py` → All checks passed! ✅
- `ruff format --check app/ cli.py tests/ seed_prod.py` → 86 files already formatted ✅ (после autoformat)
- `python3 -m pytest tests/` → **225 passed in 38.49s** ✅ (было 153 → +72 новых: 11+5+32+24)
- Все P0/P1 из предыдущих сессий закрыты.

## 2026-08-09 — Сессия 39: Frontend-фиксы (P0/P1 из аудита)

- Выполнены все рекомендации из FRONTEND_AUDIT_SESSION_38.md
- **P0-баг**: catalog.html — enum `unacceptable → strong_aversion` (миграция ADR-029 не покрыла UI-слой)
- i18n: добавлено ~50 новых ключей в en.py + ru.py; удалён 1 дубль `catalog_no_entities_hint`
- training.html: 8 RU строк → t.* + CSRF + aria-label
- Градиент в index.html удалён; SVG иконки вместо эмодзи
- Эмодзи удалены из заголовков: admin, llm_configs, catalog, notifications, privacy, my_entities, tasks, dashboard
- Hover-translate и shadow-lift убраны с 16+ карточек
- base.html: CSS variables (light/dark), skip-link, ARIA, focus ring, motion easing (`cubic-bezier`), 44px touch target, `aria-live`, `aria-current="page"`
- Градиент в achievements.html → solid
- **Результат**: 153/153 теста ✅, ruff ✅, format ✅
- Детальный отчёт: `memory/FIX_SESSION_39.md`
- Артефакты: +~200 строк в i18n, изменены 15 шаблонов

## 2026-08-09 — Сессия 38: Frontend-аудит (по запросу владельца)

- Прочитан DESIGN.md (694 строки) — приоритетный документ для frontend.
- Прочитаны все 22 шаблона (2914 строк).
- Проверки: `grep 'innerHTML'` 18 вхождений / 8 файлов; `grep 'aria-|role='` 0; `grep 'bg-slate|bg-gray'` 465 строк; `grep 'hover:-translate|hover:shadow-lg'` 21 нарушение DESIGN.md 6.3; `grep 'csrf_token'` 4 формы из ~25.
- Ключевая находка: `app/templates/catalog.html` всё ещё использует enum `unacceptable` после миграции на `strong_aversion` (ADR-029). Это **P0-баг**: CSS ветка в строке 74 не сработает + нет option для нового значения.
- Найдены hardcoded RU/EN строки вне `t.*` словаря в training.html (8 строк RU), dashboard.html, index.html, catalog.html, calendar.html.
- 0 ARIA атрибутов во всех 22 шаблонах (нет aria-label, aria-current, aria-live, skip-link).
- DESIGN.md compliance ≈30%.
- Результат: `memory/FRONTEND_AUDIT_SESSION_38.md` (полный отчёт), SESSIONS/STATUS/OPEN_QUESTIONS обновлены.
- Код НЕ изменён. Изменения отложены в Сессию 39.

## 2026-08-09 — Сессия 37: Аудит проекта (по запросу владельца)

- Прочитаны все priority-документы: REMEDIATION_SPEC.md (676), AGENTS.md (219), DESIGN.md (694), tracker-spec.md (409), README.md (304), все 7 memory/* файлов.
- Снят срез кода: main.py, security.py, entity.py, api/tasks.py, llm/pipeline.py, llm/validator.py, services/scheduler.py, config.py, alembic/versions/* (15 миграций), .github/workflows/ci.yml, docker-compose.yml.
- Проверки: `rg create_all|metadata.create` — пусто; `rg innerHTML` — 18 совпадений в 8 файлах; `rg eval(` — только htmx; `python3 -m pytest --collect-only` — 153 теста.
- Бриф-интервью: владелец выбрал bif (REMEDIATION_SPEC.md остаётся целевой, ADR-029–034 — зафиксированный компромисс v0.8-actual) и «эта сессия — только аудит».
- Результат: `memory/AUDIT_SESSION_37.md` (полный отчёт), SESSIONS.md, STATUS.md, OPEN_QUESTIONS.md (Q7) обновлены.
- Код НЕ изменён. Изменения AGENTS.md/конфига отложены в Сессию 38.
- Артефакты: +1 memory-файл, изменены SESSIONS/STATUS/OPEN_QUESTIONS.

## 2026-08-09 — Сессия 42: Troubleshooting «port already in use»

- Симптом пользователя на VPS: `failed to bind host port 127.0.0.1:8000/tcp: address already in use` при `docker compose up -d --build`.
- Диагностика: `docker compose ps -a` + `sudo ss -ltnp \| grep ':8000'` + `docker ps -a --format ...` — чтобы найти, кто держит порт (предыдущий контейнер, uvicorn напрямую, или неправильный профиль).
- Cleanup: `docker compose down --remove-orphans` × 3 профиля + `sudo fuser -k 8000/tcp` как ядерный вариант + повторный `up` с консциентным `--profile prod` (или `--profile full`).
- Добавлена секция **13.1 Troubleshooting** в `DEPLOY_VPS.md` (идентичный копипаста-стиль, как и весь runbook).
- CHANGELOG.md: строка для сессии 42.

## 2026-08-09 — Сессия 43: Troubleshooting «порт свободен, но bind всё равно падает»

- Продолжение Сесси 42: пользователь подтвердил, что `ss -ltnp | grep ':8000'` пусто, но Docker всё равно падает на старте.
- Три причины, не зависящие от видимого LISTEN-сокета:
  - **A. iptables residue** — `DOCKER` и `DOCKER-USER` цепочки в `nat` сохраняют DNAT-правила после экстренной остановки контейнера. Фикс: `sudo iptables -t nat -F DOCKER DOCKER-USER` + повторный up.
  - **B. App crash loop** — Docker бронирует bind ДО реального старта приложения. Если app сразу крашится (production gate, миграция, race с db), повторная попытка стартует с предыдущим сокетом ещё «занятым». Фикс: `docker compose up -d db` → дождаться pg_isready → `up -d app --no-deps`.
  - **C. Conflict имени сети `tracker_default`** — если на VPS два клона проекта, оба хотят одну сеть и bind сосуществуют глобально. Фикс: `docker compose --project-name tracker1 ... up`.
- Добавлена секция **13.2 Troubleshooting** в `DEPLOY_VPS.md` с диагностическим all-in-one блоком.
- CHANGELOG.md: строка для сессии 43.

## 2026-08-09 — Сессия 41: VPS Deployment runbook (DEPLOY_VPS.md)

- Создан `DEPLOY_VPS.md` в корне проекта — standalone копипаста-инструкция для развёртывания на боевом VPS.
- **Структура:** 14 шагов (предусловия, DNS, каталог, секреты, .env, сборка, миграции, регистрация, nginx+certbot, seed, Telegram, бэкапы, обновление, аварийные команды, чек-лист «всё ОК»).
- **Каждый шаг — только bash-блоки**, минимум prose между ними. Подходит для чтения на втором мониторе и копирования блок за блоком.
- Ссылка добавлена в `README.md` (раздел Deployment) и в этот SESSIONS.
- Артефакты: +1 файл в корне (`DEPLOY_VPS.md`), изменён README.md.

## 2026-08-09 — Сессия 36: TrainingLogEntry — журнал тренировки
- **Модель** `app/models/training_log.py`: TrainingLogEntry (time_label, entry_type, planned/actual_value, unit, notes, sort_order, is_extra)
- **Миграция** 015: таблица `training_log_entries`
- **API** (3 эндпоинта):
  - `POST /training/log-entry/{id}` — обновление actual_value + notes (inline HTMX)
  - `POST /training/log-entry` — добавление внеплановой записи (is_extra=True)
  - `DELETE /training/log-entry/{id}` — удаление внеплановой записи
- **UI**: training.html — inline-формы для каждой строки журнала (факт + заметки), кнопка «+ Добавить запись» с выбором типа (приём/микро-слив/давление/заметка)
- **Seed**: 27 записей по расписанию гидратации (fluid_intake, micro_leak, general_note)
- 153/153 тестов, ruff 0
- Артефакты: +3 файла (модель, миграция, seed_training.py), изменены training.py + training.html
## 2026-08-10 — Сессия 44: исправление предрелизного Docker Compose

- Воспроизведён crash loop app: Alembic выполнялся на SQLite из автоматически подмешанного `docker-compose.override.yml` и падал на `entities.tags` типа PostgreSQL `JSONB`.
- Автоматический override удалён; dev-настройки перенесены в `docker-compose.dev.yml`, подключаемый явной парой `-f`.
- Docker dev и production теперь используют PostgreSQL; hot reload и bind mounts сохранены только в явной dev-конфигурации.
- Ожидание БД переведено на compose health dependency; удалён хардкод `tracker` из shell wait-loop.
- Проверено: обе compose-конфигурации успешно рендерятся, image собирается, PostgreSQL healthy, Alembic 001–016 проходит, Uvicorn стартует, `/healthz` возвращает `ok`.
- Проверки host toolchain: pytest под системным Python 3.13 завис на первом auth-тесте и был остановлен; ruff обнаружил 15 ранее существовавших замечаний в миграциях 015/016 и `seed_training.py`.

## 2026-08-10 — Сессия 45: SSL через Cloudflare (Origin Certificate вместо certbot)

- Пользователь: домен через CF, certbot не установлен / не нужен. Прежний §8 DEPLOY_VPS.md описывал единственный путь через `certbot --nginx`.
- **DEPLOY_VPS.md §0**: certbot убран из обязательного `apt install`; перенесён в опциональный комментарий.
- **DEPLOY_VPS.md §8** переработан в три ветки:
  - **8.🅰️ Cloudflare Proxied (🟠 orange cloud) → CF Origin Certificate** (15 лет, автопродление не требуется).
    - CF Dashboard: SSL/TLS → Full (НЕ Strict для Origin Cert).
    - Сгенерировать Cert + Key в SSL/TLS → Origin Server → Create (Hostnames: tracker.your-domain.com, *.tracker.your-domain.com).
    - Положить в `/etc/ssl/cloudflare/tracker.your-domain.com.{pem,key}` с правами 600/644.
    - Конфиг nginx: `ssl_certificate /etc/ssl/cloudflare/...pem`, заголовки HSTS/Frame-Options/Referrer-Policy по Mozilla Intermediate; proxy_pass в upstream `tracker_app { 127.0.0.1:8000 }`; `X-Real-IP $http_cf_connecting_ip` (CF подставляет реальный IP клиента).
  - **8.🅱️ Cloudflare DNS-only (⚪ grey cloud) → Let's Encrypt через certbot + dns-cloudflare плагин**.
    - Создать CF API Token → Edit zone DNS.
    - `sudo apt install certbot python3-certbot-dns-cloudflare`.
    - `/etc/letsencrypt/cloudflare.ini` с токеном (chmod 600).
    - `certbot certonly --dns-cloudflare --dns-cloudflare-credentials ... --agree-tos -m ... -d ... -d '*.your-domain.com'`.
    - cron автопродления через DNS-01 — порт 80 не нужен.
  - **8.🅲️ Без CF → certbot standalone** (требует открытого порта 80).
- **DEPLOY_VPS.md §8.4**: новая таблица типичных ошибок CF SSL (Error 520/521/522/526).
- **DEPLOY_VPS.md §10.3**: убрана формулировка "certbot работают" → "SSL работают".
- Без правок кода / миграций / тестов — чисто runbook-only.


## 2026-08-10 — Сессия 46: §8.🅰️ — пошаговая навигация по CF Dashboard

- Пользователь подтвердил: 🟠 orange cloud (CF Proxied). Не помнит, где создать Origin Certificate.
- **DEPLOY_VPS.md §8.🅰️** развёрнут в пошаговую инструкцию click-by-click:
  1. `https://dash.cloudflare.com/` → кликни на свой домен.
  2. Левая панель → **SSL/TLS**.
  3. Подменю SSL/TLS → **Origin Server** (не Edge Certificates).
  4. Кнопка **Create Certificate**.
  5. Форма: RSA/ECDSA, hostnames, 15 years → Next.
  6. Скопировать Certificate + Private Key (PEM). **Private Key один раз.**
- Перед созданием: SSL/TLS → Overview → Encryption mode = **Full** (не Strict — Origin Cert не trusted).
- DNS-проверка `dig +short` (ответ CF-IP → Proxied ✅).
- Sanity-check пары: `openssl ... -modulus | openssl md5` для обоих — должны совпадать.
- Удалён дубль секции «Сохрани сертификаты на VPS» (после рефактора осталась старая версия).
- Без правок кода / миграций / тестов — чисто runbook-only.


## 2026-08-10 — Сессия 47: nginx literal bugs поверх установки tracker.gorbunovr.ru

- Домен пользователя: `gorbunovr.ru`, в CF уже есть CF Origin Cert с wildcard `*.gorbunovr.ru` + `gorbunovr.ru` (2 hosts в SAN).
- Дам готовый скрипт под реальное имя (а не плейсхолдер) — пользователь копирует и запускает.

### бага 1 (emerg) — старая конфигурация practice-loop активна
- `nginx -t` падает на `/etc/nginx/sites-enabled/practice-loop:2`, где ссылка на несуществующий `/etc/nginx/ssl/origin.pem`.
- Фикс: `sudo rm -f /etc/nginx/sites-enabled/practice-loop`. Возможны ещё артефакты в sites-available.

### баг 2 (warn) — устаревший синтаксис http/2
- На nginx 1.25+ (Ubuntu 24.04) `listen 443 ssl http2;` deprecated → директива `http2 on;` отдельно.
- **DEPLOY_VPS.md §8.🅰️** (строки 283-285) и **§8.🅱️** (строки 401-403) — обновлено на современный синтаксис.
- Применён `sed` к VPS-конфигу.

### Тонкость: nginx в compose vs host
- Если в docker compose активирован `tracker-nginx-1` (--profile full), он конкурирует за 443 с host-nginx. Два варианта:
  - A. Хост-nginx + отключить compose nginx (`docker compose stop tracker-nginx-1`).
  - B. Compose nginx + хост-nginx не активен (старая practical-loop в /etc/nginx/sites-enabled отключена вручную).

### Checklist новой версии §8
- Современный http2 синтаксис — без warning
- Чёткий single-pass flow: убери старую конфигурацию → положи сертификат → nginx -t → reload
- Упоминание wildcard case (*.gorbunovr.ru) как пример «уже есть CF cert»


## 2026-08-10 — Сессия 48: Фикс CSRF (нативные формы, контекст шаблонов, JS fetch)

- Пользователь: клик по кнопке смены темы → `{"detail":"CSRF token missing or invalid"}` на `/settings/theme`.
- **Причина 1**: `verify_csrf()` проверяла только заголовок `X-CSRF-Token` (его подставляет HTMX из meta-tag). Кнопки темы/локали — **нативные HTML-формы**: токен уходит в теле запроса (`csrf_token` hidden input), заголовка нет → всегда 403. Константа `CSRF_FORM_FIELD` была объявлена, но нигде не использовалась. Тесты не ловили: фикстура `auth_client` всегда шлёт заголовок.
- **Фикс 1** (`app/security.py`): `verify_csrf` стала async, добавлен фолбэк на поле формы (double-submit cookie) — только для content-type `form-urlencoded`/`multipart` (JSON-тела не буферизуются на пути отказа); неверный/отсутствующий токен → fail-closed 403. Подводный камень Starlette 1.4.1: `request.form()` парсит через `stream()` и НЕ заполняет `request._body` → `wrapped_receive` реплеит downstream пустое тело (422 «Field required»). Обход: сначала `await request.body()`. `main.py`: `await verify_csrf(request)`.
- **Причина 2 (найдена при проверке всех форм)**: `csrf_token` в контекст шаблона передавали только `main.py` (home) и `dashboard.py` — на ВСЕХ остальных страницах hidden-поля и HTMX meta-тег рендерились пустыми → все нативные формы (tasks, training, catalog, sessions, llm_configs, my_entities, achievements, notifications, admin, privacy) и HTMX-запросы получали 403. **Фикс 2**: context processor в `templates_setup.py` (`Jinja2Templates(context_processors=[...])`, поддерживается Starlette 1.4.1) инжектит `csrf_token` из cookie в каждый рендер.
- **Причина 3**: JS-страницы (points, schedule, measurements, inventory, calendar, telegram-link на dashboard) слали `fetch(..., {method:'POST'})` без заголовка CSRF → 403. **Фикс 3**: обёртка `window.fetch` в base.html авто-добавляет `X-CSRF-Token` для same-origin state-changing запросов (учтены `Request`-объекты; внешние origin исключены).
- **Тесты** (+4 в `tests/test_auth.py`): нативная форма темы → 303 + `user.theme == "light"` (с явным commit — тестовая фикстура переопределяет get_db без авто-commit), нативная форма локали → 303 + `user.locale == "ru"`, неверный `csrf_token` поля → 403, meta-тег с токеном на `/tasks/`. Хелпер `_auth_cookie_headers` возвращает `(headers, csrf)`.
- Избыточные явные `csrf_token` в контекстах `main.py` (home) и `dashboard.py` удалены — их полностью заменяет context processor.
- **Тесты JS-fetch сценария** (+2): JSON POST `/api/v2/points/profiles` с `X-CSRF-Token` → 200 + профиль создан (проверка через GET), без заголовка (только cookie) → 403.
- **231/231 тестов ✅**, ruff ✅, format ✅.


## 2026-08-10 — Сессия 49: аудит-фиксы training (entity/subtasks, partial plan, stored XSS)

- Пользователь процитировал аудит: «Принимаются чужая private entity и произвольные придуманные subtasks; частично созданный план коммитится после ошибки LLM и блокирует повторную попытку; новый журнал допускает stored XSS через entry_type. См. training.py».

### 1. Чужая entity + произвольные subtasks (app/llm/pipeline.py, generate_daily_plan)
- **Было**: план принимал ЛЮБОЙ `entity_id` (никакой проверки против allowed-набора, в отличие от `generate_task`) и любые subtasks как строки.
- **Стало**: каждый task проверяется — `entity_id` обязан быть в `get_allowed_ids(context)` (опт-ин набор; чужая private entity → `ValueError`, план целиком отклонён); `params` валидируются через `validate_params_against_schema` (schema из context); subtasks — только строки, кап `SUBTASK_LIMIT=20` / `SUBTASK_MAX_LENGTH=500`.

### 2. Частичный план после ошибки LLM (транзакционность)
- **generate_daily_plan**: TrainingDay создаётся только ПОСЛЕ парсинга и валидации (раньше — flush до LLM-вызова → при ошибке `get_db` коммитил пустой «planned» день → повтор блокировался «Plan already exists»).
- **generate_plan**: при повторе день удаляется, если он пустой (нет ActivityLog И TrainingLogEntry) — это чинит и старые закоммиченные leftover'ы.
- **analyze_training_day**: все мутации (`analysis_summary`, `status`, `next_day_suggestion`, usage-счётчики) отложены до успеха ОБОИХ LLM-вызовов — раньше при падении второго вызова день коммитился как «completed» с анализом, но без suggestion.
- Endpoint-rollback НЕ добавлялся: общие тестовые сессии (fixture) делали rollback опасным; транзакционность решена на уровне пайплайна.

### 3. Stored XSS через entry_type (журнал)
- **add_extra_log_entry**: allowlist `ENTRY_TYPES` — значение вне списка коэрсится в `general_note`.
- **_render_log_entry_row** (HTMX-рендер): экранированы label `tl` и `unit` (раньше сырые f-строки; шаблон training.html и так автоэкранирует — но HTMX-фрагмент — нет).
- `time_label` ограничен 20 симв. (колонка String(20), иначе DataError на PostgreSQL).

### Тесты (+8, 231→239)
- Чужая private entity → план отклонён, ничего не сохранено.
- Параметры вне `params_schema` (intensity=99 при max=3, с `"type": "integer"`) → отклонено.
- Ошибка LLM → нет частичного дня, повтор не блокируется.
- Leftover-день заменяется валидным планом (проверка logs/subtasks в БД).
- Второй LLM-вызов падает → день остаётся `active`, без analysis/next_day_suggestion.
- `entry_type="<script>..."` → сохранён как `general_note`, без тегов в HTML.
- Валидный тип (`pressure_check`) проходит.
- `_render_log_entry_row` экранирует все user-поля (прямой unit-тест).
- **239/239 тестов ✅**, ruff ✅, format ✅.


## 2026-08-10 — Сессия 50: геймификация — 500 на Stop с redemption, состояние complete/interrupt, расписание

- Пользователь процитировал аудит: «Stop отвечает 500, запись остаётся pending — ветка с redemption-конфигом делает await синхронной функции»; «Прерванную задачу можно затем завершить и получить награду; повторные Complete/Interrupt продолжают менять расписание».

### 1. Stop → 500 (app/gamification/handler.py)
- **Было**: `redemption_action = await _get_redemption_action_from_config(config)` — `await` на синхронной функции → `TypeError` → 500, `PenaltyRedemption` не создавался, запись оставалась `pending`.
- **Стало**: `redemption_action = _get_redemption_action_from_config(config)` (sync, без await); redemption-запись создаётся корректно.

### 2. Целостность состояний (app/security.py, complete_once)
- **Было**: `complete_once` блокировал только уже `completed` → прерванную задачу можно было завершить и получить награду.
- **Стало**: обрабатывается только статус `pending` — `interrupted`/`completed` → idempotent-ответ без наград. `interrupt_once` не менялся (блокирует completed/interrupted).

### 3. Повторные Complete/Interrupt меняли расписание (app/api/tasks.py)
- **Было**: `set_next_due`/`set_retry_block` вызывались всегда → каждый повторный запрос двигал `next_due_at`/`retry_not_before_at`.
- **Стало**: вызываются только при `not result["idempotent"]` — реальном изменении состояния.

### 4. Telegram-бот (app/telegram/bot.py)
- **Было**: команды /done, /interrupt, /tasks искали статус `active` (не существует — задачи создаются `pending`) → всегда «нет задач»; inline-хендлеры `done:`/`int_confirm:` не проверяли статус.
- **Стало**: запросы по `status == "pending"`; на inline-хендлерах статус-гард (`log.status != "pending"` → «Task already finished», без наград/повторного штрафа).

### Тесты (+4, 239→243)
- Прерывание задачи с redemption-конфигом не падает и создаёт `PenaltyRedemption` (clothespins, points_value>0).
- После interrupt `complete` → 303, статус остаётся `interrupted`, `total_completed == 0`, `next_due_at` не двигается.
- Повторный complete не меняет `next_due_at`; повторный interrupt не меняет `retry_not_before_at`.
- **243/243 тестов ✅**, ruff ✅, format ✅.


## 2026-08-10 — Сессия 51: PostgreSQL JSONB-фикс + удаление хардкод-пароля из истории

- Пользователь процитировал аудит: «В чистой схеме migration 006 создаёт JSON-поля как Text, тогда как ORM и seed передают словари. Offline SQL строится, но чистый PostgreSQL seed с высокой вероятностью упадёт»; «В публичных seed-файлах находятся персонализированные чувствительные данные и жёстко заданный пароль БД… данные останутся в Git history».

### 1. Migration 006 создаёт JSON как Text (PostgreSQL)
- **Найдено**: `entities.gamification_config` и `points_profiles.config` созданы в 006 как `sa.Text()`, модели объявляют `JSON`, seed шлёт dict. На чистой PostgreSQL asyncpg не может адаптировать dict → вставка падает. (`points_transactions.meta` уже починен в 014.)
- **Фикс — миграция 017**: обе колонки → `postgresql.JSONB` с `postgresql_using="...::jsonb"` (каст legacy Text-JSON). Для `points_profiles.config` сначала `server_default=None` — иначе PG: «default for column cannot be cast automatically to type jsonb»; потом тип + `'{}'::jsonb`.
- **Валидация**: поднят временный postgres:15-alpine, чистая схема → `alembic upgrade head` (001–017) ✅; legacy Text-строки вставлены ДО 017 и успешно скастованы при upgrade ✅; ORM dict-inserts/reads (`Entity.gamification_config`, `PointsProfile.config`) ✅. Контейнер удалён после проверки.

### 2. Хардкод-пароль в seed-файлах (приватность)
- **Найдено**: `tracker_dev_2024` в `seed_prod.py` (default `--database-url`) и `seed_training.py` (`os.environ.setdefault`). Запушен на GitHub (`github.com/ghostcar/practice-loop`), в истории (коммиты 12736e8, 474177a).
- **Фикс**: оба скрипта — fail-fast: без `DATABASE_URL` → понятная ошибка + `sys.exit(1)`. `seed_prod.py`: проверка ПОСЛЕ `parse_args()` (ревью-фикс: сначала парсинг, потом валидация — иначе флаг `--database-url` был мёртвым кодом).
- **Git history scrub** (пользователь одобрил force-push): `git filter-repo --replace-text` (правило `tracker_dev_2024==>REDACTED_DB_PASSWORD`), force-push `main`. Проверка: `git log -S tracker_dev_2024 --all` пуст. Бэкап до переписывания: `/tmp/tracker-backup-20260810-0724.bundle`. **ВНИМАНИЕ: все хэши коммитов изменились.**
- **Памятка владельцу** (вне кода): если `tracker_dev_2024` использовался на VPS — ротация пароля БД обязательна (пароль был публично доступен в GitHub): `openssl rand -base64 24` → новый пароль в `.env` на VPS + `ALTER USER tracker PASSWORD '...'` + `docker compose up -d db app`. Seed-данные (замеры тела, инвентарь, план гидратации) владелец решил оставить как есть.

### Тесты (+5, 243→248)
- `TestSeedScriptsNoHardcodedCredentials` в `tests/test_config.py`: пароль не в файлах; нет `user:pass@` в connection string (regex); fail-fast через subprocess (seed_training без env → exit 1; seed_prod с `--database-url` при пустом env проходит проверку креденшелов и падает на коннекте — флаг не мёртвый).
- **248/248 тестов ✅**, ruff ✅, format ✅.


## 2026-08-10 — Сессия 53: страница /import — навигация + UX для ручной работы

- Пользователь: «сделаем отдельную страницу удобную для ручной работы — скачать шаблон, загрузить файл с данными».
- **Найдено**: страница `/import` уже существует (роут + `import_data.html`) со скачиванием шаблонов/загрузкой/экспортом/API-доками, но на неё НЕТ ссылки в навигации (nav: dashboard/tasks/training/catalog/points/admin) — потому пользователь её не видел. Пользователь выбрал «доработать + добавить в навигацию» (не новую страницу).

### Сделано
- **base.html**: ссылка `Import` в nav (`{{ t.nav_import }}` — ключ уже существовал в i18n) + подсветка активной вкладки.
- **app/api/import_data.py**: `active_nav: "import"` в контекст; **фикс латентного краша** — `str(request.url_root)` → `str(request.base_url)` (в Starlette 1.4.1 `url_root` не существует; раньше открытие /import падало бы с AttributeError — тестов на страницу не было).
- **import_data.html**: карточки шаблонов с подсказкой «Колонки:» (поля в code-блоке); upload-зона — drag&drop с подсветкой при dragenter/dragover, отображение имени выбранного файла, кнопка Import disabled до выбора файла; обработчик `htmx:afterSwap` парсит JSON-ответ `/import/upload` и рендерит баннер результата (зелёный: N строк импортировано + M пропущено; красный: `import_result_error` + `data.detail` — раньше HTMX вставил бы сырой JSON текстом).
- **i18n**: +4 ключа (import_fields_hint, import_result_imported, import_result_skipped, import_result_error) в en/ru.
- **Тесты (+2)**: /import рендерится (nav-ссылка, aria-current, drop-zone, upload-result, download-ссылки csv/json); API-эндпоинт `/import/template/entities?format=csv` отдаёт CSV с Content-Disposition.
- **253/253 тестов ✅**, ruff ✅, format ✅. Ревью: ошибки импорта теперь показывают реальный текст (data.detail), а не «Error».


## 2026-08-10 — Сессия 52: CSRF 403 на /admin/seed-entities — старый образ + формы без hidden-поля

- Пользователь: обновил контейнеры после смены пароля БД, но `/admin/seed-entities` → `{"detail":"CSRF token missing or invalid"}`.

### Диагноз: две причины
1. **Контейнер крутит старый образ** (`docker compose up -d` без `--build`). Проверка `docker exec tracker-app-1 grep ...`: в `/app/app/security.py` есть `CSRF_FORM_FIELD` (был объявлен и до S48), но НЕТ `async def verify_csrf`, в `templates_setup.py` НЕТ context processor — это код до Session 48. Dockerfile `COPY app/` запекает код в образ при сборке; `up -d` лишь пересоздаёт контейнер из того же образа. → нужен `docker compose up -d --build`.
2. **Код: 7 шаблонов с native POST-формами без hidden `csrf_token`** — admin (seed-entities, seed-llm-presets), achievements (hide), llm_configs (set-active, delete, add), my_entities (create, publish, delete), notifications (read), privacy (delete), sessions (new, start, end). В Session 48/39 hidden-поля добавили только в tasks/training/catalog/base — остальные пропущены, поэтому на деплое даже с новым кодом эти POST-формы дают 403 (native-форма не шлёт заголовок X-CSRF-Token).

### Фикс
- Добавлены `<input type="hidden" name="csrf_token" value="{{ csrf_token or '' }}">` во все 14 форм (7 шаблонов). login.html/register.html сознательно не тронуты — неаутентифицированные запросы пропускают CSRF (нет access_token cookie).
- **+3 регрессионных теста**: `test_all_native_post_forms_have_csrf_hidden_field` (статическая проверка всех шаблонов: каждый method=post содержит hidden, login/register exempt); `test_admin_seed_with_form_csrf_token_passes` (admin POST /admin/seed-entities с form-encoded csrf_token → 303 + сущности реально созданы); `test_admin_seed_without_csrf_field_rejected` (без поля → 403). Ревью: эвристика теста упрощена (slice до первого `</form>`, nested forms запрещены валидным HTML).
- **251/251 тестов ✅**, ruff ✅, format ✅.

### Действие владельца (деплой)
- На VPS: `cd ~/tracker && git pull && docker compose up -d --build` — именно `--build`, чтобы образ пересобрался с новым кодом (иначе старый код продолжит давать 403).

## 2026-08-10 — Сессия 54: drag&drop, изображения, фото-отчёты, диеты, параллельные тренировки
- Обсуждали: внедрение drag&drop «везде», изображения инвентаря, фото-отчёты по активностям, концепт диет (несколько под разные цели, комбинирование), вывод нескольких тренировок на одном экране.
- Решения владельца: изображения — диск + Docker volume; диеты — отдельные таблицы (диета → продукты/правила); параллельные тренировки — гибрид (несколько планов на дату + объединённая timeline-шкала).
- **Drag&drop**: журнал тренировки (reorder-эндпоинт, `sort_order` уже существовал), инвентарь (partial reorder — работает с фильтрами; unknown id → 400), позиции диет. `sort_order` добавлен в schedule_rules и availability_windows (миграция 018) — UI-перетаскивание там отложено.
- **Изображения инвентаря**: `image_path` + upload/delete эндпоинты (валидация content-type + magic-bytes, 8 МБ лимит), превью + 📷 в inventory.html, drag&drop строк.
- **Фото-отчёты**: таблица `attachments` (owner_type allowlist), API upload/list/delete, UI на карточках задач training.html. `delete_upload` — защита от path traversal (resolve + префикс).
- **Диеты**: `diets` + `diet_items`, CRUD + reorder + toggle `is_active` (комбинирование = несколько активных одновременно), страница `/diets` в навигации.
- **Параллельные тренировки**: `training_days.name`, `/training/plan` теперь добавляет второй план вместо блокировки, `analyze_day` по `training_day_id`, страница: колонки планов + timeline-шкала дня (lane-packing JS, clamp 0..1440).
- **Инфраструктура**: `config.upload_dir`/`max_upload_bytes`, docker-compose volume `uploads`, mount `/uploads` + CSRF-bypass, `.gitignore uploads/`, `app/services/uploads.py`.
- **Миграция 018** проверена на реальном PostgreSQL 15: upgrade 001→018, ORM-вставки/чтения, downgrade 018→017, повторный upgrade — всё ✅. Временный контейнер удалён.
- **+21 тест** (`tests/test_dnd_diets_uploads.py`). Ревью поймало: partial-inventory-reorder (с фильтром), path traversal в delete_upload, мёртвый код (non_empty, oldName, legacy context, unused Request), clamp времени timeline — все исправлены.
- **274/274 тестов ✅**, ruff ✅, format ✅. Коммит после этой записи.


### Session 75 — 2026-08-12 (Social S4+S6)
- **S4 — Verification & Comments:** 5 new tables (verification_policies, verification_requests, verification_votes, social_comments, social_encouragements), migration 032
- Quorum-based verification: min_approvals → verified, max_rejections → review_required, deadline → no_quorum_action
- Comments CRUD with edit support, encouragements (4 types: thumbs_up, support, celebrate, motivate)
- 8 API endpoints: /social/verification page, verify/create, vote with quorum, comment create/edit/delete, encourage
- /social/verification page (dashboard with request list, vote form, comments section)
- +28 i18n keys EN/RU
- **S6 — Tracker Adapter:** app/platform/social/adapters.py — TrackerSocialAdapter (14 protocol methods), TimerSocialAdapter (skeleton)
- TrackerAdapter: authorize_subject (ActivityLog + Entity), build_redacted_projection (safe snapshots), list_shareable_capabilities, validate_grant_constraints
- Adapters registered at startup in main.py via composition flags
- 538/538 ✅ · ruff ✅ · migration 032 ✅ · deployed

## 2026-08-13 — Сессия 111: полный аудит проекта без изменений кода

- Выполнен read-only review архитектуры, backend, security/privacy, LLM pipeline, media,
  тестов/CI/Docker/Nginx и frontend/UX/a11y на HEAD `5ae8cc2`.
- Создан `docs/audits/PROJECT_REVIEW_2026-08-13.md`: оценки качества, 2 P0, 7 P1, 4 P2,
  сильные стороны и remediation roadmap Gate A–D.
- P0: `/uploads` смонтирован публично в обход owner-authorized media API; пустой production
  `CHALLENGE_HMAC_KEY` использует известный `default-challenge-key`.
- Проверки: ruff/format/compileall/Compose config/Alembic single head/facts-check ✅;
  memory lint 0 errors + 3 denylist warnings; собрано 661 test. Полный pytest summary в текущем
  execution environment не получен, поэтому новое утверждение 661/661 не фиксировалось.
- Исходный код, миграции и runtime-конфигурация не изменялись; новых ADR нет.
