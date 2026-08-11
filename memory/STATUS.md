# Текущий статус

Обновляется **в конце каждой сессии**. Последнее обновление: 2026-08-11 (сессия 65 — C3+C4+C5 execution services).

## LockTimer — C0 ✅ + C1+C2 ✅ + C3+C4+C5 ✅

- [x] **C0**: APP_PRODUCT_VARIANT, feature flags, ProductComposition, capabilities endpoint, User.timezone, conditional nav, ADR 047–052.
- [x] **C1 Domain**: 6+7+10 enums/state machines, domain utils (duration/clamp, canonical JSON+SHA256, deterministic random, seed, occurrence keys, safety stop).
- [x] **C2 Persistence**: 12 таблиц lock_*, миграция 025 (PG15 ✅), owner-scoped repositories.
- [x] **C3 Draft/Start**: create/update draft, add/delete rules, atomic start (conditional UPDATE+rowcount, snapshot+hash, materializer chaining).
- [x] **C4 Materializer**: 5 slot + 6 task schedule types, rolling horizon 90 days, deterministic random scheduler.
- [x] **C4 Job Runner**: enqueue (idempotent), claim (SELECT FOR UPDATE SKIP LOCKED, lease).
- [x] **C5 Slots**: open (eligibility+late-open extension), close — with audit.
- [x] **C5 Tasks**: reveal (scheduled→visible), submit, complete (idempotent), skip — with audit.
- [x] **C5 Penalties**: allowlisted types + idempotency key, add_time with cap/max_end.
- [x] **C5 Safety Stop**: active→safety_stopped + cancel future occurrences.
- [x] **C5 Outbox**: transactional domain events.
- [x] **ADR** 047–054 записаны.
- [x] **Тесты**: 479/479 ✅ (+60 LockTimer), ruff ✅, format ✅.

**Осталось по LockTimer**: C6–C9 (media/LLM/UI/hardening) → Platform Social

## Сессия 63 (C0): Platform Foundation + composition root + три варианта приложения

- [x] **Q2 (стартовый набор 30+)**: `SEED_ENTITIES` = 30 задач (спека §10.5) — **закрыт**.
- [x] **Q4 (Telegram-тексты)**: формат реализован (Markdown-уведомления всех типов + inline) — **закрыт**.
- [x] **Q8 (backend audited defects)**: дублирует Q10, всё закрыто в S40/S55/S57 — **закрыт**.
- [x] **Q11 (новая модель активностей, S58–S62)**: полный цикл завершён — **закрыт** (итоговый статус в OPEN_QUESTIONS.md).
- [ ] ⏸ Отложены до публичного доступа: Q5 (оплата/тарифы), Q6 (рейт-лимиты).

## Сессия 62: «всё по порядку» — коммит 59–61, PG15-валидация 023, деплой-проверка, Phase 2 остаток (LLM/gamification)

- [x] **Коммит кода сессий 59–61** (`c0d30a5`) — всё рабочее дерево (37 файлов) зафиксировано: update2.md справочники + update.md Phase 3 UI.
- [x] **Миграция 023 на реальном PostgreSQL 15**: временный контейнер postgres:15-alpine — upgrade 001→023 ✅, ORM-цикл (все 9 новых таблиц: BodyPart/TaskBodyTarget/ActivityBodyPartRequirement, TaskLocation/Usage/Requirement, InventoryCategory, TaskInventoryUsage/Requirement + InventoryItem) ✅, downgrade 023→022 ✅, повторный upgrade ✅. Контейнер удалён.
- [x] **Деплой подготовлен**: seed-кнопки `/admin/seed-references` (body_parts/locations/inventory_categories) и `/admin/seed-entities` (categories) на месте; Dockerfile `COPY app/` включает все seed-файлы; runbook: `git pull && docker compose up -d --build` + `alembic upgrade head` + кнопки seed.
- [x] **Phase 2 остаток (LLM-адаптация planned/actual)**: transition API (ADR-040) теперь интегрирован с soft-scheduler (`set_next_due` на completed/partial, `set_retry_block` на skipped/cancelled/stopped — только при не-идемпотентном переходе); `actual_parameters` валидируются против entity.params_schema (400 при невалидных); `build_context`/промпты включают actual_parameters из истории (LLM видит факт, не только план); `on_task_completed` читает intensity из actual (fallback planned), Points v2-бонусы оцениваются по actual params.
- [x] **Ревью-фиксы**: идемпотентность планировщика (повторные POST не двигают расписание); JS коэрция number-полей в actual_parameters (числа как числа); тавтологический тест заменён на реальный async-тест handler'а.
- [x] **Проверки**: 419/419 тестов ✅ (+5), ruff ✅, format ✅, compile ✅, node --check ✅.

## Сессия 61 (update.md Phase 3 UI): фильтры категорий, динамическая форма параметров, быстрые действия, карточка выполнения, статистика

- [x] **Каталог с фильтрами по категориям (ADR-035)**: catalog_page переведён на нормализованную таблицу `ActivityCategory` — иерархическое дерево (root + подкатегории), фильтр по `category_id` с включением потомков (`_category_and_descendants`), fallback legacy `?category=` для старых ссылок; название категории на карточке из `category_rel.title`; `create_entity` принимает `category_id`.
- [x] **Динамическая форма параметров (ADR-041)**: `GET /tasks/params-form` (partial) рендерит поля из `normalize_schema` по типам (string/text/integer/decimal/duration/boolean/enum+allow_custom_value/multi_enum/selectors) с `prefix` для planned/actual; `POST /tasks/create` — ручное создание задачи (planned) с типизированными параметрами, `validate_params`, title через `generate_title` (ADR-042), planned_comment.
- [x] **Быстрые действия (ADR-040)**: в tasks.html каждая задача получает кнопки допустимых переходов из `STATUS_TRANSITIONS` (start/complete/partial/skip/cancel/stop/review/reactivate/…), клик → `POST /api/v2/tasks/{id}/transition`; граф `next_actions` рендерится серверно.
- [x] **Карточка выполнения**: для completed/partially_completed открывается форма с actual-параметрами (lazy-загрузка params-form c prefix=actual_) + completion_comment; `TransitionIn.actual_parameters` + `completion_comment` + `completed_at` сохраняются на бэкенде.
- [x] **Статистика по статусам**: `status_stats` (GROUP BY status) — чипы в tasks.html (planned/completed/in_progress/stopped/skipped/partial/review/total).
- [x] **JS**: tasks.js переписан — загрузка формы параметров при выборе сущности, init selector-полей в динамических формах, быстрые действия, карточка выполнения, CSRF-fetch; фикс бага `selInv` (пропущенная `;` из оригинала).
- [x] **i18n**: +35 ключей EN/RU (tasks_manual_*, tasks_form_*, tasks_action_*, tasks_complete_*, tasks_stats_*).
- [x] **Тесты**: +13 (`tests/test_phase3_task_ui.py`) — фильтры категорий (root/child/legacy), params-form (типы, prefix, cross-user 404), create manual (planned, валидация, cross-user), transition с actual_parameters (completed/partial), задачи-страница (быстрые действия + статистика). **414/414 ✅**.
- [x] **Ревью-фиксы**: `_coerce_param` аннотация → object; сбор custom-значения enum (`param_{key}_custom`); маппинг `planned`-действия → `tasks_action_reactivate`; мёртвые i18n-ключи убраны из шаблона.
- [x] **Проверки**: ruff ✅, format ✅, compile ✅, node --check ✅, полный pytest 414 ✅.

## Сессия 60 (update2.md, финал): селекторы в форме задачи, фильтры истории, полный прогон 401 тестов

- [x] **Селекторы (Preferences) в форме генерации задачи** (`tasks.html`): секция с body_part / location / inventory селекторами — значения передаются как form fields в `/tasks/generate` → `generate_task()` принимает `body_part_id`/`location_id`/`inventory_item_id`, инжектит их в промпт LLM (предпочтения выбора) + создаёт `TaskBodyTarget`/`TaskLocationUsage`/`TaskInventoryUsage` после создания ActivityLog.
- [x] **Фильтр-бар истории задач** (`tasks.html` + `tasks.py`): 4 select'а — статус / зона тела / место / предмет; `applyFilter()` строит URL с query-параметрами; бэкенд фильтрует SQL (exists-подзапросы через link-таблицы, без N+1).
- [x] **JS в отдельные модули (DESIGN §15.4)**: инлайн-скрипты вынесены в `static/js/pages/tasks.js` (новый — селекторы + фильтры), `body_parts.js`, `locations.js`; тест `test_no_inline_scripts_in_pages` (test_audit_s57) проходит.
- [x] **Тест-фиксы**: `test_cannot_edit_system_location` — системные локации (owner_id NULL) дают 404 (не 403) из-за owner-фильтрации; slug'и зон в тестах сверены с реальным seed (`torso_buttocks`, `torso_chest`, `abs`).
- [x] **Финальная валидация**: полный `pytest tests/` — **401 passed ✅** (130s); ruff check ✅; ruff format (1 файл `import_data.py` переформатирован); py_compile по всем app/tests/alembic ✅.

## Сессия 59 (update2.md): справочники BodyPart / TaskLocation / InventoryCategory, DSL-селекторы, API, тесты, UI, импорт

- [x] **Модели**: `BodyPart` (иерархический справочник зон тела, 40 seed), `TaskBodyTarget` (связь задачи с зонами: роль, сторона, интенсивность, snapshot), `TaskLocation` (системные + пользовательские места, privacy_level, location_type, 25 seed), `TaskLocationUsage` (связь задачи с местами, snapshot), `InventoryCategory` (нормализованный справочник 16 категорий), `TaskInventoryUsage` (связь задачи с инвентарём: роль, quantity, snapshot), `ActivityBodyPartRequirement` / `ActivityLocationRequirement` / `ActivityInventoryRequirement` (шаблонные требования Activity к справочникам).
- [x] **InventoryItem**: +`inventory_category_id` FK, +`inventory_status` (available/in_use/cleaning/charging/maintenance/unavailable/archived — operational-измерение), старый `status` (shopping: need/ordered/bought/built) сохранён.
- [x] **Миграция 023**: 9 новых таблиц + 2 колонки в `inventory_items`.
- [x] **DSL расширен (ADR-046)**: 3 новых типа в `app/params.py` — `inventory_selector` (single/multiple mode), `body_part_selector`, `location_selector` — с нормализацией и валидацией.
- [x] **Seed**: `body_parts` (40 иерархических зон), `locations` (25 системных мест), `inventory_categories` (16 категорий) — все идемпотентны; новый endpoint `POST /admin/seed-references`.
- [x] **API (23 эндпоинта)**: `app/api/references.py` + `app/schemas/references.py` — BodyPart (плоский список, дерево, фильтр по body_system), TaskLocation (CRUD пользовательских, архив, проверка ссылок → 409), InventoryCategory (список), TaskBodyTarget/TaskLocationUsage/TaskInventoryUsage (batch-replace атомарно + auto-snapshot), Inventory available (фильтр по категории + operational-статусу), Task search (11 фильтров: status, body_part_id, body_system, location_id, location_type, inventory_item_id, inventory_category_slug, session_id, training_day_id, date_from, date_to, limit/offset).
- [x] **UI**: `body_parts.html` (иерархическое дерево ▸/▾, поиск, фильтр по системе, индикатор чувствительных зон), `locations.html` (список + поиск + фильтр по типу, CRUD форма, archive, delete), доработка `inventory.html` (динамические фильтры категорий, бейджи operational-статусов), +2 карточки в админке.
- [x] **Импорт/Экспорт**: 3 новых шаблона (`body_parts`, `locations`, `inventory_categories`), 3 handler'а (upsert по slug), CSV-шаблон инвентаря расширен (`inventory_category_slug` + `inventory_status`).
- [x] **i18n**: +48 ключей EN/RU (body_parts_*, locations_*, inventory_cat_*, inventory_status_*).
- [x] **Тесты**: +34 в `tests/test_references.py` — seed (иерархия, идемпотентность), API (CRUD, batch-replace, snapshot, cross-user, архив), search (6 фильтров), inventory available, DSL selectors (регистрация, нормализация, валидация), совместимость (старые задачи без связей).
- [x] **Проверки**: ruff ✅, compile ✅.

## Сессия 58 (Phase 2): backend новой модели — DSL параметров, title-генератор, API переходов статусов

- [x] **Типизированный DSL параметров (ADR-041)**: app/params.py — normalize_schema принимает legacy map (правила без type инференс: min/max→decimal, enum→enum+options, min_length→string; required по умолчанию true — legacy-контракт) И структурированный список (key/title/type/required/options/min/max/unit_group/visible_when/allow_custom_value); 8 типов (string/text/integer/decimal/boolean/enum/multi_enum/duration); валидация чисто декларативная, БЕЗ eval; UNKNOWN_PARAM_TYPE возвращается вместо исключения; COMMON_PARAMETERS (13 общих параметров из update.md); LLM-валидатор делегирует в DSL (мёртвый код _TYPE_VALIDATORS/_validate_one_param удалён).
- [x] **Title-генератор (ADR-042)**: app/title_gen.py — priority chain title_override→manual→template→param list→activity title→free task; пустые части шаблона пропускаются (артефакты вычищаются); i18n EN/RU лейблы (tool/zone/count/…/free task); интенсивность как N/5; option titles из схемы; pipeline генерирует авто-заголовок при создании задачи (task_template добавлен в контекст build_context).
- [x] **API переходов статусов (ADR-040)**: app/api/task_flows.py — POST /api/v2/tasks/{id}/transition (to_status + comment; 409 при нелегальном переходе; completed→on_task_completed награда, stopped→on_task_interrupted штраф, остальные без наград/штрафов — ADR-038) + GET /api/v2/tasks/transitions (граф для UI); security.transition_once — атомарный UPDATE + ActivityTaskHistory (previous захвачен ДО update — synchronize_session фикс; cross-user 404). planned→stopped добавлен в STATUS_TRANSITIONS (ADR-029: прерывание планированной = штраф).
- [x] **Тесты**: +19 (tests/test_phase2_task_flows.py) — DSL (нормализация обеих форм, отказ от bad schema, валидация без eval, legacy-совместимость), title (override/template/fallback/RU-i18n/enum-titles), transitions (skipped/cancelled/audit/награда/штраф/нелегальные 409/граф/cross-user). **354/354 ✅**, ruff ✅.

## Сессия 58 (Phase 1): новая модель активностей — категории, статус-машина 11, аудит, эволюция моделей

- [x] **ADR-035…042 записаны** (см. планирование ниже) + **FUNCTIONAL.md** создан (обзор v0.8-actual).
- [x] **ActivityCategory** (app/models/category.py): иерархия (parent_id), slug/title/description/sort_order/is_active; **seed_categories** — 16 категорий с подкатегориями из examples/update.md (идемпотентно, /admin/seed-entities).
- [x] **Entity → Activity**: +slug (slugify RU→EN), short_title, role_tags, task_template, category_id FK, penalty_enabled (ADR-038), updated_at.
- [x] **ActivityLog → ActivityTask**: +title_override, scheduled_at (index), planned_comment, completion_comment, actual_parameters, updated_at; **статусы 3 → 11** (task_status.py: TASK_STATUSES, STATUS_TRANSITIONS, can_transition, normalize_status legacy pending→planned / interrupted→stopped).
- [x] **ActivityTaskHistory** (аудит переходов): complete_once/interrupt_once пишут prev/new status + snapshot + actor; interrupt разрешён из planned и in_progress.
- [x] **ActivitySession**: +title, notes, planned_start_at/end, accepted_at (ADR-037).
- [x] **Миграция 022**: таблицы + колонки + ремап статусов + backfill категорий из legacy-строк (транслит-slug); PG15 up/down/up ✅.
- [x] **Код**: pipeline/context_builder/training/points_v2/telegram/i18n переведены на planned/stopped; charts/activity SQL label + response + JS → stopped/planned (ревью-фикс AttributeError); шаблоны обновлены.
- [x] **Тесты**: +12 (tests/test_phase1_task_model.py) — **335/335 ✅**, ruff ✅, node --check ✅.

## Сессия 58 (планирование): ADR-035…042 + FUNCTIONAL.md

- [x] **Анализ examples/update.md** — предложенная система хранения активностей сверена с текущей архитектурой (v0.8): философия «базовая активность + шаблон + экземпляр» уже реализована; выявлены пробелы (категории-таблица, 11 статусов, аудит, planned/actual параметры, title-генератор) и конфликты (ADR-029 vs «не запрещать остановку», Training, геймификация).
- [x] **Решения владельца** (ask_user): штрафы — гибрид (cancelled/skipped до начала без штрафа, stopped — штраф, partially_completed без награды, per-activity penalty_enabled, сессии-accepted: изменения после принятия = штраф); ActivityTask = эволюция ActivityLog (не новая таблица); Training остаётся отдельной системой программ.
- [x] **ADR-035…042 записаны** в memory/DECISIONS.md (ActivityCategory + 16 категорий, ActivityLog→ActivityTask, сессии-accepted, штрафы-уточнение ADR-029, Training-программа, статус-машина 11 + аудит, типизированный DSL параметров, title-генератор).
- [x] **FUNCTIONAL.md создан** — читаемое описание текущего функционала проекта (v0.8-actual): стек, страницы, каталог, LLM-пайплайн, задачи, сессии, тренировки, диеты, геймификация (XP + Points v2), календарь/расписание, замеры/инвентарь/импорт, Telegram-бот, безопасность/приватность, модель данных, планы (ADR-035…042 + 4 фазы).
- [x] OPEN_QUESTIONS Q11 добавлен (новая модель — запланировано), CHANGELOG обновлён.


- [x] **risk_level enum на Entity (REM §5.2)**: модель + миграция 021 (PG15 up/down/up) + схемы + Form-санитизация; seed → `low`; `filter_automation_eligible` в context_builder, применён в generate_task и generate_daily_plan (not_assessed/high не автоматизируются, elevated — с согласием); бейджи в catalog/my_entities.
- [x] **Typed gamification_config DSL (P2)**: app/gamification/dsl.py — валидатор условий (whitelist операторов, без eval) + Pydantic-валидаторы в BonusCondition/PenaltyLevel; engine переведён на DSL; тест-гард «нет eval».
- [x] **Subtask gate (REM §7.1)**: тест санитизации (cap 20/500, коэрция) + риск-gate тест — пункт закрыт.
- [x] **Inter self-hosted (DESIGN §7.1)**: woff2 в static/fonts, @font-face + font-family, tabular-nums, без CDN.
- [x] **Mobile bottom nav (DESIGN §4.4)**: 4 пункта 64px + safe-area; desktop-nav скрыт на mobile; тумблеры + logout доступны.
- [x] **JS-hoist (DESIGN §15.4)**: app.js + 10 page-модулей + JSON-блоки i18n; node --check ✅; ревью-фиксы: утечка api_key_encrypted через tojson ORM-объекта (→ boolean), дублирование nav, хардкод Tasks → nav_tasks.
- [x] **Тесты**: +16 — **323/323 ✅**, ruff ✅.

## Сессия 56: Диеты v3 — история оценок, синергия с тренировками, inline-редактирование, фото

- [x] **История оценок диет**: таблица `diet_evaluations` (каждая LLM-оценка adherence сохраняется, сортировка created_at+id DESC); эндпоинт `GET /diets/api/{id}/evaluations` (проверка владения → 404); UI — кнопка «История» в карточке диеты (рендерится в конкретную карточку, не в первую — баг из ревью исправлен).
- [x] **Взаимное влияние диет и тренировок**: таблица `diet_training_reviews` + LLM-функция `analyze_diet_training_synergy` (период, активные диеты + потребление + дни тренировок со статусами задач; correlations direction whitelist diet_to_training/training_to_diet; adjustments ≤8×1000; summary ≤5000); эндпоинты `POST/GET /diets/api/synergy`; UI — секция «Синергия диеты ↔ тренировки» с кнопкой и историей обзоров.
- [x] **Inline-редактирование позиций диет**: клик по названию/✎ → форма (name/qty/unit/meal/notes), Enter сохраняет (form+submit), ✕ отменяет.
- [x] **Фото диет**: upload через `/attachments` owner_type=diet (allowlist уже включал diet), миниатюры + удаление.
- [x] **Баг из ревью**: `showHistory` приклеивал блок к первой карточке (`querySelector('#diets-list .bg-white')`) → теперь передаётся конкретная card.
- [x] **Стабильный порядок**: `created_at` истории задаётся в Python (не server_default) — в одной SQLite-транзакции func.now() одинаковый, uuid4 случайный → порядок был нестабилен; плюс вторичная сортировка id DESC.
- [x] **Миграция 020** проверена на PG15: upgrade 001→020, downgrade 020→019, повторный upgrade.
- [x] **Тесты**: +6 (история с порядком, cross-user 404, синергия pipeline/endpoint/без LLM, inline update) — 297/297 ✅, ruff ✅.

## Сессия 55: Внешний аудит (P0) + диеты с LLM-контролем

- [x] **P0 deps**: pyproject `httpx<0.28`; requirements.txt/lock перегенерированы pip-compile (httpx==0.27.2 + openai==1.59.9 совместимы; lock чист, без apt-мусора); CI `ruff==0.5.7` + docker build job (проверяет seed/cli внутри образа).
- [x] **P0 CSRF**: dashboard больше не перевыпускает CSRF-cookie после рендера; `ensure_csrf_cookie` ставит только если нет; `GET /` больше не 500 (get_optional_user переживает прямой вызов, home через ensure_csrf_cookie).
- [x] **P0 safety gate LLM**: промпт subtasks «3-5» → «1-5 при необходимости»; `format_context_abstract` не раскрывает реальные имена из истории (+entity_id в history); `entity_name` из LLM заменяется каноническим серверным (generate_task + generate_daily_plan); **training-пайплайн теперь тоже уважает llm_mode abstract** (generate_daily_plan → format_context_abstract, analyze_training_day → entity_id вместо имени).
- [x] **Целостность**: interrupted training-задачу нельзя завершить (complete_once атомарный UPDATE WHERE status='pending', rowcount=0 → idempotent); уникальный индекс `uq_points_txn_activity_log` (не даёт двойного начисления); `activity_logs.completed_at` (импорт + атомарный complete); `ScheduleRuleCreate.entity_id` → UUID (PG больше не 500).
- [x] **Cross-user**: `/api/v2/points/balance` скрывает чужие thresholds; импорт Entity по имени — только owner/public.
- [x] **Ops/security**: login/CSRF куки Secure в production; logout только POST; TTL-очистка raw payload — `cleanup_expired_raw_responses(db)` в scheduler (каждые 6ч); Dockerfile включает cli.py/seed*.py; DEPLOY_VPS/README → /register /login; UI llm_configs: переключатели llm_mode + store_raw (+ эндпоинт `/llm-configs/{id}/update`).
- [x] **Диеты v2 (LLM)**: `diets.direction` (направление: weight_loss/muscle_gain/health/…), `last_evaluation`/`evaluated_at`; `diet_consumptions` (факт: что реально съедено, CRUD + limit 200); LLM-генерация диеты (`generate_diet` — санитизация: cap 20 items, длины, qty>0); LLM-оценка adherence (`evaluate_diet` — score 0-100, findings, adjustments add/modify/remove по точному имени, никаких свободных id от LLM); UI diets.html: select направления, форма AI-генерации, журнал питания, блок оценки.
- [x] **Латентный баг**: `SYSTEM_PROMPT_TEMPLATE` — неэкранированные `{`/`}` в JSON-примере ломали `.format()` (KeyError) → экранированы (test поймал).
- [x] **Миграция 019** проверена на PG15: upgrade 001→019, downgrade 019→018, повторный upgrade, ORM-цикл (Diet/DietItem/DietConsumption с direction).
- [x] **Тесты**: +17 (tests/test_audit_s55.py) — 291/291 ✅, ruff ✅.

## Сессия 54: drag&drop везде, изображения инвентаря, фото-отчёты, диеты, параллельные тренировки

- [x] **Drag&drop сортировка**: журнал тренировки (эндпоинт `POST /training/log-entry/reorder`, `sort_order` уже был), инвентарь (`POST /api/v2/inventory/reorder` — partial: работает с активными фильтрами, unknown id → 400), позиции диет (`POST /diets/api/{id}/items/reorder`), плюс `sort_order` добавлен в `schedule_rules` и `availability_windows` (миграция 018, UI-сортировка там позже).
- [x] **Изображения инвентаря**: `inventory_items.image_path` + `POST/DELETE /api/v2/inventory/{id}/image` (валидация content-type + magic-bytes, лимит 8 МБ), превью и 📷-кнопка в inventory.html, drag&drop строк.
- [x] **Фото-отчёты (универсальные)**: таблица `attachments` (owner_type/owner_id, allowlist), API `POST/GET/DELETE /attachments`; UI — на карточках задач в training.html (загрузка/просмотр/удаление). `delete_upload` защищён от path traversal (resolve + префикс).
- [x] **Диеты**: таблицы `diets` + `diet_items`, API `/diets/api` CRUD + items + reorder + toggle `is_active` (комбинирование = несколько активных), страница `/diets` в навигации (drag&drop позиций, бейдж «комбинируются»).
- [x] **Параллельные тренировки (гибрид)**: `training_days.name`; `/training/plan` больше НЕ блокирует второй план — добавляет (leftover-пустые удаляются); `analyze_day` принимает `training_day_id`; страница — колонки планов (grid до 2) + общая timeline-шкала дня (журнал всех планов + правила расписания, lane-packing в JS, clamp 0..1440).
- [x] **Инфраструктура загрузок**: `config.upload_dir`/`max_upload_bytes`, docker-compose volume `uploads:/app/uploads` + `UPLOAD_DIR`, mount `/uploads` + CSRF-bypass в main.py, `.gitignore uploads/`, `app/services/uploads.py`.
- [x] **Миграция 018** проверена на реальном PostgreSQL 15: upgrade 001→018, ORM-вставки/чтения новых таблиц, downgrade 018→017, повторный upgrade — всё ✅.
- [x] +21 тест (`tests/test_dnd_diets_uploads.py`): reorder (полный/partial/unknown/cross-user), upload (валидация, oversize, delete), attachments (allowlist, изоляция), диеты CRUD, несколько планов, timeline-рендер, pipeline name.
- [x] 274/274 тестов, ruff 0, format clean.

## Сессия 53: страница /import — навигация + UX (drag&drop, результат импорта)

- [x] **/import добавлена в навигацию** (base.html, ключ `nav_import` уже был в i18n, но ссылки не было) + `active_nav: "import"`.
- [x] **Фикс латентного краша**: `request.url_root` не существует в Starlette 1.4.1 → `request.base_url` (страница /import падала бы с AttributeError при открытии).
- [x] **UX**: карточки шаблонов показывают подсказку «Колонки:» с полями; upload-зона — drag&drop с подсветкой, имя выбранного файла, кнопка Import disabled до выбора файла; JSON-ответ `/import/upload` теперь рендерится красивым баннером (импортировано/пропущено), ошибки — с реальным текстом (`data.detail`), не-JSON ответы — raw text.
- [x] +3 i18n ключа (import_fields_hint, import_result_imported, import_result_skipped, import_result_error) в en/ru.
- [x] +2 теста: /import рендерится с nav-ссылкой и drop-zone; у всех шаблонов есть CSV/JSON download + API-эндпоинт отдаёт CSV с Content-Disposition.
- [x] 253/253 тестов, ruff 0, format clean.

## Сессия 52: CSRF-покрытие оставшихся native форм (admin seed и др.) + rebuild контейнера

- [x] **Симптом**: `/admin/seed-entities` → 403 «CSRF token missing or invalid» после обновления контейнеров.
- [x] **Причина 1 (деплой)**: `docker compose up -d` НЕ пересобирает образ — Dockerfile `COPY app/` запекает код при сборке. Контейнер крутил код до Session 48 (нет `async def verify_csrf`, нет context processor) → native POST без заголовка всегда 403. Фикс: `docker compose up -d --build`.
- [x] **Причина 2 (код)**: 7 шаблонов (admin, achievements, llm_configs, my_entities, notifications, privacy, sessions) содержали native `<form method="post">` БЕЗ hidden `csrf_token` — пропущены в Session 48 (покрыли только tasks/training/catalog/base). Добавлены hidden-поля во все 14 форм; login/register не требуют (неаутентифицированные запросы пропускают CSRF).
- [x] +3 регрессионных теста: статическая проверка всех шаблонов (каждый method=post содержит hidden csrf_token), интеграционный admin-тест (POST /admin/seed-entities с form-token → 303 + реальный seed), admin без form-token → 403.
- [x] 251/251 тестов, ruff 0, format clean.

## Сессия 51: PostgreSQL JSONB-фикс (migration 017) + удаление пароля из git history

- [x] **Migration 017** (`alembic/versions/017_fix_jsonb_columns.py`): `entities.gamification_config` и `points_profiles.config` Text → JSONB (миграция 006 создала Text, ORM/seed передают dict → на чистой PostgreSQL вставка падала). Для `config` сначала дроп server_default (иначе PG не может скастовать `'{}'`), потом тип + `'{}'::jsonb`. Legacy Text-JSON кастится через `postgresql_using`.
- [x] **Валидация на реальном PostgreSQL 15**: чистая схема → alembic upgrade head (001–017), вставка legacy Text-строк ДО 017 → успешный каст при upgrade, ORM dict-inserts/reads — все проходят.
- [x] **Пароль `tracker_dev_2024` удалён** из `seed_prod.py` и `seed_training.py` (fail-fast: без DATABASE_URL → понятная ошибка + exit 1; `--database-url` флаг работает — проверка после parse_args, ревью-фикс).
- [x] **Git history вычищен** (`git filter-repo --replace-text`, пароль → `REDACTED_DB_PASSWORD`), force-push на GitHub выполнен (пользователь одобрил). Бэкап: `/tmp/tracker-backup-20260810-0724.bundle`. ВСЕ хэши коммитов изменились.
- [x] **Памятка владельцу**: если `tracker_dev_2024` использовался на VPS — ротация пароля БД обязательна (даже после scrub истории пароль был публично доступен); если репо GitHub публичный — чувствительные seed-данные остаются в истории (пользователь решил оставить seed-данные как есть).
- [x] +5 тестов (`tests/test_config.py` TestSeedScriptsNoHardcodedCredentials): нет известного пароля, нет `user:pass@` в URL, fail-fast (subprocess: seed_training без env → exit 1; seed_prod с `--database-url` при пустом env проходит проверку и падает на коннекте).
- [x] 248/248 тестов, ruff 0, format clean.

## Сессия 50: геймификация — Stop 500 (await на sync), состояние complete/interrupt, расписание

- [x] **Stop → 500** (app/gamification/handler.py): убран `await` на синхронной `_get_redemption_action_from_config` (был TypeError → 500, запись оставалась pending, redemption не создавался).
- [x] **Целостность состояний** (app/security.py `complete_once`): обрабатывается только статус `pending` — прерванную задачу больше нельзя завершить для награды; `interrupt_once` без изменений (блокирует completed/interrupted).
- [x] **Расписание** (app/api/tasks.py): `set_next_due`/`set_retry_block` вызываются только при `not result["idempotent"]` — повторные Complete/Interrupt не двигают `next_due_at`/`retry_not_before_at`.
- [x] **Telegram-бот** (app/telegram/bot.py): /done, /interrupt, /tasks ищут `status == "pending"` (статуса `active` не существует — задачи создаются `pending`); inline-хендлеры `done:`/`int_confirm:` получили статус-гарды (без двойных наград/штрафов).
- [x] +4 регрессионных теста (redemption-path не падает и создаёт PenaltyRedemption; complete после interrupt не даёт награду и не двигает расписание; повторный complete/reinterrupt идемпотентны для расписания).
- [x] 243/243 тестов, ruff 0, format clean.

## Сессия 49: аудит-фиксы training (чужой entity/subtasks, partial plan, stored XSS)

- [x] **generate_daily_plan** (app/llm/pipeline.py): каждый task плана валидируется — `entity_id` обязан быть в allowed (опт-ин) наборе пользователя (чужой private entity отклоняется), `params` — против `params_schema` сущности; subtasks санитизируются (только строки, ≤20 шт., ≤500 симв.); TrainingDay создаётся только ПОСЛЕ валидации (транзакционно).
- [x] **Частичный план после ошибки LLM**: `analyze_training_day` мутирует день/usage только после успеха ОБОИХ LLM-вызовов (раньше status/analysis коммитились при падении второго вызова); `generate_plan` при повторе удаляет пустой leftover-день (нет задач И журнала), не блокируя генерацию.
- [x] **Stored XSS через entry_type**: `add_extra_log_entry` — allowlist `ENTRY_TYPES` (вне списка → `general_note`); `_render_log_entry_row` экранирует label и `unit` (защита и для старых строк); `time_label` ограничен 20 симв. (String(20)).
- [x] +8 регрессионных тестов (foreign entity → 303 error, params вне диапазона → отклонено, нет partial day при ошибке LLM + повтор не блокируется, leftover заменяется, analyze без partial state, entry_type санитизация/валидный тип, экранирование рендера).
- [x] 239/239 тестов, ruff 0, format clean.

## Сессия 48: фикс CSRF — нативные формы, контекст шаблонов, JS fetch

- [x] `verify_csrf()` теперь async и валидирует `csrf_token` из поля формы (double-submit cookie) — чинит кнопки темы/локали (нативные POST-формы): раньше проверялся только заголовок `X-CSRF-Token` (HTMX), форма без заголовка всегда получала 403.
- [x] Парсится только form content-type (`form-urlencoded`/`multipart`); JSON-тела не буферизуются на пути отказа.
- [x] `await request.body()` вызывается до `request.form()` — обход бага Starlette 1.4.1 (`form()` парсит через `stream()` без заполнения `request._body`, иначе BaseHTTPMiddleware не реплеит тело в endpoint → 422).
- [x] **Найдено при проверке всех форм**: `csrf_token` в контекст шаблона передавали только home и dashboard — на остальных страницах hidden-поля и HTMX meta-тег были пустыми (все нативные формы и HTMX → 403). Фикс: context processor в `templates_setup.py` инжектит токен из cookie во все шаблоны.
- [x] **JS-страницы** (points/schedule/measurements/inventory/calendar/telegram-link) слали `fetch(..., {method:'POST'})` без заголовка CSRF → 403. Фикс: обёртка `window.fetch` в base.html авто-добавляет `X-CSRF-Token` для same-origin state-changing запросов.
- [x] Избыточные явные `csrf_token` в контекстах `main.py` (home) и `dashboard.py` убраны — их заменяет context processor.
- [x] Регрессионные тесты: нативные формы темы и локали (303 + сохранение в БД), неверный токен поля → 403, meta-тег с токеном на /tasks/, JSON POST с заголовком CSRF → 200 / без заголовка → 403 (JS-fetch сценарий на /api/v2/points/profiles).
- [x] 231/231 тестов, ruff 0, format clean.

## Сессия 44: исправление предрелизного Docker Compose

- [x] Устранён автоматический dev override, переключавший app на SQLite и ломавший Alembic на PostgreSQL `JSONB`.
- [x] Dev-конфигурация вынесена в явно подключаемый `docker-compose.dev.yml`; она также использует PostgreSQL.
- [x] Готовность БД задаётся через `depends_on: condition: service_healthy`, без хардкода имени пользователя/БД в app command.
- [x] `docker compose up -d --build app`: PostgreSQL healthy, миграции 001–016 применены, app запущен.
- [x] `GET /healthz` вернул `ok`; production и development compose-конфигурации валидны.
- [ ] Полный pytest на системном Python 3.13 завис на первом auth-тесте; baseline проекта использует Python 3.11. Полный ruff также показывает 15 ранее существовавших ошибок вне изменённых Docker-файлов.

## Обзор фаз
| Область | Статус |
| --- | --- |
| Проектирование (AGENTS.md, tracker-spec.md, memory) | ✅ Завершено |
| Phase 1 — Фундамент и инфраструктура | ✅ Завершена |
| Phase 2 — Каталог и конфиги | ✅ Завершена |
| Phase 3 — LLM-пайплайн | ✅ Завершена |
| Phase 4 — UI, сессии, геймификация, уведомления | ✅ Завершена |
| Phase 5 — Training (тренировки) | ✅ Завершена |
| Phase 6 — Points v2, Measurements, Inventory, Schedule | ✅ Завершена |
| Phase 7 — Import/Export + Charts + Layout | ✅ Завершена |
| Phase 8 — Calendar (календарь доступности) | ✅ Завершена |
| Phase 9 — Penalty & Points v2 (штрафы и баллы) | ✅ Завершена |
| Phase 10 — Telegram Bot v2 (реальный бот) | ✅ Завершена |
| Phase 11 — Auto-Analysis Scheduler | ✅ Завершена |
| v0.7 Audit & Interview (R0) | ✅ Завершён |
| R1 — Воспроизводимость | ✅ Завершён |
| R2 — Безопасность и транзакции | ✅ Завершён |
| R3 — Каталог, модерация, scheduler | ✅ Завершён |
| R4 — LLM planner | ✅ Завершён |
| R5 — Frontend shell | ✅ Завершён |
| R6 — Возврат вторичных модулей | ✅ Завершён |
| DESIGN.md Compliance & Dashboard | ✅ Завершён |
| R0-R6 Re-audit (Session 27) | ✅ Завершён |

## R0-R6 Re-audit — критические исправления
- [x] CSRF: verify_csrf починена (header-less bypass), подключена как HTTP middleware
- [x] CSRF: пропускает неаутентифицированные запросы (нет access_token cookie)
- [x] create_all() полностью удалён из lifespan (Alembic only)
- [x] requirements.lock: 102 замороженных пакета
- [x] Миграция 014: JSON→JSONB (subtasks, meta), boolean defaults true/false
- [x] Object-level auth: get_gamification_config (is_public|owner), toggle_opt_in (is_public|owner), delete_window (JOIN template owner)
- [x] Идемпотентность: training complete_training_task (проверка статуса)
- [x] XSS: escapeHtml() в base.html + экранирование во всех user-значениях (inventory, schedule, points, calendar, measurements)
- [x] HTMX listener: DOMContentLoaded (не document.body до ready)
- [x] CDN: FIXME-комментарии в base.html, план миграции на локальные assets
- [x] conftest.py: auth_headers включает CSRF cookie + X-CSRF-Token header
- [x] main.py: очищены неиспользуемые импорты
- [x] 105/105 тестов с CSRF, ruff 0, format clean
- [x] security.py: require_entity_owner() — отдельный хелпер для Entity (owner_id ≠ user_id)
- [x] points_v2.py: update_gamification_config + assign_profile_to_entity проверяют владельца entity
- [x] calendar.py: create_override проверяет владельца template
- [x] Аудит всех остальных эндпоинтов: уже используют user_id-фильтрацию (безопасны)

## Что сделано (Phase 9 — Penalty & Points v2)
- [x] PenaltyRedemption модель + миграция 008: отслеживание отработок штрафов (pending/completed/skipped)
- [x] Redemption API: `GET /api/v2/points/redemptions`, `POST .../complete` (возврат баллов), `POST .../skip`
- [x] Handler: авто-создание PenaltyRedemption при прерывании задачи
- [x] PointsProfile: полный CRUD (`POST`/`GET`/`DELETE`), назначение профиля на сущность
- [x] Threshold effects: авто-уведомления при пересечении negative/warning/good порогов
- [x] Gamification editor: `PUT /entities/{id}/gamification` — обновление конфига баллов/штрафов
- [x] Points page: список pending отработок (✅ Complete / ⏭ Skip), профили баллов, назначение на сущность
- [x] Тесты: 105/105

## Что сделано (Phase 10 — Telegram Bot v2)
- [x] 8 команд с реальной логикой: /start, /link, /next→LLM, /tasks, /done→gamification, /interrupt→penalty, /stats→DB, /session→DB, /settings→locale
- [x] Inline-клавиатуры: ✅ Done / ⏹ Interrupt на каждой задаче, подтверждение прерывания
- [x] User.telegram_chat_id, telegram_link_code, telegram_link_code_expires (миграция 009)
- [x] Привязка: 6-значный код (30 мин), /link CODE, /profile/telegram-link-code, /profile/telegram-status
- [x] Уведомления: send_telegram_notification(), хук _send_tg_notifications в gamification handler
- [x] Webhook: авто-регистрация при старте (setup_webhook в lifespan)
- [x] Дашборд: карточка «Link Telegram» с генерацией кода, статусом, кнопкой
- [x] config: tg_bot_username, tg_webhook_base_url
- [x] Polling-режим: tg_polling=true → start_polling() (фоновая asyncio task), stop_polling() при shutdown
- [x] Тесты: 105/105

## Что сделано (Phase 11 — Auto-Analysis Scheduler)
- [x] app/training/scheduler.py — фоновая asyncio задача, без внешних зависимостей
- [x] Ежедневный запуск в tg_auto_analysis_time (по умолчанию 23:00 UTC)
- [x] Сканирует всех пользователей: ищет TrainingDay со статусом active/planned
- [x] Вызывает analyze_training_day (анализ дня + генерация плана на завтра)
- [x] Запуск/остановка в lifespan вместе с Telegram
- [x] Тесты: 105/105

## Что сделано (Phase 7 — Import/Export + Charts + Layout)
- [x] Import/export модуль: 8 типов шаблонов (measurements, inventory, entities, schedule, points_transactions, training_days, activity_logs, points_profiles)
- [x] CSV/JSON upload с авто-определением типа по заголовкам
- [x] API-push для внешних сервисов (`POST /import/api`)
- [x] Full backup: `GET /import/export/full` — все данные пользователя одним JSON
- [x] Per-type export: `GET /import/export/{type}?format=csv|json`
- [x] CLI-утилита: `python cli.py import/export/template`
- [x] Веб-страница `/import` с шаблонами, загрузкой, экспортом, API-документацией
- [x] 2 новых chart API: `/api/v2/charts/category-breakdown` + `/api/v2/charts/completion-rate`
- [x] Dashboard v2: 4 графика (points trend, category donut, completion gauge, XP sparkline)
- [x] Training page: weekly completion rate chart
- [x] Sessions page: 14-day activity timeline + duration bars
- [x] Achievements: улучшенные прогресс-бары + 3 счётчика
- [x] Все страницы: компактный layout (chart heights h-72→h-40, py-8→py-4, text-3xl→text-2xl)
- [x] python-dotenv в requirements.txt

## Что сделано (Phase 8 — Calendar)
- [x] 3 модели: CalendarTemplate (шаблон недели), AvailabilityWindow (окно с политикой allowed/disallowed/passive_only), CalendarOverride (отпуск/каникулы на диапазон дат)
- [x] Entity.intensity (active/passive/neutral) — пассивные активности обходят ограничения
- [x] Миграция 007 (calendar_templates, availability_windows, calendar_overrides + entity.intensity)
- [x] API: CRUD templates/windows/overrides + `GET /calendar/check` (проверка доступности)
- [x] `is_available()` — утилита проверки (time + duration + intensity → bool)
- [x] `get_day_schedule()` — получение расписания на день (для LLM и UI)
- [x] LLM-интеграция: календарь в `context_builder` → инжектится в промпт
- [x] Веб-страница `/calendar` с timeline-баром на сегодня, конструктором шаблонов, управлением отпусками
- [x] Интеграция в `/tasks`: индикатор доступности + today's schedule
- [x] Schedule page: weekly timeline chart (горизонтальные бары по дням недели)
- [x] Отпуск = CalendarOverride с шаблоном «Vacation» на диапазон дат

## v0.7 Audit & Interview (R0)
- [x] Внешний аудит: REMEDIATION_SPEC.md прочитан, 18 дефектов зафиксированы
- [x] Интервью по 6 ключевым архитектурным решениям (ADR-029–034)
- [x] AGENTS.md обновлён: приоритет документов, LLM-режимы, актуальные фазы
- [x] AGENTS_.md удалён (заменён на AGENTS.md)
- [x] DECISIONS.md: +6 ADR
- [x] CONTEXT.md: убрано «код не написан», отражён статус
- [x] DESIGN.md — ожидает создания

## R1 — Воспроизводимость
- [x] pyproject.toml — единый источник зависимостей
- [x] requirements.txt — сгенерирован из pyproject.toml
- [x] bcrypt закреплён <4.1 (совместимость с passlib)
- [x] python-dotenv добавлен в pyproject.toml
- [x] Версия 0.7.0 в pyproject.toml и main.py
- [x] create_all с предупреждением (Alembic для production)
- [x] CI: ruff lint + pytest на PostgreSQL 15 (.github/workflows/ci.yml)
- [x] Миграция 012: subtasks String→JSON, next_day_suggestion Text→JSONB исправлены

## R2 — Безопасность
- [x] app/security.py: CSRF (double-submit cookie), OwnershipChecker, complete_once/interrupt_once
- [x] login/logout: CSRF cookie + очистка, access_token path=/
- [x] base.html: CSRF meta tag, HTMX auto-include X-CSRF-Token, scripts block
- [x] tasks: идемпотентный complete/interrupt (защита от двойной награды)
- [x] encryption: ключ от CREDENTIALS_ENCRYPTION_KEY (отделён от JWT_SECRET)
- [x] config: credentials_encryption_key
- [x] dashboard/home: csrf_token в шаблонах
- [ ] Object-level auth: OwnershipChecker создан, но нужно применить во всех эндпоинтах

## R3 — Каталог, модерация, scheduler
- [x] User.role (user/moderator/admin) + миграция 010
- [x] require_admin() dependency — /admin защищён
- [x] OwnershipChecker применён в tasks, training, sessions, achievements, notifications
- [x] unacceptable → strong_aversion (модель, схемы, pipeline, тесты)
- [x] Soft scheduler: get_due_practices(), set_next_due(), set_retry_block()
- [x] UserEntityOptIn.next_due_at + retry_not_before_at (миграция 011)
- [x] Tasks page: due practices + авто-установка сроков после complete/interrupt

## R4 — LLM planner
- [x] LLMProviderConfig.llm_mode (full/abstract) + миграция 012
- [x] context_builder: format_context_abstract() — opaque IDs
- [x] app/llm/validator.py — проверка entity_id в allowed set
- [x] Pipeline: валидатор ответа, выбор формата по llm_mode
- [x] Deterministic fallback: /tasks/generate-deterministic
- [x] tasks.html: due practices + кнопка «Pick from due (no LLM)»
- [x] Миграция 012: subtasks + next_day_suggestion типы исправлены

## В работе
- Ничего. R0–R4 завершены.

## R5 — Frontend shell
- [x] active_nav: подсветка активной страницы в навигации
- [x] Навигация упрощена: dashboard, tasks, training, catalog, points, admin
- [x] CSRF hidden поля в формах locale/theme
- [x] innerHTML аудит: всё использование — серверные данные (безопасно)
- [x] scripts блок в base.html

## DESIGN.md Compliance & Dashboard
- [x] base.html: убраны градиенты (body, logo), emoji из nav, animate-fade-in из main
- [x] dashboard_v2.html: полный редизайн — 4 графика (activity bars, category donut, points trend, completion gauge), solid XP bar, SVG-иконки, consistent spacing
- [x] training.html: SVG checkmark, solid progress ring, compact chart
- [x] sessions.html: improved timeline, no gradient duration bars
- [x] schedule.html: light mode support, clean forms
- [x] measurements.html/inventory.html/calendar.html/points.html: light/dark theme, semantic tokens
- [x] Убраны дубликаты Chart.js CDN (уже в base.html)
- [x] DESIGN.md токены: accent #6B57A5, success #2F7657, warning #9A6415, danger #A83B4A, info #356A9A
- [x] 105 тестов, ruff 0, Docker ok

## В работе
- Ничего. R0–R6 завершены, переаудит пройден.

## Cross-user Auth Tests & README (Session 28)
- [x] test_cross_user_auth.py: 22 теста межпользовательской авторизации
- [x] CSRF middleware: HTTPException → JSONResponse (try/except в main.py)
- [x] README.md: полная документация проекта
- [x] 127/127 тестов, ruff 0, format clean, Docker ok

## Что сделано (Session 28 — Cross-user Auth)
- [x] 22 cross-user теста: entity gamification, opt-in, calendar, schedule, inventory, points profiles, penalty redemptions, sessions, notifications, LLM configs, training, tasks, admin, CSRF
- [x] SQLite-совместимость: время как datetime.time (не строки), admin URL с trailing slash
- [x] README.md: структура, установка, архитектура, API, конфигурация, разработка

## Интеграционные тесты + Обновление зависимостей (Session 30)
- [x] test_scheduler.py: 8 тестов (_parse_time, lifecycle, training days, auto-analysis, cross-user)
- [x] test_telegram_bot.py: 10 тестов (link code, status, get_user_by_chat, webhook, send_notification)
- [x] requirements.txt + requirements.lock — обновлены (102 пакета)
- [x] 153/153 тестов, ruff 0, format clean, Docker ok

## CI GitHub Actions (Session 31-32)
- [x] pyproject.toml: +[build-system] для pip install .[dev]
- [x] CI: 3 job'a — lint (ruff), test (pytest+SQLite), migrations (Alembic roundtrip на PostgreSQL)
- [x] Убран неиспользуемый PostgreSQL-сервис из test job (тесты на SQLite)
- [x] seed_prod.py: ruff fix (_pts)
- [x] Session 32: фикс CI — repair type guard + migration boolean defaults
- [x] Все 3 job'а зелёные (lint, test, migrations) в GitHub Actions
- [x] 153/153 тестов, ruff 0, format clean

## Обновление статических файлов (Session 33)
- [x] HTMX: 2.0.0 → 2.0.10 (51KB)
- [x] Chart.js: 4.4.0 → 4.5.1 (209KB)
- [x] TailwindCSS: v3 → v4.3.3 (282KB, @tailwindcss/browser@4)
- [x] base.html: убран tailwind.config (v4 использует class-стратегию по умолчанию)
- [x] 153/153 тестов, ruff 0

## Подготовка релиза 0.8.0 (Session 34)
- [x] Версия 0.7.0 → 0.8.0
- [x] .env.example: все переменные (CREDENTIALS_ENCRYPTION_KEY, TG_*, docker compose)
- [x] docker-compose.yml: все env vars, nginx опциональный (профиль), порт 8000 на хост, pg_isready wait-loop
- [x] seed_prod.py: argparse --email --database-url
- [x] docker-compose.override.yml: dev-окружение (SQLite, hot-reload)
- [x] Docker smoke-test: все эндпоинты OK (/healthz, /static/*, /)
- [x] README: секция Deployment (хост-nginx + certbot + docker compose + бэкапы)

## Сессия 40: Deferred-фиксы (production gate, bif, JS i18n, XSS-fixtures) (2026-08-09)

Детальный отчёт: `memory/DEFERRED_FIX_SESSION_40.md`.

### Закрыто в S40
- [x] **Backend P0 — Production gate секретов в config.py**: `app_env` model_validator + длина ≥32 + `change-me-...` отвергаются при APP_ENV=production. `docker-compose.yml` APP_ENV по умолчанию production, `docker-compose.override.yml` явно development.
- [x] **AGENTS.md bif-комментарий**: новая секция 0 «Архитектурный bif v0.8-actual ↔ v0.7-spec» с таблицей 6 пунктов расхождения и ADR-029/031/032/033/034.
- [x] **store_raw_response flag** (REM §7.5): миграция 016 + `LLMProviderConfig.store_raw_response` + `ActivityLog.raw_response_expires_at` + helper `_resolve_raw_response` в pipeline.py (TTL 30 дней).
- [x] **Расширение LLM validator** (REM §7.4): `validate_params_against_schema` с типами (number/integer/string/boolean), min/max, min_length/max_length, enum, optional.
- [x] **dashboard_v2.html refactor** (DESIGN §11): 4 графика → 2 канваса + 2 summary-карточки (categories top-3 + completion big-number).
- [x] **calendar.html JS async i18n**: I18N dict + POLICY_LABEL map (Mon..Sun, Allowed/Passive/Blocked, Templates/Overrides, check-result, default-marker).
- [x] **inventory.html JS async i18n**: I18N dict + STATUS_LABEL map (All/Clothing/Equipment/Cosmetics/Shopping List, status badges, qty/priority labels).
- [x] **import_data.html: localhost:8443 → app_url** (из `request.url_root`), 17 новых i18n ключей, эмодзи удалены, градиент solid.
- [x] **XSS-fixture тесты** (REM §A14): 24 теста в 4 фазах (Jinja autoescape, escapeHtml mirror, end-to-end, OWASP regression).

### Метрики
- ruff check ✅ | ruff format ✅
- **225/225 тестов** ✅ (было 153 → +72 новых: 11 production gate + 5 raw-response policy + 32 validator + 24 XSS-fixtures)
- 86 файлов Python отформатированы
- 105+ i18n ключей добавлено в en.py + ru.py
- 1 миграция Alembic (016)

## Аудит проекта (Session 37, 2026-08-09)

Детальный отчёт: `memory/AUDIT_SESSION_37.md`.

### Выводы
- 153 теста ✅, ruff 0, CI 3 job'а зелёные, Docker smoke OK, реальный деплой на VPS.
- 6 ADR (029–034) сознательно расходятся с REMEDIATION_SPEC.md (bif владельца).
- Архитектурный bif зафиксирован как принятый (Q7 в OPEN_QUESTIONS, см. ниже).
- Код НЕ менялся в Сессии 37 — только аудит.

### Открытые дефекты
- P0: secret defaults в config.py без production gate
- P0: innerHTML в 6 файлах требует перепроверки (XSS-fixture)
- P1: LLM validator не покрывает variant_id/automation/risk
- P1: generate_daily_plan разрешает свободные subtasks (REM 7.1)
- P1: нет `risk_level` enum на Entity
- P2: scheduler без advisory lock; pipeline смешивает 3 use-case

### Не закрыто до следующей сессии
- [ ] Bif SPEC↔ADR: добавить явный комментарий в AGENTS.md
- [ ] Production gate секретов
- [ ] innerHTML аудит + A14 XSS-тест
- [ ] `store_raw_response` флаг в LLMProviderConfig (REM 7.5)
- [ ] Расширение LLM validator (REM 7.4)

## Frontend-аудит (Session 38, 2026-08-09)

Детальный отчёт: `memory/FRONTEND_AUDIT_SESSION_38.md`.

### Выводы
- DESIGN.md compliance: **≈30%** (694 строки спецификации).
- Покрыто: CDN ✅, локальные assetы ✅, CSRF через HTMX ✅, light/dark ✅, CSRF middleware ✅.
- Не покрыто: **0 ARIA** атрибутов (WCAG AA недостижимо), 1 баг enum, hardcoded строки, градиенты, hover-translate, emoji в навигации, нет feature flags, нет mobile bottom nav, нет self-hosted Inter.
- **Найден P0-баг:** `app/templates/catalog.html` использует старое значение `unacceptable` (строки 74, 88-89); миграция `strong_aversion` не покрыла UI-слой.
- **Найдены hardcoded RU строки** в `training.html` (8 строк вне i18n словаря).
- **Найдены hardcoded EN строки** в `dashboard.html`, `index.html`, `catalog.html`, `calendar.html`.

### Топ-3 критичных фронтенд-фикса
- [x] catalog.html: enum `unacceptable → strong_aversion` + i18n для строки (P0-баг) — **FIXED S39**
- [x] training.html: вынести 8 RU строк в t.* словарь — **FIXED S39**
- [x] index.html: убрать градиент в h1 + emoji из заголовков; добавить ARIA везде — **FIXED S39**

## Frontend-фиксы (Session 39, 2026-08-09)

Детальный отчёт: `memory/FIX_SESSION_39.md`.

### Закрыто
- [x] P0-баг `unacceptable → strong_aversion` в catalog.html + i18n
- [x] Хардкоженные RU/EN строки вне t.* словаря
- [x] Градиенты в `<h1>` (index.html) и в progress (achievements.html)
- [x] Эмодзи в 8 заголовках (admin, llm_configs, catalog, notifications, privacy, my_entities, tasks, dashboard)
- [x] Hover-translate/shadow-lift с 16+ карточек
- [x] CSS variables для light/dark тем (DESIGN.md 6.2) в base.html
- [x] Skip-link первым focusable (WCAG)
- [x] aria-label на `<nav>`, aria-current="page" на активной ссылке
- [x] aria-live на `<main>` + HTMX live region
- [x] Focus ring `2 px + 2 px offset` через `*:focus-visible`
- [x] Motion easing `cubic-bezier(0.2, 0, 0, 1)` через CSS variable
- [x] Touch target `min-h-[44px]` на критичных кнопках
- [x] CSRF hidden input в 8 новых формах (catalog opt-in, all training forms, dashboard theme/locale, tasks forms)
- [x] Авто-submit `onchange="this.form.submit()"` удалён (DESIGN 9.2)

### Не закрыто (deferred)
- [ ] `dashboard_v2.html` refactor: 4 графика одновременно нарушают DESIGN 11 (≤2)
- [ ] `calendar.html` JS: hardcoded EN (Mon–Sun, Allowed, Passive, Templates, Overrides) — нужен async i18n
- [ ] `inventory.html` JS: hardcoded EN (All, Clothing, Equipment, Cosmetics) — аналогично
- [ ] `import_data.html`: hardcoded `https://localhost:8443` URL в copy-button
- [ ] Полная миграция классов Tailwind → custom CSS variables в шаблонах
- [ ] XSS-fixture тесты (REM A14) — только запланированы
- [ ] Self-hosted Inter Variable font (DESIGN 7.1)
- [ ] Mobile bottom nav (DESIGN 4.4)
- [ ] JS-hoist в отдельные ES modules (DESIGN 15.4)

## Следующие шаги
1. Сессия 38: фикс bif в AGENTS.md + P0/P1 работы из аудита
2. Деплой: docker compose up -d db app, хост-nginx reverse proxy, certbot, seed
