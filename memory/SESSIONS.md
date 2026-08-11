# Журнал сессий

Формат: `дата — Сессия N: тема` → что обсуждали → результаты/договорённости → артефакты.
Новая запись добавляется **в конце каждой сессии**.

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
