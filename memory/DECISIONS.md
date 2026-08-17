# Реестр решений (ADR)

Формат: `ID | Дата | Тема | Решение | Статус`. Статусы: `принято` / `отложено` / `отклонено`.
Новая запись добавляется **сразу** после принятия решения.

| ID | Дата | Тема | Решение | Статус |
| --- | --- | --- | --- | --- |
| ADR-001 | 2026-08-06 | Semantic Masking | **Отклонено**. Гибридная генерация: каталог + LLM выбирает | принято |
| ADR-002 | 2026-08-06 | Провайдеры LLM | BYOK: Omniroute, Groq, OpenRouter | принято |
| ADR-003 | 2026-08-06 | Telegram-бот | aiogram 3.x, вебхук, 6 команд, код-привязка | принято |
| ADR-004 | 2026-08-06 | Сессии | created/active/ended, правила JSON | принято |
| ADR-005 | 2026-08-06 | Штрафы | В задаче: фикс XP / % / множитель, эскалация | принято |
| ADR-006 | 2026-08-06 | XP, комбо, челленджи | Формула, комбо +10%→+50%, челленджи авто+ручные | принято |
| ADR-007 | 2026-08-06 | Каталог задач | Категории + теги, 3 типа, params_schema, итерации с таймером | принято |
| ADR-008 | 2026-08-06 | Опт-ин | да/нет + рейтинг + шкала желания | принято |
| ADR-009 | 2026-08-06 | Публикация задач | Без модерации, с авторством | принято |
| ADR-010 | 2026-08-06 | Доска достижений | Комбинированная, ник, скрытие, SVG-бейджи | принято |
| ADR-011 | 2026-08-06 | Регистрация | Простая, без подтверждения email | принято |
| ADR-012 | 2026-08-06 | Рейт-лимиты | Отложено | отложено |
| ADR-013 | 2026-08-06 | Подписки/оплата | Заглушка, без логики | отложено |
| ADR-014 | 2026-08-06 | Бэкапы | pg_dump по cron | принято |
| ADR-015 | 2026-08-06 | Тесты | pytest unit + интеграционные | принято |
| ADR-016 | 2026-08-06 | i18n / темы | EN/RU, dark/light с сохранением | принято |
| ADR-017 | 2026-08-06 | Язык контента | По locale пользователя | принято |
| ADR-018 | 2026-08-07 | Тренировка | TrainingDay + subtasks, облегчённая геймификация | принято |
| ADR-019 | 2026-08-07 | Фоновый авто-анализ | APScheduler/cron, отложено до деплоя | отложено |
| ADR-020 | 2026-08-07 | Гибкая балльная система | JSON в Entity.gamification_config, PointsTransaction для аудита | принято |
| ADR-021 | 2026-08-07 | Импорт данных | CSV+JSON шаблоны, upload, API-push, upsert | принято |
| ADR-022 | 2026-08-07 | Замеры тела | BodyMeasurement, Chart.js morning/evening | принято |
| ADR-023 | 2026-08-07 | Инвентаризация | InventoryItem, фильтры, shopping list | принято |
| ADR-024 | 2026-08-07 | Расписание дня | ScheduleRule: day_of_week+time+task_type+recurring | принято |
| ADR-025 | 2026-08-07 | Календарь доступности | CalendarTemplate + AvailabilityWindow (allowed/disallowed/passive_only) + CalendarOverride (отпуск). Entity.intensity. `is_available()` utility. Отпуск = шаблон «Vacation» через override | принято |
| ADR-026 | 2026-08-07 | Интеграция календаря в LLM | Расписание дня инжектится в context_builder → промпт. LLM получает окна с политиками и intensity сущностей | принято |
| ADR-027 | 2026-08-07 | Отработка штрафов и профили баллов | PenaltyRedemption для отслеживания отработок (pending→completed→возврат баллов). PointsProfile как переиспользуемый шаблон баллов/штрафов/бонусов через назначение на сущность. Threshold effects: уведомления при negative/warning/good. Gamification editor через PUT /entities/{id}/gamification | принято |
| ADR-028 | 2026-08-07 | Telegram-бот v2 с реальной логикой | aiogram 3.x webhook. Бот вызывает внутренние сервисы (generate_task, on_task_completed, on_task_interrupted) напрямую, а не через HTTP. Привязка через 6-значный код (сессия 30 мин). Уведомления через send_telegram_notification() — хук в gamification handler после каждого db.flush(). Webhook auto-setup в lifespan. Бот-username и webhook URL конфигурируются через settings | принято |
| ADR-029 | 2026-08-07 | Штрафы v0.7 — оставить как есть | Штрафы сохраняются в полном объёме: PenaltyRedemption, эскалация, PointsProfile, Threshold effects. Безусловные остановки без последствий не допускаются — прерывание всегда со штрафом. Вразрез с REMEDIATION_SPEC.md раздел 4.3, но утверждено владельцем | принято |
| ADR-030 | 2026-08-07 | LLM-режимы: full и abstract | Два режима: `full` (по умолчанию — LLM видит названия, генерирует параметры, пишет reasoning) и `abstract` (opaque ID, только candidate_id+variant_id+position — для провайдеров со строгими фильтрами). Режим выбирается в LLMProviderConfig. Abstract-режим упрощённый, т.к. LLM не видит контент для анализа | принято |
| ADR-031 | 2026-08-07 | Entity — оставить единой моделью | Entity не разделяется на PracticeTemplate + PracticeVariant + UserPractice. Остаётся единой моделью с доработками полей по мере необходимости. Вразрез с REMEDIATION_SPEC.md раздел 5.2 | принято |
| ADR-032 | 2026-08-07 | Training — оставить отдельной страницей | Training сохраняется как полноценная отдельная страница с LLM-подзадачами и анализом дня. Не заменяется на Plan of the day в дашборде. Вразрез с REMEDIATION_SPEC.md раздел 12.3 | принято |
| ADR-033 | 2026-08-07 | Вторичные модули — оставить в главном меню | Points, Measurements, Inventory, Schedule, Import, Calendar остаются в главной навигации дашборда. Не скрываются за «Ещё» и feature flags. Вразрез с REMEDIATION_SPEC.md раздел 12.3 | принято |
| ADR-034 | 2026-08-07 | raw_llm_response — опциональное хранение | Хранение raw_llm_response опционально (флаг в LLMProviderConfig, по умолчанию включено). Usage-метрики (токены, стоимость) хранятся всегда и отдельно. Краткий контекст (entity_id, статус) для точечной отладки. Компромисс между REMEDIATION_SPEC.md раздел 7.5 и текущей реализацией | принято |
| ADR-035 | 2026-08-11 | Каталог: ActivityCategory | Новая таблица категорий (id, slug, title, description, sort_order, is_active, parent_id — иерархия) + seed 16 категорий из `examples/update.md`. `entities.category` (строка) мигрируется в таблицу (non-destructive, rollback; legacy-значение сохраняется). Развитие ADR-007 | принято |
| ADR-036 | 2026-08-11 | ActivityLog → ActivityTask эволюцией | Задача (ActivityTask) НЕ вводится новой таблицей: `activity_logs` эволюционирует (+title_override, scheduled_at, planned_comment, completion_comment, actual_parameters; статусы 3 → 11). Все интеграции (XP, баллы, штрафы, LLM, календарь, точки по activity_log_id) продолжают работать без рефактора | принято |
| ADR-037 | 2026-08-11 | Сессии: принятие (accepted) | Сессия = связный набор взаимосвязанных активностей на ограниченное время (пример: вечерний сценарий, N действий в течение часа). Фаза планирования (status=created) — свободное наполнение; после принятия (`accepted_at`) любое изменение состава/параметров задач = штраф. Развитие ADR-004 | принято |
| ADR-038 | 2026-08-11 | Штрафы: уточнение ADR-029 | cancelled до начала / skipped / not_applicable — без штрафа и без награды; partially_completed — **без награды**; stopped (начата и остановлена) — штраф по ADR-029. Отдельный флаг на активности `penalty_enabled` переопределяет поведение. Не считать cancelled/stopped «нарушением» в статистике | принято |
| ADR-039 | 2026-08-11 | Training — отдельная программа | TrainingDay/TrainingLogEntry остаются самостоятельной системой «программ»: отдельный прогресс, LLM-анализ, корректировки (снизить планку), synergy с диетами. Новая модель задач (ADR-036) её не поглощает; задачи могут ссылаться на training_day_id | принято |
| ADR-040 | 2026-08-11 | Статус-машина 11 состояний + аудит | Строгий enum: draft/planned/in_progress/completed/partially_completed/skipped/cancelled/stopped/substituted/not_applicable/review_needed + правила переходов + таблица `activity_task_history` (task_id, prev/new status, changed_at, comment, parameter_snapshot, actor_id). Переходы — атомарные гарды (паттерн complete_once: UPDATE WHERE status=…, rowcount=0 → idempotent) | принято |
| ADR-041 | 2026-08-11 | Типизированный DSL параметров | `parameter_schema` формализуется: key/title/type (string/integer/decimal/boolean/enum/multi_enum/duration/text)/required/options/min/max/unit_group/visible_when/allow_custom_value. planned_parameters и actual_parameters хранятся раздельно. Валидация через Pydantic (без eval) | принято |
| ADR-042 | 2026-08-11 | Title-генератор | Читаемый заголовок по шаблону «{count} {unit} — {activity_title}, {tool}, зона: {target_area}, интенсивность {intensity}/5, позиция: {position}»; пустые части пропускаются; fallback на title_override → ручной заголовок → «Свободная задача»; i18n EN/RU | принято |
| ADR-043 | 2026-08-11 | Справочник зон тела (BodyPart) | Иерархическая таблица body_parts (slug/title/body_system/sensitivity, parent_id self-FK). 40 seed-записей (голова→лицо→губы, торс→грудь, …). TaskBodyTarget — линковка задачи с зонами (роль target_area/contact/avoid, сторона, интенсивность 1-5, name_snapshot). ActivityBodyPartRequirement — шаблонные требования (min/max count, allowed_roles). Развитие ADR-041 (DSL-тип body_part_selector) | принято |
| ADR-044 | 2026-08-11 | Справочник мест (TaskLocation) | task_locations: системные (25 seed — дом→спальня→кровать, …) + пользовательские; location_type (room/furniture/outdoor/venue/vehicle/other), privacy_level (system/public/private). TaskLocationUsage связывает задачу с местом (роль primary/secondary/prohibited, name_snapshot). Archive вместо delete при наличии ссылок (409). DSL-тип location_selector | принято |
| ADR-045 | 2026-08-11 | Категории инвентаря + dual-статус | inventory_categories — нормализованная таблица (16 категорий из update2.md: impact_tool, restraint, wearable, clothing, …). InventoryItem получает FK + inventory_status (available/in_use/cleaning/charging/maintenance/unavailable/archived — operational-измерение). Старый status (need/ordered/bought/built — shopping-измерение) сохранён — два независимых измерения | принято |
| ADR-046 | 2026-08-11 | DSL-селекторы + таблицы требований | 3 новых DSL-типа (inventory_selector, body_part_selector, location_selector) с single/multiple mode. Параллельно — таблицы Activity*Requirement для шаблонных требований. Оба подхода сосуществуют: DSL для параметров задачи, таблицы — для описания «какой инвентарь/зоны нужны для этой активности». Тесты validate_params проверяют оба пути | принято |
| ADR-047 | 2026-08-11 | LockTimer: модуль, не второе приложение (D-001) | LockTimer живёт внутри Practice Loop как отдельный bounded context с таблицами `lock_*`, но может быть единственным включённым доменом. Никакого второго репозитория, auth, React/Vite или отдельного deployable. Один код, один Alembic head, три варианта: tracker/timer/combined | принято |
| ADR-048 | 2026-08-11 | Варианты приложения (D-013, PL-CMP-001) | `APP_PRODUCT_VARIANT=tracker|timer|combined` управляет module registry. Выключенный домен не регистрирует routes, nav, jobs. Смена варианта не удаляет данные. CSS-скрытие недостаточно. Разные ветки кода/схемы для вариантов запрещены | принято |
| ADR-049 | 2026-08-11 | Platform Foundation (D-014) | Auth/user/timezone/i18n/theme/outbox/media/LLM config/calendar/notification/rewards — общие platform contracts. Timer не импортирует Tracker models/services. Platform-owned слой `app/platform/` для нейтральных контрактов; Tracker compatibility через adapters | принято |
| ADR-050 | 2026-08-11 | Timer Core и Social принимаются раздельно (D-003) | Первый mergeable результат — полностью приватный Timer Core + platform composition (C0–C9). Platform Social — отдельный branch/PR с собственным gate. Timer Social Adapter включается только после Timer Core gate | принято |
| ADR-051 | 2026-08-11 | User.timezone (LT-INT-002) | Обязательный timezone с default UTC; существующим пользователям — UTC + banner до подтверждения. IANA-валидация через zoneinfo. Хранится в users.timezone + timezone_confirmed_at | принято |
| ADR-052 | 2026-08-11 | Feature flags — default off (03A §7) | Все новые flags (LOCKTIMER_CORE_ENABLED, SOCIAL_ENABLED, etc.) default FALSE для staged rollout. APP_PRODUCT_VARIANT default combined для upgrade. Fresh deploy требует явного значения. На старте конфигурация валидируется и строится immutable ProductComposition | принято |
| ADR-053 | 2026-08-11 | LockTimer domain + persistence (C1+C2) | 6+7+10 enums/state machines (sessions/draft→active→safety_stopped; slots/pending→eligible→open→closed; tasks/scheduled→visible→submitted→…→completed; transition tables + can_transition). Domain: duration/extension/clamp, canonical JSON+SHA256, deterministic random (seed+rule+index→[0,1)), occurrence key, seed generation+commitment. Persistence: 12 таблиц lock_* (templates, sessions, snapshots, inner_periods, slot_rules/occurrences, task_rules/occurrences, penalty_events, audit_events, job_receipts, outbox_events); миграция 025 (PG15 up/down/up ✅); owner-scoped repositories + conditional UPDATE. 31 domain unit test | принято |
| ADR-054 | 2026-08-11 | LockTimer execution services (C3+C4+C5) | DraftService (create/update draft, add/delete slot+task rules); StartService (atomic start via conditional UPDATE+rowcount, canonical snapshot+hash, occurrence materialization); Materializer (5 slot schedule types: every_n_days/exact_datetime/recurring_from_date/flexible_window_once/after_previous_close; 6 task schedule types: daily/every_n_days/recurring_from_date/exact_datetime/anytime_before_end/deterministic_random; rolling horizon 90 days); Job runner (enqueue idempotent by job_key, claim via SELECT FOR UPDATE SKIP LOCKED, lease); SlotService (open with eligibility+late-open extension, close); TaskService (reveal scheduled→visible, submit, complete idempotent, skip); PenaltyService (allowlisted types + idempotency key, add_time with cap/max_end); SafetyStop (immediate transition active→safety_stopped + cancel future occurrences); Outbox (transactional domain events). SQLite compat: returning() → update+flush+select. 29 service integration tests. | принято |
| ADR-055 | 2026-08-11 | LockTimer LLM + UI (C7+C8) | lock_llm_proposals (kind/status/items JSON/usage tracking, migration 026); timer-aware LLM context builder (build_timer_context, format_timer_prompt); proposals API (POST create, GET, apply/reject items by type slot_rule→add_slot_rule, task_rule→add_task_rule); SSR timer pages (/locktimer overview — active session/drafts/history/slots/tasks; /locktimer/sessions/{id} detail — rules/occurrences/proposals); LOCKTIMER_CORE_ENABLED=true in tests; +23 i18n keys EN/RU. 9 integration tests. | принято |
| ADR-056 | 2026-08-11 | Universal media + verification (platform C6) | media_assets table (owner-scoped, staged→ready→archived pipeline, MIME+magic-bytes, SHA-256, thumbnail via Pillow, dimensions); verification_challenges (HMAC-SHA256, constant-time compare, TTL, max attempts, code never returned after creation); API: POST upload, GET serve/thumbnail, DELETE staged-only, POST finalize; POST create/verify/GET status challenge. OCR deferred. Migration 027. +19 tests. **507/507 ✅**. | принято |
| ADR-057 | 2026-08-11 | C9 hardening — test matrix, concurrency, secrets, runbook | Concurrency tests (11 scenarios: double-start/open/close/penalty/job/outbox, cross-user safety-stop, complete idempotency, recovery). Secret scan (no hardcoded secrets found). Owner allowlist gate (locktimer_owner_allowlist config). RUNBOOK.md (deploy, migration, rollback, backup/restore, incident playbooks, SLOs). pre_deploy_check.sh (7-step validation). /healthz/readiness endpoint. **518/518 ✅**, ruff ✅. | принято |
| ADR-058 | 2026-08-12 | Platform Social S0+S1 — foundation + subject registry | `app/platform/social/` — независимый пакет, не импортирует Tracker/Timer. social_profiles: alias-based public identity (3-80 chars, case-insensitive), consent versioned. social_subjects: opaque registry для domain adapters. SocialSubjectAdapter Protocol (14 методов) + adapter registry. SOCIAL_ENABLED gate в composition. 3 таблицы, миграция 029. **538/538 ✅** | принято |
| ADR-059 | 2026-08-12 | Platform Social S2 — relationships, blocks, grants | Единый relationship/block graph на весь продукт. Invitation lifecycle: pending→accepted/declined/expired/revoked, cooldown 24h. Display_role — UI-лейбл без capability grants. Grants: subject/module/global scope, JSON caps, separate accept. Block отменяет pending + отключает accepted grants. Notification outbox (9 types). 4 таблицы, миграция 030, 14 API эндпоинтов. **538/538 ✅** | принято |
| ADR-060 | 2026-08-12 | Timer numbered tags (S72) | Номерные бирки: close_tag_number на LockSlotOccurrence (свободный формат), require_tag на LockSlotRule (опционально). verify_tag: сверка номера, расхождение → lock_tag_violations. Бирка опциональна при закрытии если require_tag=False. Для будущих social-функций (уведомление keyholder, verification challenge). Миграция 028, 20 тестов. | принято |
| ADR-061 | 2026-08-12 | Platform Social S4+S6 — verification + tracker adapter | Verification: policies/requests/votes, quorum check, comments; SocialSubjectAdapter для tracker-домена. **538/538 ✅** | принято |
| ADR-062 | 2026-08-12 | Терминология: lock = chastity, таблицы не меняем (PD-017) | Честный фронт EN/RU: Lock Timer / Lock Session / Unlock Windows / Seal (# пломба); кнопки Unlock/Lock; таблицы lock_* и API не переименовываются (риск регрессий без продуктовой ценности) | принято |
| ADR-063 | 2026-08-12 | Мобильный клиент: кроссплатформенный, после портала (PD-018) | Полноценный клиент Personal (Flutter/RN, выбор PQ-008) после запуска портала; API-first + push-уведомления | принято |
| ADR-064 | 2026-08-12 | Масштабирование: обязательство по трём осям (PD-019) | (1) много пользователей, (2) объём данных одного, (3) горизонтальная инфраструктура; owner-scoped контракт, storage-абстракция, JSON-first; без преждевременной постройки | принято |
| ADR-065 | 2026-08-12 | JSON-first контракт для action-эндпоинтов (PD-020) | Новые action-эндпоинты возвращают JSON; HTMX через fetch; HTML — только страницы; пилот: timer start/safety-stop | принято |
| ADR-066 | 2026-08-13 | Device-tz дневные бакеты графиков (PD-021) | Дневные ряды бакетируются в Python через local_date (device-день), не SQL func.date (UTC-день); подписи local_today() | принято |
| ADR-067 | 2026-08-13 | Фоновые задачи: границы суток через конфиг-tz | Training auto-analysis берёт «сегодня» из tg_auto_analysis_tz (IANA, default UTC), не из request ContextVar | принято |
| ADR-068 | 2026-08-13 | Memory v2 | Многоуровневая память L0–L4 (контракт, wiki/ADR, generated facts, hybrid code retrieval, local-only эпизоды); milestones M0–M6; M0+M1 реализованы | принято |
| ADR-069 | 2026-08-13 | M3 pilot: Qdrant local + embedding через Omniroute, только vectors | Qdrant local (shadow) — единственный пилот; embedding через Omniroute (text-embedding-3-small, 1536-dim, remote /v1/embeddings) — аmended 2026-08-14 (Сессия 118): BGE-M3 заменена, т.к. fastembed её не поддерживает + VPS без локальных моделей; QMD и code graph отложены; зависимости только optional dev-group (qdrant-client), рантайм не трогается | принято |
| ADR-070 | 2026-08-14 | Границы LLM для личного контура (расширение ADR-030/034) | Личный контур — первая очередь: LLM подключается полностью через Omniroute (первый источник, подбор моделей, harness, инструменты). 1) **Гибрид сохраняется**: LLM выбирает из каталога + opt-in, но режим названий (полные / обезличенные) регулируется per-provider через `llm_mode` (full/abstract, уже есть). 2) **Параметрическая генерация через промпт-шаблоны**: пользователь осознанно создаёт шаблон промпта с параметрами, сохраняет как переиспользуемый шаблон; LLM генерирует по шаблону. 3) **LLM-верификация медиа как истина в последней инстанции**: для соло-игр подтверждение кодов и закрытия пояса верности через LLM-анализ фото (развитие Q13; OCR не требуется — LLM понимает изображения). 4) **Приватная база знаний LLM** для обогащения промптов (на базе существующего векторного индекса + Omniroute-эмбеддингов). 5) **Библиотека типовых промптов** по функциональным блокам. Комплаенс-красная линия остаётся: никакого обхода safety-фильтров провайдеров и маскирования контента (ToS + риск блокировки ключа Omniroute/upstream). Статус: решено владельцем 2026-08-14 (Сессия 119), реализация — этапами в STAGE_PLAN | принято |
| ADR-071 | 2026-08-14 | M5: freeze legacy memory v1 (Memory v2 milestone) | Legacy `memory/` (кроме `DECISIONS.md`) **заморожен** (frozen headers): `SESSIONS.md`, `STATUS.md`, `CHANGELOG.md`, `OPEN_QUESTIONS.md`, `CONTEXT.md` больше не дописываются — архив; история сессий — Git. Активная память — Memory v2 (ADR-068): решения `DECISIONS.md` (единственный активный legacy, компилируется в `docs/adr/`), знания `docs/wiki/`, вопросы `docs/questions/`, факты `docs/state/`. `memoryctl lint` + `facts --check` — **required** в CI (был informational). В benchmark добавлена метрика **impact-recall** (ground truth по символам → полнота нахождения всех затронутых файлов/тестов/миграций; задел под graph-пилот). AGENTS.md/README.md/DOCUMENTATION_MAP обновлены. 758/758 ✅ | принято |
| ADR-072 | 2026-08-14 | Q14: penalty честно в HTTP + Omniroute в портал (Шаг 4) | 1) **Штрафы применяются по политикам правил**: `skip_task` применяет `rule.penalty_policy` (points/add_time), `close_slot` при позднем закрытии (now > close_due_at) применяет `rule.late_close_policy`; идемпотентно по occurrence (`skip:{id}` / `late_close:{id}`); неизвестный тип политики логируется и пропускается. API skip/close возвращают JSON (ADR-065) с `penalty`-блоком (`serialize_penalty_event`); UI показывает реальный результат («Штраф применён: -5 points») вместо «Penalty may apply»; формы переведены на fetch + i18n-ключи (6 новых EN/RU). 2) **Omniroute в портале**: `Settings.omniroute_host/api_key/embedding_model`; seed-пресет Omniroute строится из settings (host → /v1, key шифруется), активен по умолчанию; .env.example обновлён. 767/767 ✅ | принято |
| ADR-073 | 2026-08-14 | Шаг 5: икон-пак PracticeLoop + Gate B (async media, transaction boundary, browser smoke) | 1) **Икон-пак интегрирован (design/icons → runtime)**: sprite.svg + favicon скопированы в app/static/; макрос `components/icon.html` (`{{ icon('name', cls) }}`); все emoji/inline-SVG заменены в base.html (nav desktop/mobile, theme sun/moon, logout, flash), index, dashboard, training, import_data, llm_configs, admin, privacy, my_entities; JS-хелпер `window.plIcon` (DOM API, без innerHTML — §6.7) для diets/inventory. Иконки будущих модулей зарезервированы, не используются. Обязательство в AGENTS.md/DESIGN.md: иконки только из пакета, при нехватке — сообщать. Недостающие (thumbs-up/fire для social encourage — значения контента) оставлены как emoji, зафиксировано. 2) **P2-2 async media**: `save_media` → Pillow/диск в thread pool (`asyncio.to_thread`), decompression bomb guard (`PILLOW_MAX_IMAGE_PIXELS` + escalate warning→error), тест. 3) **P1-5 transaction boundary**: `tests/test_transaction_boundary.py` — allowlist legacy (28 файлов), новые роутеры без db.commit() (locktimer/social уже чистые); media upload/finalize переведены на auto-commit get_db (delete оставлен явным — файл удаляется после фиксации БД). 4) **P1-4 browser smoke**: optional `e2e` dev-group (playwright), `tests/e2e/test_browser_smoke.py` (register→dashboard→tasks→timer→no console errors), CI job e2e (postgres + alembic + chromium). 776/776 ✅ (+9), ruff ✅ | принято |
| ADR-079 | 2026-08-14 | Шаг 9c: Inventory/Media patterns (Media Vault, крупные изображения, verified state) | 1) **Media Vault `/media`** (новая SSR-страница): плитки с изображением ≥160×120 (thumbnail или приватный стрим, object-cover), подпись «дата · тип · provenance» (inventory_item → name, activity_log → title; остальные тип+id), verified-бейдж (последний `media_verification_results`: verdict + тип + confidence), retention «Приватно · только вы»/«В архиве», state-чип staged/ready/archived; upload-форма (staged, owner_type=general); nav sidebar → `/media` (заменён JSON-эндпоинт). 2) **Inventory**: изображение 160×120 (`w-40 aspect-[4/3]`) + placeholder-иконка, бейджи → токены, оболочка → pl-surface. 3) **i18n `mvt_*`** (избегаем коллизии: `mv_*` — страница `/llm/verify`). 869/869 ✅ (+6 test_design_v2_9c), ruff ✅ | принято |
| ADR-082 | 2026-08-14 | Шаг 9f: Visual QA, light-тема контрасты, browser-матрица (DESIGN_V2 §20) | Светлая тема = первый класс: `--text-muted` #6b5e53; цветные тексты `-700 dark:-400`; белый текст на `bg-emerald/green-500/600` → фон -700; JS-шаблоны (points/dashboard/calendar/diets/measurements/locations/body_parts) в токен-пассе (text-slate/gray→токены); axe-маршруты 8×2 темы; CSRF-кука loopback-aware (WebKit); playwright `workers: 2` (Firefox font-flake). 36 passed/6 skip/0 fail, ruff ✅, i18n 876/876 | принято |
| ADR-083 | 2026-08-16 | Шаг 10: Mobile Foundation (M4) — bearer-auth + JSON-first + push-устройства | 1) **Bearer-auth**: `POST /api/v2/auth/token` (email+пароль → access JWT + refresh), `/refresh` (ротация), `/revoke`, `GET /tokens` + `POST /tokens/{id}/revoke`, `GET /me`; access JWT с claim `type=access` (refresh/не-access JWT отвергаются), refresh — непрозрачный `secrets.token_urlsafe`, в БД только SHA-256 (`api_tokens`), ротация + revocable, sliding 30 дней (`refresh_token_expire_days`). 2) **JSON-first dual-mode (ADR-065)**: locktimer action-эндпоинты (start/safety-stop/open/reveal/complete/правила/шаблоны) отдают JSON при `Authorization: Bearer`, redirect для HTMX-форм — helper `app/api/responses.action_response`; skip/close/validate уже JSON. 3) **Push-устройства**: `push_devices` (register upsert/list/deactivate/delete, cross-user) + `app/push` (PushSender protocol + registry + `dispatch_push`, `PUSH_PROVIDER=none|logging|fcm|apns`, default none) + hook в gamification (best-effort). 4) **Медиа URL-контракт**: `GET /api/v2/media/{id}` + `/thumbnail` работают по bearer. Миграция 040, +14 тестов test_mobile_foundation. ruff ✅ | принято |
| ADR-084 | 2026-08-16 | Шаг 11: M3 Personal Suite — TARGET_ARCHITECTURE + DATA_LIFECYCLE + Medication Organizer | 11a: созданы `TARGET_ARCHITECTURE.md` (bounded contexts, события, мобильный API-контракт) и `DATA_LIFECYCLE.md` (закрывает PQ-006). 11b: **Medication Organizer** (relief-only, PD-013) — 5 таблиц (`medications`/`med_kits`/`med_stocks`/`med_schedules`/`med_intakes`), миграция 041, `/medications` (due today / expiring / low-stock + инлайн-CRUD), JSON API `/api/v2/medications` (bearer), CSV-экспорт для врача, feature flag `medication_enabled`. 10/10 тестов ✅ | принято |
| ADR-085 | 2026-08-17 | Шаг 12: Медицина × игра — смягчение PD-013 (adherence) | **PD-013 смягчён (явно заменяет пункт о баллах)**: своевременный приём (adherence) может давать XP и достижения (позитивное подкрепление, cap/день); **пропуск/мисс никогда не отнимает баллы и не штрафуется** (негативная геймификация здоровья запрещена). Медицинский сигнал остаётся relief-only (открыть окно/смягчить/пауза/стоп). Интеграции: (1) adherence-XP + достижения `med_first`/`med_adherence_3/7/30` (миграция 042), хук в оба intake-эндпоинта; (2) LockTimer relief-задачи — med schedule → task rule с `penalty_policy` выключенным; (3) «сегодня» трекера — due-приёмы видны в дашборд-блоке (view-level, без ActivityLog); (4) одноразовая миграция инвентарь→медицина (`POST /medications/migrate-inventory`, provenance `source_inventory_id` + маркер `migrated_to_medication`, миграция 043). 24/24 таргетных ✅ (ADR-085). | принято |
| ADR-086 | 2026-08-17 | Шаг 13: Health + Cycle foundation (ROADMAP §7 4D) | Второй Health-срез личного контура, **relief-only (PD-013)**: никакой игровой интеграции, никаких штрафов; все записи Private Record (DATA_LIFECYCLE.md); расчётная фаза Cycle никогда не выдаётся за факт (§9.4). 4 таблицы (`health_states` — check-in: настроение/энергия/сон/симптомы/восстановление; `lab_records` — анализы с оригинальным диапазоном лаборатории; `cycle_settings` — одна строка на пользователя; `cycle_events` — факты цикла), миграция 044. Страница `/health` (check-in upsert по дате, история, анализы с подсветкой вне-диапазона, Cycle: настройки + события + расчётная фаза menstrual/follicular/ovulation/luteal по дню цикла от последнего начала кровотечения, перерыв ≥3 дней = новый цикл; всегда `phase_estimated`). JSON API `/api/v2/health` (bearer: сводка/states/labs/cycle + POST state/labs/cycle-events). Дашборд-блок `dash-block-health` (настраиваемый в /settings). Feature flag `health_enabled` (default true). 20/20 таргетных + 55/55 регрессионных ✅, ruff ✅, i18n 1009/1009, single head ✅. | принято |
| ADR-087 | 2026-08-17 | LLM-режим пользователя (safe/expanded) + LLM-разбор анализов | Введён **`prefs.llm_mode`** (safe — default, только факты; expanded — рекомендации/советы/интерпретация). Режим управляется в /settings (LLM mode) и **влияет на все LLM-блоки** (распространено в той же сессии): `app/llm/mode.py` — единый `llm_mode_hint()` аппендится к системным промптам задач/тренировок/диет/промпт-шаблонов; параметр `llm_mode` у всех pipeline-функций (None → из prefs); Telegram `/next` и фоновый scheduler передают режим явно из `user.prefs`. **Дисклеймер «не врач» убран из промптов — только в UI** (владелец, Session 137); в промптах остаётся «не выдумывай медицинские утверждения» (достоверность). Первый специализированный потребитель — **LLM-разбор анализов** (`app/llm/pipeline/health.py`): safe — нейтральный пересказ + вопросы врачу; expanded — рекомендации (в т.ч. по схеме приёма: активные med_schedules в контексте). Эндпоинты: `POST /health/analyze` (form) и `POST /api/v2/health/analyze` (JSON). Usage-трекинг. Комплаенс: режим НЕ обходит safety-фильтры и не маскирует контент — только расширяет инструктивную рамку промпта. 10 новых тестов + 30/30 health + 127/127 регрессионных (training/prompt_templates/tasks/diets) ✅, ruff ✅, i18n 1022/1022. | принято |
| ADR-093 | 2026-08-17 | Шаг 17: Personal Insights (ROADMAP §7 4E) | По решению владельца «сделать следующий модуль личного контура: 4E Personal Insights». Явно запрошенный кросс-модульный LLM-анализ личных данных (PRODUCT_OVERVIEW §12): тенденции и связи между активностями/таймером/журналом/здоровьем/уходом/тренировками/диетами. **Relief-only (PD-013)**: без игровой интеграции. 2 таблицы (`insight_runs` — запуск: period_start/end, sections JSON, status, summary, usage; `insight_findings` — находки по разделу: section, title, summary, used_data JSON), миграция 050, single head. LLM-пайплайн `app/llm/pipeline/insights.py` + `insights_prompts.py`: контекст только из выбранных разделов за период, промпт требует показывать использованные данные и **не объявляет корреляцию причиной**, режим llm_mode (ADR-087), usage на LLMProviderConfig. Страница /insights (пикер разделов/периода + результат + история с удалением), JSON /api/v2/insights (GET/POST/GET runs/{id}). Дашборд-блок dash-block-insights, nav «Инсайты» (иконка insights.svg), флаг insights_enabled. 11/11 таргетных + 164 регрессионных ✅, ruff ✅, i18n 1196/1196, single head ✅. | принято |
| ADR-092 | 2026-08-17 | Шаг 16b: Care Products — средства/косметика с привязкой к инвентарю | По решению владельца «каталог средств/косметики для ухода с привязкой к инвентарю». **Relief-only (PD-013)**: справочник без игровой интеграции. 2 таблицы (`care_products` — позиция средства: name/category cleanser/toner/serum/moisturizer/mask/exfoliant/sun/body/hair/other, brand, notes, **inventory_item_id FK inventory_items SET NULL** — остаток/список покупок ведётся в инвентаре; `care_entry_products` — many-to-many care_entries ↔ care_products, оба CASCADE), миграция 049, single head. Страница /care: секция «Средства и косметика» (форма + список с инвентарным бейджем и счётчиком использований), форма записи ухода — мультиселект средств. JSON API `/api/v2/care`: `/products` POST (201)/DELETE (204), `product_ids` в записях. Валидация владельца: чужой inventory_item_id/product_id → 400; удаление продукта чистит join-строки на уровне приложения + CASCADE в БД. 13/13 таргетных + 151 регрессионный ✅, ruff ✅, i18n 1166/1166, single head ✅. | принято |
| ADR-091 | 2026-08-17 | Шаг 16: Универсальный каталог активностей (сквозной) | По решению владельца «каталог сквозной, применим в любых активностях». Универсальный каталог как Entity (`activity_catalog`, миграция 048, single head): name/description/category_id (FK activity_categories)/tags/domains (JSON: journal/care/timer/tracker, пусто = сквозная)/owner_id (NULL = системная, видна всем)/is_public. **Замена свободных полей на FK-ссылку**: `sj_entries.catalog_item_id`, `care_routines.catalog_item_id`, `lock_slot_rules.catalog_item_id`, `entities.catalog_item_id` (все SET NULL) — свободный ввод только через создание своей записи каталога. Страница `/catalog` (просмотр/создание/удаление, фильтр по domain) + JSON `/api/v2/catalog` + хелпер `catalog_options(domain)` для пикеров. Интеграция во все 4 модуля: журнал, уход, окна таймера (причина/цель), трекер-задачи. nav-пункт «Каталог» (иконка library.svg), feature flag `catalog_enabled`. Каталог нейтрален (relief-only, PD-013): справочник без игровой интеграции. 18/18 таргетных + 154 регрессионных ✅, ruff ✅, i18n 1120/1120, single head ✅. | принято |
| ADR-090 | 2026-08-17 | Шаг 15: Personal Care (ROADMAP §7 4B) | Третий срез ухода личного контура, **relief-only (PD-013)**: никакой игровой интеграции, никаких штрафов; все записи Private Record (DATA_LIFECYCLE.md); снимок расчётной фазы Cycle никогда не выдаётся за факт (§9.4). 2 таблицы (`care_routines` — каталог процедур/рутин: area face/body/hair/hands/feet/other, kind home/salon, frequency_days, notes; `care_entries` — факты выполнения: entry_date, duration_minutes, skin_reaction 1–5, notes, снимок cycle_phase/cycle_day), миграция 047, single head. Страница `/care` (форма процедуры + журнал ухода + каталог рутин + история с фото). **Медиа**: `owner_type=care_entry` в media registry/allowlist, `POST /care/entries/{id}/media` (owner-scoped, чужой entry → 404) — фото динамики. **Связь с Cycle**: снимок расчётной фазы при создании записи. JSON API `/api/v2/care` (bearer: сводка + процедуры + записи + POST routines/entries). Дашборд-блок `dash-block-care` (процедуры за 30д / последняя / число рутин), настраиваемый в /settings. nav-пункт «Уход» (иконка routine.svg), feature flag `care_enabled` (default true). 17/17 таргетных + 126 регрессионных ✅, ruff ✅, i18n 1105/1105, single head ✅. | принято |
| ADR-089 | 2026-08-17 | Шаг 14b: Sexual Journal — медиа + связки с Tracker/Timer | По решению владельца «медиа в журнале + связка активностей с журналом + авто-запись при открытии окна таймера для плановой активности». (1) **Медиа**: `owner_type=journal_entry` в media registry/allowlist, `POST /journal/entries/{id}/media` (save_media → MediaAsset, owner-scoped, чужой entry → 404), фото-плитки в истории. (2) **Связка с Tracker**: `sj_entries.activity_log_id` (мягкая ссылка по ID без FK, валидация владельца — чужой task → 400), селект недавних активностей в форме, `source=activity` при привязке, отображение названия задачи. (3) **Timer-автозапись**: `lock_slot_rules.journal_auto` (миграция 046) — открытие окна авто-создаёт **draft**-запись (`source=timer_slot`, `status=draft`, idempotent, `ensure_timer_slot_entry` в open-флоу, журнал недоступен — действие таймера не прерывается); при закрытии окна API возвращает `journal_pending` (`get_pending_slot_entry`), CTA «Заполнить детали журнала» в session_detail; секция «Требуются детали» на /journal с формой `complete` (детали обязательны при закрытии). JSON API: `POST /api/v2/journal/entries/{id}/complete`. 11/11 новых тестов + 197 регрессионных ✅, ruff ✅, i18n 1082/1082, single head ✅. | принято |
| ADR-088 | 2026-08-17 | Шаг 14: Sexual Journal (ROADMAP §7 4A) | Первый срез журналов личного контура, **relief-only (PD-013)**: никакой игровой интеграции, никаких штрафов; все записи Private Record (DATA_LIFECYCLE.md): отдельное удаление, связи с Timer/Health — **по ID без раскрытия** (мягкие ссылки без FK). 2 таблицы (`sj_partners` — локальные псевдонимы партнёров, никогда не раскрываются; `sj_entries` — записи журнала: вид активности, дата/длительность, желание/возбуждение до начала, защита/контрацепция, оргазмы, интенсивность, удовлетворённость, удовольствие, реакции, эмоциональное состояние, aftercare, восстановление, заметки), миграция 045. Страница `/journal` (форма записи + история + псевдонимы). **Связь с Cycle (§16)**: при создании записи сохраняется снимок расчётной фазы (`cycle_phase`/`cycle_day`, помечен как оценка, не факт — §9.4). JSON API `/api/v2/journal` (bearer: сводка/записи/партнёры + POST). Дашборд-блок `dash-block-journal` (записи за 30д / последняя / ср. удовлетворённость), настраиваемый в /settings. Feature flag `journal_enabled` (default true). 15/15 таргетных + 99/99 регрессионных (health/medication/shell/design/icon) ✅, ruff ✅, i18n 1072/1072, single head ✅. | принято |
| ADR-081 | 2026-08-14 | Шаг 9e: Social tone + customization/discretion (DESIGN_V2 §13/§16) | 1) **Prefs-инфраструктура**: `users.prefs` JSONB (миграция 037, generic JSON в модели для SQLite-тестов) + `app/prefs.py` (UserPrefs dataclass, sanitize с дефолтами и доводкой dash_blocks, ContextVar); инъекция в шаблоны через `_load_prefs_context` в auth-зависимостях (get_current_user/get_optional_user) + контекст-процессор `_prefs_context` — ноль правок хендлеров. 2) **Тема system**: выбор dark/light/system; `data-theme-choice` + JS-резолв matchMedia в app.js; SSR-fallback `detect_theme`; set_theme принимает system и синхронизирует users.theme. 3) **Accent-наборы**: ember/sage/slate `html[data-accent]` — контраст-верифицировано (accent↔on-accent ≥4.5, accent-text↔surface ≥4.5). 4) **/settings**: appearance + блоки дашборда (порядок/скрытие, стрелки + drag&drop, hidden inputs) + discretion (off/always/schedule-окно, blur 0/1/2); POST /settings + quick-toggle /settings/discretion/toggle (JSON). 5) **Блоки дашборда**: рендер по `prefs.dash_visible` (id `dash-block-*`). 6) **Social tone §13**: токен-пасс 7 social-шаблонов (bg-white→pl-surface, gray→токены, indigo→`--dom-social*`); новые `--dom-social-text` (6.21/6.48:1) и `--dom-social-btn` (5.76/5.10:1). 7) **Discretion v1 §12**: нейтральные nav-лейблы (`dscr_*` EN/RU, макрос dscr_label в components/labels.html, импорт `with context` — иначе макрос не видит контекст), маскировка имён на дашборде (Item #N), favicon-neutral.svg, blur (media vault SSR + inventory JS `data-blur`), quick-toggle мгновенно без перезагрузки (сервер — источник истины для следующего SSR). Долг: уведомления не нейтрализованы (v1) → закрыт в сессии 134 (см. ADR-081 Status). 141/141 таргетных ✅ (+11 test_design_v2_9e), ruff ✅, node --check ✅ | принято |
| ADR-080 | 2026-08-14 | Шаг 9d: токен-пасс Personal-разделов + a11y-контраст (WCAG AA) | 1) **Токен-пасс 25 шаблонов**: legacy `bg-white/slate-*`, `text-slate-*`, `border/divide-slate-*`, индиго-кнопки → `pl-surface/-soft`, токены текста/границ, `pl-accent-bg`, `focus-ring → --focus`; осиротевшие `dark:*` удалены; намеренно оставлены тёмный код-блок import_data, семантические цветные чипы, градиенты. 2) **Контрастная политика (WCAG 2.2 AA)**: новый токен `--accent-text` (#743a37 light / #c9897f dark) — accent как цвет текста; `.pl-accent-text`/`.pl-accent-soft` используют его; тёмный `--accent` `#a95f58 → #a25a53` (кнопки accent-bg 4.40 → 4.76); индиго-ссылки `text-indigo-600 dark:text-indigo-400`. 3) **Форм-контролы**: aria-label фильтр-селектам /tasks и desire_level /entities/catalog (axe select-name, critical). Browser desktop-chromium: 5/5 ✅ (smoke/a11y/usability) + 1 осознанный skip; 113/113 таргетных pytest ✅ | принято |

| ADR-078 | 2026-08-14 | Шаг 9b: Active Timer + Tasks по DESIGN_V2 §8/§10 | 1) **Active Timer hero** (session_detail, state=active): крупный serif-таймер `pl-display` 6xl/7xl с tabular-цифрами (тот же `#countdown-display`, live-countdown сохранён); честная строка: локализованный режим (`locktimer_mode_duration`/`locktimer_mode_infinite`), устройство (chip), tz; диапазон `started → effective_end` + `cap` (max_end_at, показывается при отличии) + merge gap; **safety stop — первый и самый крупный CTA** (danger-токен), из header-действий убран (остался extend-horizon). Draft-сессии hero не получают — настройки/правила остаются. 2) **Токен-рестайл** session_detail (96 замен) и overview (70): gray/slate → `pl-surface` + токены (text/border/secondary/muted), indigo-кнопки → accent, статусы → success/warning/danger/info, timer-иконки → `--dom-timer`. 3) **Tasks §10**: переключатель плотности **compact/comfortable** (localStorage `pl_tasks_density`, класс `density-compact` на `#log-list` скрывает детали/комментарии, JS — в `tasks.js`, без inline-скриптов — audit `test_no_inline_scripts`); строка-строка с статусом/именем/параметрами/due/reason/действиями сохранена; добавлена due-строка (`scheduled_at`). 4) i18n: locktimer_mode_*, locktimer_cap, tasks_density_*, tasks_row_due (EN/RU). 863/863 ✅ (+8 test_design_v2_9b), ruff ✅, node --check ✅ | принято |
| ADR-077 | 2026-08-14 | Шаг 9a: редизайн «Тёмный архив» — фундамент (токены, шрифты) + app shell | 1) **Семантические токены DESIGN_V2 §4** в `base.html`: `--canvas/--surface/--border/--text/--accent` + доменные оттенки `--dom-*` (tracker/timer/care/health/insights/social/dynamics) и статусные `--success/warning/danger/info` для обеих тем; старые `--color-*` оставлены как алиасы (пре-в2 шаблоны продолжают работать). 2) **Self-hosted шрифты §5**: Inter Variable (был) + Source Serif 4 Variable (display serif, для названий сессий/дат/формул) + IBM Plex Mono (коды/длительности/аудит) — 21 файл, кириллица+латиница, unicode-range. 3) **App shell §7**: sidebar 72px collapsed / 272px expanded (явное раскрытие, localStorage persist), группы «Сейчас/Личное/Данные/Связи/Система» по feature flags, collapsed — иконки+tooltip; utility bar 64px (контекст-заголовок, locale/theme, уведомления, logout); mobile top bar 56px + полноэкранный sheet навигации (глобальный bottom nav удалён). Активный пункт — по `active_nav` или пути (request), заголовок вкладки — по маппингу. 4) **Dashboard §9 (9a-часть)**: шапка — дата в локали (`today_label`, ru/en) + ритуальная формула + статус; стат-карты/XP-бар на токенах. 5) Сигил `practiceloop-sigil.svg` → `/static/brand/`. 6) **Не в этом шаге**: 9b–9f (Timer/Tasks, Inventory/Media, остальные разделы, Social tone, discretion, visual QA) — расписаны в PLAN.md. 861/861 ✅ (+8 test_shell_v2), ruff ✅ | принято |
| ADR-076 | 2026-08-14 | Шаг 8: второй эшелон личного контура (device inventory, честный UI, TG-команды) | 1) **Device inventory для таймера**: `lock_sessions.device_id` FK → `inventory_items` (nullable, SET NULL, миграция 038). Устройство — любой инвентарный предмет владельца (не archived); выбирается при создании черновика и в настройках (`update-draft`), отображается чипом в шапке сессии и на овервью. Авто-статусы operational-измерения: старт → `in_use`, safety-stop → `available` (best-effort, не перезатирает ручные изменения). Устройство НЕ входит в canonical config (не влияет на расписание) — не замораживается в snapshot. 2) **Честный UI**: все оставшиеся emoji-иконки заменены на PracticeLoop icon pack (шаблоны + JS через plIcon DOM API); тест `test_icon_pack` теперь запрещает emoji-иконки в шаблонах и JS (исключение — content-значения в social/verification). 3) **Personal Telegram**: `/lock` (статус активной сессии — с/до/остаток/следующее окно/задачи), `/lock_start` (старт последнего черновика, inline-confirm), `/lock_stop` (safety-stop, inline-confirm), help обновлён. 847/847 ✅ (+22), ruff ✅ | принято |
| ADR-075 | 2026-08-14 | Шаг 7: LLM-верификация медиа (vision через Omniroute, ADR-070 Q13) | 1) **Vision в call_llm** (`app/llm/client.py`): поддержка image parts (data URL, лимит 4) — модель `openrouter/openai/gpt-4o-mini` подтверждена через Omniroute (дёшево). 2) **Движок** `app/llm/pipeline/media_verify.py`: два типа — `code_match` (LLM сравнивает код на фото с ожидаемым) и `chastity_closed` (оценка закрыт ли замок); verdict/confidence/reasoning; plaintext кода НЕ хранится (только HMAC-хэш в `media_verification_results`). Challenge-режим: LLM читает код с фото, **сервер сверяет HMAC** (сервер — авторитет, LLM — OCR-читатель); auto-consume challenge только по явному запросу владельца. 3) **API**: `POST /api/v2/media/{id}/verify` (JSON: verification_type/expected_code/auto_consume_challenge), `GET .../verification-results`, страница `/llm/verify` (выбор медиа, форма, история). Таблица `media_verification_results` + миграция 037. 825/825 ✅ (+25), ruff ✅ | принято |
| ADR-074 | 2026-08-14 | Шаг 6: LLM-инструменты личного контура (prompt library, templates, private KB) | 1) **Библиотека промптов** (`app/llm/prompt_library.py`): единый реестр 8 типовых системных промптов (task.single/weekly, training.plan/analyze/suggest, diet.generate/evaluate/synergy) — переиспользует существующие константы (единый источник), i18n-заголовки/описания EN/RU, страница `/llm/prompts` с «создать шаблон из этого». 2) **Промпт-шаблоны** (таблица `prompt_templates`, миграция 036): тип `text` (свободный ответ) и `task` (выбор задачи из opt-in набора, как generate_task с кастомным системным промптом); переменные `{{var}}` + `params_schema` в формате ADR-041 (валидация без eval через `app.params.validate_params`); CRUD-страницы `/llm/templates`, `/llm/templates/{id}`, JSON API `/api/v2/prompt-templates`; usage-трекинг (usage_count/last_used_at, токены/стоимость в provider config). 3) **Приватная база знаний — служебная** (решение владельца: пользователю НЕ доступна, без ручного ввода): `app/knowledge/` автоиндексирует существующие данные (ActivityLog, Diet, TrainingDay) в Qdrant (коллекция `personal_kb`, фильтр по user_id) через Omniroute-эмбеддинги (text-embedding-3-small); retrieval dense+lexical-fallback (никогда не ломает генерацию); интеграция в `build_context` (секция `kb_context` в промпт); read-only JSON API `/api/v2/knowledge/{status,search,reindex}`. Опциональные deps `memory` — без них KB деградирует. 800/800 ✅ (+24), ruff ✅ | принято |


### ADR-061 — Social S4+S6 (Verification + Tracker Adapter)
**Date:** 2026-08-12
**Decision:** Implement verification (S4) and Tracker adapter (S6) together as Path A.

**S4 — Verification:**
- Policies are frozen snapshots at request creation time
- Quorum: min_approvals → verified, max_rejections → review_required, deadline → no_quorum_action
- One vote per verifier per request (unique constraint)
- Owner cannot vote on own requests
- Comments on publications and verification requests, edit+delete support
- Encouragements are lightweight (no executable state change): thumbs_up, support, celebrate, motivate

**S6 — Tracker Adapter:**
- Single TrackerSocialAdapter covering tracker.activity_log and tracker.entity
- Authorize: checks ActivityLog.user_id or Entity.owner_id
- build_redacted_projection: strips raw_llm_response, penalty_details, user_id
- Capabilities: view_summary, view_details, verify (allowlisted per subject type)
- Timer adapter is a valid skeleton (all methods, returns empty/not_implemented)

**Rationale:** Verification without real domain data is a hollow shell; adapter without verification has no consumer. Together they form the minimum viable Social loop: share tracker data → verify results → comment.

### ADR-062 — Терминология: lock = chastity, таблицы не меняем, фронт честный (PD-017)
**Date:** 2026-08-12
**Decision:** «Lock» происходит от закрытия/замка — это и есть chastity. Таблицы, код и API остаются `lock_*`; переименование таблиц и миграции **не производятся** (миграции ради имени недопустимы). Честная терминология (device, wearer, lock-on, unlock window, keyholder) даётся во фронте, уведомлениях и внешних текстах; внутренние имена остаются нейтральными. Прямой Chastity Timer в UI, нейтральность только для discretion-уведомлений.
**Supersedes:** прежняя нейтральная семантика LockTimer UI (ADR-047…052 не меняются — они технические).
**Rationale:** честность предметной модели (PD-004) + отказ от дорогих миграций. Переименование 12+ таблиц lock_* дало бы риск регрессий без продуктовой ценности.
**Status:** ✅ Implemented в Session 81 — честные i18n EN/RU (Lock Timer / Unlock Windows / Seal #), кнопки Unlock/Lock, nav через t.nav_timer; таблицы и API не тронуты.

### ADR-063 — Мобильный клиент: кроссплатформенный, после портала (PD-018)
**Date:** 2026-08-12
**Decision:** После запуска базового портала разрабатывается мобильное приложение (Flutter или React Native, выбор — PQ-008). Это полноценный клиент Personal, не обёртка над web. Требования закладываются с этого момента: JSON API-first (PD-020), bearer-auth, push-уведомления (FCM/APNs) помимо Telegram.
**Rationale:** мобильный клиент — первый внешний потребитель внутреннего API; закладывать JSON-first сейчас дешевле, чем переписывать контракты потом.

### ADR-064 — Масштабирование: обязательство по трём осям (PD-019)
**Date:** 2026-08-12
**Decision:** Масштабирование = (1) много пользователей, (2) объём данных одного, (3) горизонтальная инфраструктура. Сейчас закладываются дешёвые решения: owner-scoped как контракт (уже соблюдается), storage-абстракция (uploads → S3-совместимый интерфейс), JSON-first. Rate limits, очередь, partition, реплика БД — по мере реальной потребности, без преждевременной постройки.
**Rationale:** избегаем over-engineering сейчас, но фиксируем направление, чтобы не перестраивать при открытии доступа.

### ADR-065 — JSON-first контракт для action-эндпоинтов (PD-020)
**Date:** 2026-08-12
**Decision:** Все новые и изменяемые action-эндпоинты возвращают JSON (JSONResponse), а не HTML/redirect. HTMX-фронт работает через те же JSON-контракты (fetch). HTML-рендер остаётся только для страниц. Пилот: timer start/safety-stop и ключевые действия перевести на JSON.
**Rationale:** фундамент для мобильного клиента (ADR-063) и масштабирования (ADR-064); единый контракт для всех клиентов.

### ADR-066 — Device-tz дневные бакеты графиков (PD-021)
**Date:** 2026-08-13
**Decision:** Дневные ряды графиков (activity/points-trend/xp-history/completion-rate) бакетируются в Python через `local_date(created_at)` (device-календарный день из ContextVar `client_tz`), а не SQL `func.date(created_at)` (UTC-день БД). Подписи оси — `local_today()`. `cutoff` остаётся UTC-инстантом.
**Rationale:** SQL `func.date()` группирует по UTC-дню, сдвигая бары на день относительно device-local подписей для пользователей вблизи UTC-полуночи. Python-бакетирование переносимо между Postgres и SQLite (SQLite не поддерживает `AT TIME ZONE`).
**Tradeoff:** загрузка сырых строк (≤90–365 дней) вместо агрегации в БД — приемлемо для одного пользователя; при росте объёма вернуться к dialect-specific `AT TIME ZONE`.
**Status:** ✅ Implemented в Session 96.

### ADR-067 — Фоновые задачи: границы суток через конфиг-tz, не request-tz
**Date:** 2026-08-13
**Decision:** Фоновые задачи без request-контекста (training auto-analysis scheduler) берут day-boundary «сегодня» из конфиг-настройки `tg_auto_analysis_tz` (IANA, по умолчанию "UTC") через `resolve_tz()`, а не из ContextVar `client_tz` и не из per-user `User.timezone`. Время срабатывания (`tg_auto_analysis_time`) интерпретируется в том же tz. TTL-пурдж raw-ответов остаётся сравнением UTC-инстантов (не граница суток).
**Rationale:** у фонового job нет request-контекста/cookie; единый глобальный tz дешевле per-user расписаний. Per-user `User.timezone` — возможное уточнение, если автоанализ станет per-user-расписанием.
**Status:** ✅ Implemented в Session 97.
### ADR-068 — Многоуровневая память проекта Memory v2
**Date:** 2026-08-13
**Decision:** Принята архитектура памяти Memory v2 (RFC в `docs/memory-rfc/`): L0 — короткий always-on контракт (AGENTS.md ≤5–8 KiB + knowledge.md ≤4 KiB); L1 — canonical semantic memory (`docs/wiki/`, `docs/adr/`, `docs/questions/` с provenance); L2 — generated facts текущего HEAD (`docs/state/FACTS.json` + `NOW.md`, никогда не вручную); L3 — гибридная память кода (exact/BM25 + AST/graph + локальные vectors, Qdrant local, shadow mode); L4 — эпизодическая память только локально (`.memory-local/`, `.agent-runtime/`). Внедрение по milestone M0–M6 (MEMORY_IMPLEMENTATION_PLAN.md); принят объём M0+M1 (schema/lint/facts + границы), остальное — отдельными milestones с gate-проверками и owner approval. Legacy `memory/*` не трогается и не замораживается до M5.
**Rationale:** `memory/` вырос до ~400 KiB (SESSIONS.md 159 KiB); чтение больших агрегатов в каждой сессии дорого, дублирует факты и смешивает роли (решение/факт/план/история). Целевые лимиты: always-on ≤10 KiB, context pack ≤12 KiB. Вектора не являются источником истины; authority определяется DOCUMENTATION_MAP.md и явным owner-решением.
**Tradeoff:** стоимость инструментов (memoryctl, benchmark) до появления измеримой экономии контекста; риск «wiki-свалки» — митигируется atomic pages + size lint + draft-only compiler.
**Status:** ✅ принято владельцем 2026-08-13 (Сессия 110); M0+M1 реализованы.

### ADR-069 — M3 пилот: Qdrant local + embedding через Omniroute (только vectors, shadow)

**Date:** 2026-08-13 (амended 2026-08-14, Сессия 118)
**Decision:** После baseline M3 (recall@5 = 0.26; доминирующий зазор — русский запрос → английский код, T3/T8/T10 ≈ 0) принят единственный пилот: Qdrant local mode + embedding через локальный LLM-прокси **Omniroute** (remote `/v1/embeddings`, модель `openrouter/openai/text-embedding-3-small`, 1536-dim, мультиязычная RU→EN). Режим shadow: векторные результаты пишутся в benchmark-отчёт, но не формируют обязательный impact без exact подтверждения (CODE_MEMORY_DESIGN.md §12). QMD (docs) и codebase-memory-mcp (graph) отложены. Code-specific второй named-вектор — только если text-embedding-3-small окажется слаб на коде.
**Amendment 118 (владелец):** исходно выбрана BGE-M3 (fastembed, local-only), но: (1) fastembed не поддерживает BGE-M3 нативно (qdrant/fastembed#348 — нужен патч); (2) это VPS с ограниченными ресурсами — fp32-модель ≥2.24 ГБ исчерпала 15 ГБ RAM на единственном batch-прогоне (OOM). Владелец указал Omniroute (llm.gorbunovr.ru, ~2800 моделей, 47 embedding) как источник эмбеддингов; параметры OMNIROUTE_HOST/OMNIROUTE_API_KEY в .env (позже используются порталом). Выбрана бесплатная/дешёвая модель: text-embedding-3-small ($0.02/1M токенов; индекс 2167 units ≈ $0.01). Qdrant остаётся локальным (лёгкое хранилище, не модель).
**Rationale:** Доминирующий провал baseline — кросс-языковой RU→EN, который решает только multilingual embedding; text-embedding-3-small — мультиязычная, дёшево, уже доступна через Omniroute без локальной модели. Этапность RFC §7/§12 — измерять инкрементально (off → shadow → assist → required).
**Tradeoff:** remote-эмбеддинги уходят в Omniroute (исходники code units отправляются на API прокси — не покидают хост, но уходят upstream-провайдеру маршрутизации); dev-зависимость только qdrant-client (fastembed/onnxruntime удалены, рантайм FastAPI не тронут). Первый запуск холодный (индексация 2167 units ≈ 4 мин, ~$0.01).
**Evidence (Сессия 118, A/B):** recall@5 0.24 → 0.37 (+0.13), MRR 0.356 → 0.496 (+0.14), pack ≤12 KiB, 0 forbidden; прирост именно на RU→EN задачах (T3/T4/T5/T8). Gate STAGE_PLAN: прирост recall@5/MRR подтверждён → пилот admit/shadow (assist-режим).
**Status:** ✅ принято владельцем 2026-08-13 (Сессия 116); аmended 2026-08-14 (Сессия 118).

### ADR-070 — Границы LLM для личного контура (расширение ADR-030/034)
**Date:** 2026-08-14
**Decision:** Личный контур — первая очередь разработки; все социальные/общедоступные функции — вторая очередь. В личном контуре LLM подключается полностью: **Omniroute — первый источник моделей** (подбор бесплатных/дешёвых моделей, harness, инструменты для личного контура). Границы расширены владельцем:

1. **Гибридная генерация сохраняется** (каталог + opt-in, LLM выбирает), но видимость названий регулируется **per-provider** через существующий `llm_mode`: `full` (полные названия активностей) или `abstract` (обезличенные). Это уточнение ADR-030, не отмена.
2. **Параметрическая генерация через промпт-шаблоны**: пользователь осознанно создаёт шаблон промпта (с параметрами/переменными), сохраняет его как переиспользуемый шаблон; LLM генерирует по шаблону. Требует: таблица промпт-шаблонов, UI создания/редактирования, подстановка параметров, validate против allowlist.
3. **LLM-верификация медиа — истина в последней инстанции** для соло-игр: подтверждение кодов и закрытия пояса верности через LLM-анализ загруженного фото (развитие Q13; OCR не обязателен — LLM понимает изображения). Хранить: медиа → verification → LLM-оценка (match/mismatch + reasoning) → статус.
4. **Приватная база знаний LLM** для обогащения промптов: на базе существующего векторного индекса (memoryctl Qdrant local + Omniroute-эмбеддинги) — выбранные документы/заметки пользователя инжектятся в контекст.
5. **Библиотека типовых промптов** по функциональным блокам (генерация задачи, анализ дня, диета, верификация) — типовые промпты для запросов по функционалу и доступным для обработки LLM блокам.

**Комплаенс-красная линия (не «консерватизм», а ToS + блокировка ключа):** генерация откровенного контента напрямую LLM или обход/маскирование фильтров провайдеров запрещены. Omniroute-модели (OpenRouter и др.) режут такой контент на upstream — обход = потеря ключа. Это ограничение не снимается.
**Rationale:** владелец считает текущие ограничения слишком консервативными для личного контура и готов расширить границы; приватность/локальность сохраняется (данные не покидают хост-прокси, кроме upstream-маршрутизации Omniroute).
**Status:** ✅ решено владельцем 2026-08-14 (Сессия 119); реализация — отдельными этапами (см. STAGE_PLAN, шаги 6–7).

### ADR-071 — M5: freeze legacy memory v1 (Memory v2 milestone)
**Date:** 2026-08-14
**Decision:** Legacy-память `memory/` (кроме `DECISIONS.md`) заморожена: `SESSIONS.md`, `STATUS.md`,
`CHANGELOG.md`, `OPEN_QUESTIONS.md`, `CONTEXT.md` получают frozen headers и больше не дописываются
(архив; история сессий — Git history). Активная память — Memory v2 (ADR-068): решения — в
`DECISIONS.md` (единственный активный legacy-реестр, компилируется в `docs/adr/`), новые знания —
`docs/wiki/`, открытые вопросы — `docs/questions/`, generated facts — `docs/state/` (FACTS.json + NOW.md).
Рабочий preflight — `memoryctl bootstrap`/`sentinel`/`impact`, launcher — `bin/practice-agent`.
CI: `memory-lint` job стал **required** (убраны `continue-on-error` и `|| echo` fallback для facts).
В `benchmark` добавлена метрика **impact-recall**: для задач с `impact_symbols` ground truth строится
механически (все scan-файлы с символом — consumers/tests/migrations), recall считается против retrieved
pack. Это метрика, с которой будущий code-graph пилот будет сравниваться (RFC §7/§12).
**Rationale:** период наблюдения Memory v2 (114–118, 5 сессий) пройден; параллельное ведение четырёх
копий одного события (SESSIONS/STATUS/CHANGELOG/NOW) дорого и дублирует факты; freeze снижает
startup-чтение до целевого ≤10 KiB.
**Status:** ✅ реализовано в Сессии 120 (758/758 ✅, lint 0/0, facts fresh).

### ADR-072 — Q14: penalty честно в HTTP + Omniroute в портал (Шаг 4)
**Date:** 2026-08-14
**Decision:**
1. **Штрафы LockTimer применяются фактически и возвращаются в HTTP (Q14).** Раньше UI писал
   «Skip this task? Penalty may apply.», но `apply_penalty` не вызывался из `skip_task`/`close_slot` —
   штраф не применялся. Теперь: `skip_task` применяет `rule.penalty_policy` (тип points/add_time,
   value N), `close_slot` при позднем закрытии (`now > close_due_at`) применяет `rule.late_close_policy`;
   идемпотентность — ключ `skip:{occurrence_id}` / `late_close:{occurrence_id}`; неизвестный тип
   политики логируется и пропускается (без краша и без неверного штрафа). API `POST .../skip` и
   `.../close` возвращают JSON (ADR-065) с блоком `penalty` (serialize_penalty_event); UI-кнопки
   переведены на fetch и показывают реальный результат («Штраф применён: -5 points») через
   data-атрибуты + 6 новых i18n-ключей EN/RU.
2. **Omniroute внедрён в портал (ADR-070).** `Settings` получил `omniroute_host`,
   `omniroute_api_key`, `omniroute_embedding_model` (те же переменные, что использует memoryctl).
   Seed-пресет Omniroute строится из settings (host нормализуется к `/v1`, API-ключ шифруется
   `encrypt_api_key`), активен по умолчанию. `.env.example` обновлён (портал + vector pilot).
**Rationale:** UI должен быть честным (Q14); переменные Omniroute лежали в .env без потребителя —
теперь пресет по умолчанию реально работает из .env, без ручного ввода.
**Status:** ✅ реализовано в Сессии 120 (767/767 ✅, ruff ✅).

### ADR-073 — Шаг 5: икон-пак PracticeLoop + Gate B (async media, transaction boundary, browser smoke)
**Date:** 2026-08-14
**Decision:**
1. **Икон-пак PracticeLoop интегрирован как единый источник иконок (ADR-070/шаг 5).**
   `design/icons` → runtime: `sprite.svg` и favicon в `app/static/`, макрос
   `app/templates/components/icon.html` (`icon(name, class_name, label)`), серверный allowlist
   имён. Все emoji/inline-SVG в UI заменены (base.html desktop+mobile nav, theme sun/moon,
   logout, flash; index, dashboard, training, import_data, llm_configs, admin, privacy,
   my_entities). JS: `window.plIcon` через DOM API (без innerHTML — §6.7), используется в
   diets.js/inventory.js. Обязательство в AGENTS.md/DESIGN.md: иконки только из пакета,
   нехватка — сообщать. Недостающие (thumbs-up/fire для social encourage — это значения
   контента, хранятся в БД) оставлены emoji и зафиксированы как долг.
2. **P2-2 — media без блокировки event loop.** `save_media` переносит Pillow-декод/миниатюру
   и запись на диск в thread pool (`asyncio.to_thread`); decompression bomb guard:
   `PILLOW_MAX_IMAGE_PIXELS=100MP` + эскалация warning→error, оба класса
   (DecompressionBombError/Warning) ловятся fail-closed.
3. **P1-5 — единый владелец транзакций.** `tests/test_transaction_boundary.py`: legacy
   allowlist (28 файлов, где commit остаётся осознанно), новые роутеры без `db.commit()`,
   locktimer/social — уже чистые (0 commit). `media.py` upload/finalize переведены на
   auto-commit `get_db()`; delete оставлен явным (файл удаляется только после фиксации БД).
4. **P1-4 — browser smoke.** Optional `e2e` dev-group (playwright), тест
   `tests/e2e/test_browser_smoke.py` (register → dashboard → tasks → timer → отсутствие
   console errors), CI job `e2e` (postgres + alembic + chromium). В default-окружении тест
   скипается (importorskip).
**Rationale:** личный контур — единственный приоритет; икон-пак покрывает и будущие модули
(Media Vault, Care, Health, Cycle, Insights, Chastity, D/s), заменяя emoji/Lucide; audit Gate B
(P1-4/P1-5/P2-2) закрывает блокеры перед следующим шагом.
**Status:** ✅ реализовано в Сессии 120 (776/776 ✅, ruff ✅, lint 0/0, facts fresh).

### ADR-074 — Шаг 6: LLM-инструменты личного контура (prompt library, templates, private KB)
**Date:** 2026-08-14
**Decision:**
1. **Библиотека промптов — единый реестр.** `app/llm/prompt_library.py` собирает 8 типовых
   системных промптов (task.single, task.weekly, training.plan_day/analyze_day/suggest_next,
   diet.generate/evaluate/synergy) из существующих констант (единый источник истины, без
   дублирования). Каждый — с i18n-заголовком/описанием (EN/RU) и метаданными. Страница
   `/llm/prompts` показывает промпты и позволяет создать приватный шаблон «из библиотеки».
2. **Промпт-шаблоны — параметрическая генерация (ADR-070).** Новая таблица `prompt_templates`
   (миграция 036): name, description, template_type (`text` | `task`), system_prompt с
   переменными `{{var}}`, params_schema (формат ADR-041, валидация через `app.params` — без
   eval), usage_count, last_used_at. Движок `app/llm/pipeline/templates.py`: `text` — свободный
   ответ по шаблону с подставленными переменными; `task` — как generate_task, но с кастомным
   системным промптом (allowed set + schema validation + ActivityLog + TaskBodyTarget и т.д.).
   UI: `/llm/templates` (список + create), `/llm/templates/{id}` (edit + generate + результат);
   JSON API `/api/v2/prompt-templates` (+ generate). Usage-метрики пишутся в provider config
   (ADR-034), шаблон — usage_count/last_used_at.
3. **Приватная база знаний — служебная система (решение владельца).** Пользователю НЕ
   доступна: без ручного ввода. `app/knowledge/` автоматически индексирует существующие
   данные пользователя (ActivityLog — название/params/actual/note, Diet — name/direction/goal,
   TrainingDay — plan_summary) в Qdrant (коллекция `personal_kb`, payload user_id — доступ
   только владельцу) через Omniroute-эмбеддинги (text-embedding-3-small, переиспользован
   подход memoryctl/vectors.py). Retrieval: dense + детерминированный lexical fallback (работает
   всегда, даже без backend'а — генерация не падает). Интеграция: `build_context` добавляет
   секцию `kb_context` (свои данные → релевантный контекст для LLM). Read-only JSON API
   `/api/v2/knowledge/{status,search,reindex}`. Зависимости — optional `memory` group; без них
   KB деградирует в пустой результат.
**Rationale:** ADR-070 (границы LLM) обещал эти инструменты; KB — служебная, потому что
«база не доступна пользователю» — это слой обогащения промптов своими данными, а не UI-модуль;
гибридная генерация сохранена (LLM по-прежнему выбирает из каталога, шаблоны — осознанный
пользовательский контроль промпта).
**Status:** ✅ реализовано в Сессии 120 (800/800 ✅, ruff ✅, lint 0/0).
### ADR-075 — Шаг 7: LLM-верификация медиа (vision через Omniroute)

**Контекст:** Q13 — верификация кодов и «закрыт ли замок» по фото без OCR. На VPS нет
ресурсов для локальных моделей — используем Omniroute (локальный LLM-прокси на том же
VPS, ~2000 моделей; embeddings уже используются KB). Доступные vision-модели проверены
реальным запросом: `openrouter/openai/gpt-4o-mini` работает (~$0.00015/1K prompt).

**Решение:**
1. **call_llm + vision** — image parts как data URL (лимит 4); фото читается только из
   приватного upload-хранилища владельца (path traversal защищён).
2. **Два типа проверки** в `media_verify.py`:
   - `code_match` с expected_code — LLM сравнивает код на фото с ожидаемым;
   - `code_match` с активным VerificationChallenge — LLM ЧИТАЕТ код с фото, сервер
     сверяет HMAC constant-time (сервер — авторитет; LLM — вспомогательный читатель);
   - `chastity_closed` — LLM оценивает, закрыт ли замок/устройство.
3. **Конфиденциальность:** plaintext кода нигде не хранится — только HMAC в
   `media_verification_results.expected_code_hmac`; в промпт ожидаемый код попадает
   только для сравнения (тот же запрос владельца).
4. **Auto-consume challenge** — только по явному флагу `auto_consume_challenge`
   (движок сам challenge не потребляет; API — по запросу).
5. **Таблица** `media_verification_results` (миграция 037): owner_id/media_id/
   verification_type/expected_code_hmac/verdict/confidence/reasoning/llm_model/
   consumed_challenge_id. Страница `/llm/verify` + JSON API.
6. **Не реализовано:** OCR как распознавание текста в общем виде — остаётся долгом (Q13).

**Status:** ✅ реализовано в Сессии 121 (825/825 ✅, ruff ✅).
### ADR-076 — Шаг 8: второй эшелон личного контура (device inventory, честный UI, TG-команды)

**Контекст:** после Шага 7 (LLM-верификация) — стабилизация личного контура: физическое
устройство сессии таймера, честный UI (икон-пак везде), личные Telegram-команды.

**Решение:**
1. **Device inventory** — `lock_sessions.device_id` → `inventory_items` (nullable, SET NULL,
   индекс). Устройство — любой предмет инвентаря владельца (не archived); выбор в
   `create_draft`/`update_draft` (валидация владения), в UI — селектор в настройках
   черновика + чип в шапке/овервью. Авто-статусы: `start_session` → `in_use`,
   `safety_stop` → `available` (best-effort через `services/device.py`). Устройство — метаданные,
   не часть canonical config (не влияет на расписание) — в snapshot не замораживается.
2. **Честный UI / икон-пак** — эмпирика FastAPI: пустое form-значение → default параметра,
   поэтому unbind идёт явным sentinel `__none__` из UI. Оставшиеся emoji-иконки во всех
   шаблонах и JS заменены на пакет (dashboard/achievements/diets/notifications/tasks/
   training/locktimer/login/social); тест запрещает emoji-иконки (content-значения
   social/verification — исключение).
3. **Personal Telegram** — `/lock` (статус), `/lock_start` (черновик → active, inline-confirm),
   `/lock_stop` (safety-stop, inline-confirm); гейт `settings.locktimer_core_enabled`.
4. **Не реализовано:** Mobile Foundation (M4) — запланировано следующим кандидатом.

**Status:** ✅ реализовано в Сессии 122 (847/847 ✅, ruff ✅).

### ADR-077 — Шаг 9a: редизайн «Тёмный архив» — фундамент (токены, шрифты) + app shell

**Контекст:** владелец утвердил `DESIGN_V2.md` («Тёмный архив») как целевой UI-контракт
и поставил Шаг 9 плана. Редизайн идёт по агентскому порядку §19: токены → шрифты → shell →
dashboard → Timer/Tasks → Inventory/Media → остальные разделы → Social tone → discretion → visual QA.

**Решение:**
1. **Токены** — палитра §4 (canvas `#171311`/`#e9e2da`, surface, border, text, accent `#a95f58`/`#8d4945`,
   доменные оттенки `--dom-*`, статусные `--success/warning/danger/info`) заданы в `base.html` для
   `data-theme="dark"/"light"`. Старые `--color-*` стали алиасами — пре-в2 шаблоны (slate/indigo классы)
   не ломаются, shell и новые экраны используют новые токены.
2. **Шрифты** — self-hosted: Source Serif 4 Variable (display serif, `pl-display`) и IBM Plex Mono
   (`pl-mono`), кириллица+латиница, без CDN. Inter Variable остался UI-sans.
3. **Shell §7** — sidebar 72/272px (collapsed по умолчанию, «раскрытие по явному действию»,
   localStorage `pl_sidebar`), группы навигации с feature flags, utility bar, mobile top bar + sheet
   (удалён глобальный bottom nav как противоречащий §7). Активный пункт — `active_nav` или путь
   запроса (base.html `nav_key`), заголовок контекста — маппинг ключей.
4. **Dashboard §9** — шапка: дата в локали (`_today_label`, ru/en массивы в dashboard.py) +
   ритуальная формула (`dashboard_ritual`), стат-карты/XP-бар переведены на токены; `⏳` → icon('clock').
5. **Не входит в 9a** (расписано в PLAN.md): 9b Active Timer+Tasks, 9c Inventory/Media, 9d остальные
   разделы, 9e Social tone + customization/discretion, 9f visual QA 4 вьюпорта + DoD §20.

**Status:** ✅ реализовано в Сессии 128 (861/861 ✅, ruff ✅, test_shell_v2 +8).

### ADR-078 — Шаг 9b: Active Timer + Tasks по DESIGN_V2 §8/§10

**Контекст:** после 9a (токены, шрифты, shell) редизайн по агентскому порядку §19 переходит
к ключевым экранам. DESIGN_V2 §10: Active Timer — «один крупный таймер, ниже события и сводная
статистика», safety stop «всегда видим и работает первым действием»; Tasks — строки со статусом,
названием, параметрами, due, причиной и действиями, два режима плотности, «карточная россыпь запрещена».

**Решение:**
1. **Active Timer hero** — на странице активной сессии: крупный serif-таймер (`pl-display`,
   tabular-nums, live-countdown сохранён через тот же `#countdown-display`); честная строка
   «режим · устройство · tz» (режим локализован: duration_from_start / infinite); диапазон
   `started → effective_end` + потолок `cap` (max_end_at при отличии от effective_end) + merge gap;
   safety stop — первый и самый крупный CTA (danger-токен), из шапки убран (остался extend-horizon).
2. **Токен-рестайл** session_detail + overview: gray/slate → `pl-surface` и токены, indigo-кнопки →
   accent, статус-чипы → семантические токены, timer-иконки → `--dom-timer`.
3. **Tasks** — переключатель плотности compact/comfortable (localStorage, класс `density-compact`
   на `#log-list`, JS в `tasks.js` — inline-скрипты запрещены audit'ом `test_no_inline_scripts_in_pages`);
   строки сохраняют статус/название/параметры/due/reason/действия; добавлена due-строка (scheduled_at).
4. i18n EN/RU: locktimer_mode_duration/infinite, locktimer_cap, tasks_density_label/compact/comfortable,
   tasks_row_due.

**Status:** ✅ реализовано в Сессии 129 (863/863 ✅, ruff ✅, node --check ✅).

### ADR-079 — Шаг 9c: Inventory/Media patterns (DESIGN_V2 §10/§11)

**Контекст:** §10 — «Изображение занимает минимум 160×120 px в списке и не требует открытия
для базовой оценки. Под ним или рядом: дата, тип, provenance, verified state, связанные объекты
и retention»; §11 — object-cover в обзорной ленте, placeholder — геометрическая метка, оригинал
не раскрывается через публичный URL.

**Решение:**
1. **Media Vault — новая страница `/media`** (`app/api/media_vault.py` + `app/templates/media_vault.html`):
   SSR-галерея. Плитка: изображение ≥160×120 (thumbnail `/api/v2/media/{id}/thumbnail` при наличии,
   иначе приватный стрим `/api/v2/media/{id}`), object-cover; подпись — дата (localtime), тип
   (owner_type), provenance (разрешается: inventory_item → name, activity_log → title/selected_entity_name,
   остальные → тип+id); verified-бейдж из `media_verification_results` (последний результат: verdict
   match/mismatch/unclear + тип проверки + confidence); retention — «Приватно · только вы» / «В архиве»;
   state-чип staged/ready/archived поверх изображения. Upload-форма (staged, owner_type=general —
   привязка из доменных страниц). Nav в sidebar: `/media` вместо JSON-эндпоинта `/api/v2/media`.
   **i18n-ключи страницы названы `mvt_*`** — коллизия: `mv_*` уже занят страницей `/llm/verify`
   (`mv_title` = «Media Verification»); дубликат был перезаписан — исправлено переименованием.
2. **Inventory** (`inventory.js` + `inventory.html`): изображение 160×120 (`w-40 aspect-[4/3]`
   object-cover) с placeholder-иконкой при отсутствии; бейджи категорий/статусов → токены
   (accent/info/success/warning/danger/surface-soft); оболочка страницы → pl-surface/токены.
3. **Тесты**: `test_design_v2_9c` — рендер галереи, upload→staged→показ, verified-бейдж,
   nav → /media, инвентарь, i18n EN/RU.

**Status:** ✅ реализовано в Сессии 130 (869/869 ✅, ruff ✅, node --check ✅).

### ADR-080 — Шаг 9d: токен-пасс Personal-разделов + a11y-контраст (WCAG AA)

**Контекст:** browser-набор (node playwright, установлен в параллельной сессии — решение
владельца: такие тесты не скипать) на живом проде нашёл реальные баги и контрастные
нарушения после Шага 9a: графики дашборда не рисовались («Chart is not defined» — пре-`extends`
скрипты), `--text-muted`/accent/индиго-ссылки не проходили 4.5:1 на тёмной поверхности,
селекты без aria-label (axe select-name, critical).

**Решение:**
1. **Токен-пасс 25 шаблонов** (points/catalog/calendar/import/training/diets/measurements/
   schedule/locations/llm/admin/sessions/notifications/achievements/privacy/auth + быстрые
   ссылки дашборда): legacy `bg-white/slate-*`, `text-slate-*`, `border/divide-slate-*`,
   индиго-кнопки → `pl-surface/-soft`, токены текста/границ, `pl-accent-bg`, `focus-ring →
   --focus`; осиротевшие `dark:*`-варианты после замен удалены. Намеренно оставлены: тёмный
   код-блок import_data, семантические цветные чипы/алерты (indigo/amber/emerald), градиенты.
2. **Контрастная политика (WCAG 2.2 AA, минимум 4.5:1 для обычного текста):**
   - новый токен `--accent-text` (#743a37 light / #c9897f dark) — accent для ЦВЕТА ТЕКСТА
     (сам `--accent` как текст: 3.63 dark / 4.48 light — не проходит); `.pl-accent-text` и
     `.pl-accent-soft` используют его;
   - тёмный `--accent` `#a95f58 → #a25a53` — кнопки accent-bg + on-accent: 4.40 → 4.76;
   - индиго-ссылки: `text-indigo-600 dark:text-indigo-400` (indigo-500/600 без dark-варианта
     проваливали тёмную тему);
   - форм-контролы: aria-label фильтр-селектам /tasks (tasks_filter_*) и desire_level
     /entities/catalog (catalog_desire_label, EN/RU).
3. **Баг графиков**: page-i18n + dashboard.js перенесены из пре-`{% extends %}` в
   `{% block head %}` (рендерились в начало документа ДО chart.umd.min.js).

**Status:** ✅ реализовано в Сессии 131. Browser desktop-chromium: 5/5 ✅ (smoke/a11y/usability×3)
+ 1 осознанный skip (prototype — нужен DESIGN_PROTOTYPE_URL); 113/113 таргетных pytest ✅;
задеплоено на прод. Долги a11y: light-theme контрасты (axe гоняется только в dark colorScheme),
прочие проекты матрицы (tablet/mobile/firefox/webkit) — на 9f visual QA.

### ADR-081 — Шаг 9e: Social tone + customization/discretion (DESIGN_V2 §13/§16)

**Контекст:** после 9a–9d (shell, токены, a11y) остались два блока DESIGN_V2: §13 (Social —
холодный сине-серый тон, отдельная группа sidebar, приватность через точные visibility-лейблы)
и §16 (пользовательская кастомизация: тема system, accent-наборы, плотность, блоки дашборда,
discretion с расписанием, blur чувствительных изображений). В коде не было никакого механизма
пользовательских настроек кроме theme/locale колонок.

**Решение:**
1. **Prefs-инфраструктура.** `users.prefs` JSONB (миграция 037; в модели generic `JSON` — иначе
   SQLite-тесты ломаются на postgresql.JSONB). `app/prefs.py`: `UserPrefs` dataclass,
   `sanitize_prefs` (валидация + дефолты, доводит недостающие dash_blocks), `raw_dict`
   (коэрция dict/строка/None), ContextVar. Инъекция — в `_load_prefs_context()` внутри
   `get_current_user`/`get_optional_user` (каждая авторизованная страница их вызывает) +
   контекст-процессор `_prefs_context` (templates_setup.py) → `prefs`/`discretion_active` во
   всех шаблонах. Первая реализация была middleware'ом — отклонена: middleware открывал свою
   сессию на общем SQLite-соединении тестов и при close() откатывал транзакцию тестовой
   сессии (юзер «терялся», 401). Auth-зависимости используют ту же сессию через DI — безопасно.
2. **Тема system.** Выбор dark/light/system; SSR рендерит резолв (system→dark fallback) в
   `data-theme`, сырой выбор — в `data-theme-choice`; app.js резолвит matchMedia и следит за
   изменениями ОС. `set_theme` принимает system и пишет выбор в users.theme + prefs.theme_choice.
3. **Accent-наборы.** ember/sage/slate через `html[data-accent]`; значения контраст-верифицированы
   скриптом (accent↔on-accent ≥4.5:1, accent-text↔surface ≥4.5:1): sage dark #5b7452/light #57734f,
   slate dark #56758a/light #4f6675; `--focus` синхронизирован.
4. **Страница /settings.** Appearance (тема, акцент, плотность), Dashboard (блоки: чекбоксы +
   стрелки + HTML5 drag&drop, hidden inputs block_order/block_hidden), Discretion (off/always/
   schedule с окном start/end, blur 0/1/2). `POST /settings` (санутизация на сервере) +
   `POST /settings/discretion/toggle` (JSON, quick-switch). Nav: Settings в System-группе (+
   автономная группа для timer/social-only вариантов, где System-группа не рендерится).
5. **Блоки дашборда.** dashboard_v2.html рендерит 8 блоков по `prefs.dash_visible` (порядок +
   скрытие), секции получили `id="dash-block-*"` (структурные якоря для тестов).
6. **Social tone §13.** Токен-пасс 7 social-шаблонов: bg-white→pl-surface, gray-*→токены,
   indigo-*→`--dom-social*`; добавлены `--dom-social-text` (контраст 6.21 light / 6.48 dark) и
   `--dom-social-btn` (5.76/5.10 — сам `--dom-social` как фон кнопки даёт 3.93 dark — не проходит
   AA). Sidebar-группа «Связи» уже была (9a).
7. **Discretion v1 §12.** Активен при mode=always или schedule-окне (время — локальное устройство
   через client_tz). Меняет: nav-лейблы (dscr_* EN/RU, макрос `dscr_label` в
   `components/labels.html`; импорт макроса требует `with context` — иначе контекст недоступен и
   лейблы не нейтрализуются — поймано тестом), заголовки дашборда, имена задач/диет/планов
   (Item #N), favicon (favicon-neutral.svg), blur изображений (media vault SSR + inventory JS
   через `data-blur` + `window.__dscrBlurCls`). Quick-toggle применяет состояние мгновенно
   (favicon, html[data-discretion], nav-лейблы из data-dscr/data-label), сервер — источник
   истины для следующего SSR. Режим не трогает данные/правила/safety (соответствует §12).
   Долг: тексты уведомлений не нейтрализованы (v1) — закрыт в Сессии 134: `neutral_notification()`
   в app/prefs.py + маскировка всех 7 in-app-уведомлений (level_up/achievement/streak/3×threshold/
   penalty) в gamification/handler.py на этапе создания (Telegram автоматически получает тот же
   нейтральный текст), i18n dscr_notif_title/body EN/RU, +7 тестов test_discretion_notifications.

**Status:** ✅ реализовано в Сессии 132; долг уведомлений закрыт в Сессии 134. 141/141 таргетных
pytest ✅ (+11 test_design_v2_9e: settings render/persist/sanitize, blocks order/hidden,
discretion always+schedule+toggle, accent+system, media blur, social tone без legacy-классов),
+7 test_discretion_notifications (37/37 ✅), ruff ✅, node --check ✅, i18n EN/RU паритет 878/878.

### ADR-082 — Шаг 9f: Visual QA, light-тема контрасты и browser-матрица (DESIGN_V2 §20)

**Контекст.** 9f требовал visual QA на 4 вьюпортах + DoD §20 («dark/light одинаково приглушены»,
«contrast проверки пройдены»). Первый честный light-прогон axe (реальное переключение темы,
а не эмуляция colorScheme) вскрыл системный долг: 9d токен-пасс затронул только пары
slate/gray/indigo, но цветные status-чипы/быстрые ссылки/декоративные цифры оставались на
raw Tailwind -400/-500/-600 — они проходят тёмную тему и падают светлую.

**Решения.**
1. **Светлая тема = первый класс.** `--text-muted` light #75675c → #6b5e53 (4.88 canvas /
   5.34 surface / 4.58 soft, иерархия светлее secondary сохранена). Цветные тексты переводятся
   на паттерн `-700 dark:-400` (emerald/red/amber/purple -400/-500/-600 → -700 в light, -400 в dark);
   белый текст на `bg-emerald/green-500/600` → фон -700 (white-on-700 ≥4.5). Проверено скриптом
   контраста до правки.
2. **Клиентские JS-шаблоны входят в токен-пасс.** points/dashboard/calendar/diets/measurements/
   locations/body_parts JS инжектят text-slate/gray-400/500 — заменены на `text-[color:var(--text-muted|secondary)]`.
   Это закрыло дыру: 9d гонялся только по HTML-шаблонам, а axe видел и JS-инжект.
3. **Axe-маршруты расширены** до 8 (dashboard/tasks/catalog/locktimer/settings/achievements/media/
   points) × dark/light — покрытие DoD «contrast проверки пройдены».
4. **WebKit Secure-cookie.** CSRF-кука теперь loopback-aware (`secure=production and not loopback`),
   как access_token — иначе WebKit дропает её на http://127.0.0.1 и POST получает 403.
5. **Firefox font-download flake.** `workers: 2` в playwright.config — 6 параллельных браузеров
   истощали app-контейнер на маленьком VPS, Firefox не успевал скачать woff2 (status=2152398850).
   MIME (font/woff2) уже был корректен; это ресурсный флейк, не баг кода.

**Status:** ✅ реализовано в Сессии 133. Browser-матрица 36 passed / 6 skip (prototype — осознанный) /
0 fail; задеплоено; 233 browser-тест-юзера вычищены. ruff ✅, node --check ✅, i18n 876/876,
45/45 таргетных pytest (design 9b/9c/9e + icon + shell).

### ADR-083 — Шаг 10: Mobile Foundation (M4) — bearer-auth + JSON-first + push-устройства

**Контекст.** ROADMAP M4 (ADR-063/064/065) требует технический фундамент для будущего
мобильного клиента: JSON-first action-контракты, bearer-auth (access+refresh) рядом с
cookie-сессией, push-канал (FCM/APNs) помимо Telegram, медиа URL-контракт. Владелец выбрал
полный объём 5A: bearer + push-устройства + конвертация action-эндпоинтов (dual-mode по
bearer) + ротация/отзыв refresh-токенов.

**Решения.**
1. **Bearer-auth.** JSON-эндпоинты `/api/v2/auth/{token,refresh,revoke,tokens,tokens/{id}/revoke,me}`.
   Access — JWT с claim `type=access`; legacy токены без claim считаются access (обратная
   совместимость с cookie-сессиями), `decode_access_token` отвергает JWT с иным type. Refresh —
   непрозрачный `secrets.token_urlsafe(48)`, в БД только SHA-256-хэш (`api_tokens`), ротация при
   каждом `/refresh` (старый revoke + новый с `rotated_from_id`), revocable по значению и по id,
   sliding `refresh_token_expire_days` (30). CSRF для bearer-запросов не нужен (нет cookie-сессии).
2. **JSON-first dual-mode (ADR-065).** `app/api/responses.action_response(request, json_body, redirect_url)`:
   при `Authorization: Bearer` → JSON, иначе redirect (HTMX-фронт не переписывается). Конвертированы
   locktimer action-эндпоинты (start/safety-stop/open/reveal/complete/правила/шаблоны); skip/close/validate
   уже были JSON. `POST /api/v2/tasks/{id}/transition` уже JSON (ADR-040).
3. **Push-устройства.** Таблица `push_devices` (unique user+platform+token, is_active) + JSON API
   `/api/v2/push/devices` (register upsert/list/deactivate/delete, cross-user изоляция). Пакет `app/push`:
   `PushSender` protocol + registry + `dispatch_push` (best-effort, никогда не роняет доменную операцию),
   `PUSH_PROVIDER=none|logging|fcm|apns` (default none — disabled; fcm/apns регистрируются когда появятся
   креды). Hook `_send_push_notifications` в `gamification/handler.py` рядом с Telegram.
4. **Медиа URL-контракт.** `GET /api/v2/media/{id}` / `/thumbnail` и list работают по bearer
   (уже через `get_current_user`); добавлено тест-покрытие.

**Status:** ✅ реализовано (Шаг 10). Миграция 040 (`api_tokens`, `push_devices`), single head ✅.
14/14 test_mobile_foundation ✅, 177/177 регрессионных (auth/locktimer/gamification/transaction) ✅,
ruff ✅.

**Rationale:** мобильный клиент — первый внешний потребитель внутреннего API; bearer + refresh +
rotation + revocation — стандарт безопасности для токенов; dual-mode по bearer сохраняет HTMX-фронт
без переписывания; push-абстракция без реальных кредов дёшева сейчас и дорога в перестройке потом.

### ADR-084 — Шаг 11: M3 Personal Suite — архитектура + Medication Organizer

**Контекст.** ROADMAP §5 требует `TARGET_ARCHITECTURE.md` до Personal Foundation и
`DATA_LIFECYCLE.md` (закрывает PQ-006) до Media Vault/Health. Шаг 11 (M3 Personal Suite) охватывает
журналы, Care и Health foundation. Владелец выбрал «оба документа сначала» (11a) + первый модуль —
Medication Organizer (11b).

**Решения.**
1. **11a — архитектура.** `TARGET_ARCHITECTURE.md` (bounded contexts: Platform/Tracker/Chastity
   Timer/Journals/Care/Health/Media Vault/Insights/Social/D/s; межмодульные контракты только через
   ID+проекция+adapter; события/outbox/adapters; транспорты; мобильный API-контракт
   `api/v2`+bearer+dual-mode; feature flags и rollout/не-регрессия). `DATA_LIFECYCLE.md`
   (классификация 4 слоёв PD-012, retention, export/delete, derivatives/Shared Artifact, Health
   relief-only) — закрывает PQ-006. `DOCUMENTATION_MAP.md` §2/§7 и `PRODUCT_DECISIONS.md`
   (PQ-002 первый модуль, PQ-006 закрыт) синхронизированы.
2. **11b — Medication Organizer (relief-only, PD-013).** 5 таблиц + миграция 041 (single head):
   `medications` (name/kind/active_ingredient/form/strength/unit/instructions), `med_kits` (аптечки),
   `med_stocks` (quantity+expiry_date+lot+low_stock_threshold), `med_schedules` (доза + frequency
   daily/interval/weekly), `med_intakes` (taken/missed/skipped/rescheduled/unknown). Без игровой
   интеграции (gamification/xp/penalty не импортируются). Feature flag `medication_enabled` (default true).
3. **Страница `/medications`**: «на сегодня» (due по локальному дню устройства через
   `timeutils.local_date`), истекающие (30 дней) / низкий остаток, каталог + аптечки + инлайн-CRUD.
4. **JSON API** `/api/v2/medications` (bearer): list, `/today`, `POST /{id}/intake`, `/export`.
5. **Экспорт**: `GET /medications/export` — CSV (список + история приёма) для врача (Shared Artifact).

**Status:** ✅ реализовано (Шаг 11a+11b). 10/10 test_medication ✅, 45/45 регрессионных
(shell/icon/mobile/design-9e) ✅, ruff ✅, i18n 935/935, alembic single head ✅.

**Rationale:** Health — строго Private Record и relief-only (никогда не в штрафах); архитектурные
доки фиксируют границы до роста модулей; Medication Organizer — самодостаточный первый Health-срез
с явным экспортом врачу и без игровой интеграции.

### ADR-085 — Шаг 12: Медицина × игра — смягчение PD-013 (adherence), relief-задачи, миграция инвентаря
**Date:** 2026-08-17
**Decision:** **PD-013 смягчён владельцем** — пункт «Медицинские записи не дают и не отнимают баллы» заменяется: *своевременный приём (adherence) может давать XP и достижения (позитивное подкрепление, cap в день)*; **пропуск/мисс никогда не отнимает баллы и не наказывается** (негативная геймификация здоровья запрещена). Медицинский сигнал остаётся relief-only: может только открыть окно, смягчить, поставить на паузу или завершить активность.

**Что входит (Шаг 12):**
1. **Adherence-XP + достижения.** Новый модуль `app/gamification/medication.py`: `on_medication_taken(db, user_id, medication_name, on_time)` — начисляет XP (фикс, cap/день), считает adherence-streak (подряд идущие дни, где все дозы приняты) и выдаёт достижения `med_first` (первый приём), `med_adherence_3/7/30` (серии 3/7/30 дней). Достижения добавим в SEED_ACHIEVEMENTS + миграция 042 (idempotent insert — для существующих БД).
2. **Хук в оба intake-эндпоинта** (form `/med-intakes` + JSON `/api/v2/medications/{id}/intake`): при status=taken и on_time → `on_medication_taken`. Пропуск (missed) — только запись, без штрафа.
3. **LockTimer relief-задачи.** Med schedule → task rule сессии с `penalty_policy` выключенным (`{"enabled": false}`): `POST /api/v2/locktimer/sessions/{id}/medication-task-rules` (+ кнопка в session detail). Задача появляется в списке задач сессии, но её пропуск не штрафуется.
4. **«Сегодня» трекера (view-level).** Due-приёмы видны в дашборд-блоке medications (без создания ActivityLog — не загрязняем историю задач).
5. **Одноразовая миграция инвентарь→медицина.** `POST /api/v2/medications/migrate-from-inventory` (JSON: item_ids) + UI на `/medications`: предметы инвентаря из мед-категорий (hygiene_supply, consumable, recovery_item, measurement_tool) → Medication (kind=supply/device) + MedStock, удаление из инвентаря.

**Supersedes:** пункт PD-013 «не дают и не отнимают баллы» (частично — только позитивное подкрепление adherence; негатив остаётся запрещён).
**Rationale:** владелец решил вписать медицину в игровой контент позитивно (вознаграждение за своевременный приём), сохранив защиту здоровья от наказаний (miss никогда не штрафуется, relief-only для сигналов).
**Status:** ✅ реализовано (Шаг 12).

### ADR-086 — Шаг 13: Health + Cycle foundation (ROADMAP §7 4D)
**Date:** 2026-08-17
**Decision:** Второй Health-срез личного контура — **relief-only (PD-013)**: никакой игровой интеграции, никаких штрафов; все записи Private Record (DATA_LIFECYCLE.md); расчётная фаза Cycle никогда не выдаётся за достоверный факт (PRODUCT_OVERVIEW §9.4).

**Что входит (Шаг 13):**
1. **Модель 4 таблицы** (миграция 044, single head): `health_states` (ежедневный check-in: event_date, mood/energy/sleep_quality/recovery 1–5, sleep_hours, symptoms JSON, notes), `lab_records` (анализы: name, measured_at, value, unit, ref_min/ref_max — оригинальный диапазон лаборатории, lab_name, flagged, notes), `cycle_settings` (одна строка на пользователя: cycle_length, period_length, contraception), `cycle_events` (факты цикла: event_date, event_type — bleeding/symptom/state/sleep/energy/libido/skin/test/note, value, notes).
2. **Страница `/health`**: check-in на сегодня (upsert по дате), история, анализы с подсветкой вне-диапазона (`out_of_range`), Cycle: настройки + события + расчётная фаза.
3. **Расчёт фазы**: `_day_of_cycle` — день цикла от последнего начала кровотечения (новый цикл после перерыва ≥3 дней между bleeding-событиями), `_cycle_phase` — menstrual/follicular/ovulation/luteal по дню; всегда `phase_estimated=True`.
4. **JSON API** `/api/v2/health` (bearer): сводка `/`, `/states`, `/labs`, `/cycle`, `POST /state` (upsert), `POST /labs`, `POST /cycle/events`.
5. **Дашборд-блок** `dash-block-health` (check-in сегодня / число анализов / фаза цикла), управляется в /settings (DASH_BLOCKS), discretion-aware через dscr_health.
6. nav-пункт «Здоровье» (иконка health.svg из пакета), feature flag `health_enabled` (default true).

**Отложено:** ограниченный LLM-разбор анализов (§9.3 — пересказ/вопросы врачу) — будущий срез (см. PLAN.md).
**Rationale:** закрывает ROADMAP §7 4D (состояния/сон/восстановление, анализы с оригинальным диапазоном, Cycle с фактическими и расчётными фазами) по паттерну Medication (11b), relief-only.
**Status:** ✅ реализовано (Шаг 13). 20/20 таргетных + 55/55 регрессионных ✅, ruff ✅, i18n 1009/1009, single head ✅. Прод не тронут.

### ADR-087 — LLM-режим пользователя (safe/expanded) на всех LLM-блоках + разбор анализов
**Date:** 2026-08-17
**Decision:** Введена настройка профиля **`prefs.llm_mode`** (`safe` — default | `expanded`), управляемая в /settings (секция «LLM mode»). Режим определяет, насколько свободно ассистент интерпретирует данные пользователя.

**Распространение на все LLM-блоки (Session 137):**
- `app/llm/mode.py` — единый `llm_mode_hint()`: safe — «только факты, без непрошенных советов»; expanded — «разрешены практические рекомендации/советы». Hint аппендится к системным промптам **всех** блоков: задачи (`generate_task`, `generate_weekly_tasks`), тренировки (`generate_daily_plan`, `analyze_training_day` — оба LLM-вызова), диеты (`generate_diet`, `evaluate_diet`, `analyze_diet_training_synergy`), промпт-шаблоны (`generate_from_template` — text и task).
- Все pipeline-функции получили параметр `llm_mode: str | None = None` (None → из `get_prefs()` ContextVar, заполняется auth-зависимостью).
- **Telegram `/next`** и **фоновый scheduler авто-анализа** (нет request-контекста) передают режим явно из `user.prefs`.
- **Дисклеймер «не врач» убран из всех промптов** (в т.ч. из expanded health) — по решению владельца «LLM не даём инструкции что он не врач»; дисклеймер живёт только в UI (`health_analysis_disclaimer`). В промптах остаётся «не выдумывай медицинские утверждения» (требование достоверности, не дисклеймер).

**LLM-разбор анализов (первый специализированный потребитель):**
- `app/llm/health_prompts.py` — два системных промпта (safe/expanded), JSON-схема: summary/observations/assumptions/questions_for_doctor/(recommendations).
- `app/llm/pipeline/health.py` — `analyze_labs()`: собирает анализы за 180 дней + активные расписания приёма, вызывает call_llm (json_mode), парсит/санитизирует, трекает usage на активном LLMProviderConfig. Не сохраняется в БД (stateless, on-demand).
- Эндпоинты: `POST /health/analyze` (form → redirect с JSON в query) и `POST /api/v2/health/analyze` (JSON, bearer). Без активного LLM-конфига — понятная ошибка.

**Комплаенс-граница (важно):** «небезопасный режим» здесь НЕ означает обход safety-фильтров провайдеров и НЕ маскирование контента (запрещено AGENTS.md/ToS). Оба режима — обычное поведение ассистента; `expanded` лишь расширяет инструктивную рамку (разрешены рекомендации). Это сохраняется и для будущих «геймплейных» влияний.

**Supersedes:** нет (новое). Расширяет ADR-070 (границы LLM личного контура).
**Status:** ✅ реализовано (Шаг 13-LLM + распространение). 10 новых тестов + 30/30 health + 127/127 регрессионных (training/prompt_templates/tasks/diets) ✅, ruff ✅, i18n 1022/1022. Прод не тронут.

### ADR-088 — Sexual Journal (ROADMAP §7 4A)
**Date:** 2026-08-17
**Decision:** Реализован первый срез **Sexual Journal** — приватная запись фактической сексуальной жизни (PRODUCT_OVERVIEW §7), relief-only (PD-013): никакой игровой интеграции, никаких штрафов; все записи — Private Record (DATA_LIFECYCLE.md).

**Модель (2 таблицы, миграция 045, single head):**
- `sj_partners` — локальные псевдонимы партнёров (user-scoped, `name`/`notes`; никогда не раскрываются наружу).
- `sj_entries` — записи журнала: `entry_date`, `partner_id` (FK SET NULL), `activity_type`, `duration_minutes`, `desire_before`/`arousal_before` (1–5), `protection` (none/condom/birth_control/withdrawal/other), `orgasms`, `intensity`/`satisfaction`/`pleasure` (1–5), `reactions` (JSON), `emotional_state` (JSON), `aftercare`, `recovery` (1–5), `notes`, плюс мягкие ссылки `timer_session_id`/`health_state_id` (UUID без FK) и снимок `cycle_phase`/`cycle_day`.

**Связи (PRODUCT_OVERVIEW §16, DATA_LIFECYCLE.md):**
- **Sexual Journal ↔ Cycle**: при создании записи вычисляется и сохраняется снимок расчётной фазы цикла (`_cycle_snapshot` из health-хелперов) — помечен как оценка, не факт (§9.4). Если Cycle недоступен — (None, None).
- **Timer/Health**: связи по ID без раскрытия — мягкие UUID-колонки без FK; отдельное удаление; общая проекция не открывает журналы друг друга (§7).

**API:** страница `/journal` (форма записи + история + псевдонимы), CRUD-формы (create/delete), JSON `/api/v2/journal` (bearer: сводка + записи + партнёры, POST entries/partners). Object-level auth: чужой partner_id отклоняется; удаление псевдонима обнуляет ссылки в записях (SET NULL на уровне приложения).

**Дашборд-блок** `dash-block-journal` (записи за 30д / последняя запись / ср. удовлетворённость), настраиваемый в /settings; nav-пункт «Журнал» (иконка `aftercare.svg` из пакета), feature flag `journal_enabled` (default true).

**Supersedes:** нет (новое). Следует паттерну Medication (11b) / Health (13) — вертикальный срез личного контура.
**Status:** ✅ реализовано (Шаг 14). 15/15 таргетных + 99/99 регрессионных (health/medication/shell/design/icon) ✅, ruff ✅, i18n 1072/1072, single head ✅. Прод не тронут.

### ADR-089 — Sexual Journal: медиа + связки с Tracker/Timer (Шаг 14b)
**Date:** 2026-08-17
**Decision:** По решению владельца «медиа в журнале + связка активностей с журналом + авто-запись при открытии окна таймера для плановой активности».

**(1) Медиа в журнале:** `owner_type=journal_entry` добавлен в media registry + ALLOWED_OWNER_TYPES; `POST /journal/entries/{id}/media` (save_media → MediaAsset, owner-scoped, чужой entry → 404); фото-плитки в истории записей (160×120, thumbnail).

**(2) Связка с Tracker-активностями:** `sj_entries.activity_log_id` (мягкая ссылка по ID без FK, DATA_LIFECYCLE.md); валидация владельца — чужой task → 400; селект недавних задач в форме; при привязке `source=activity`; отображение названия задачи в записи.

**(3) Timer-автозапись (окно для плановой активности):** `lock_slot_rules.journal_auto` (миграция 046, single head):
- при **открытии** окна авто-создаётся **draft**-запись журнала (`source=timer_slot`, `status=draft`, `slot_occurrence_id`, `timer_session_id`) — `ensure_timer_slot_entry` в open-флоу, **idempotent**; журнал недоступен — действие таймера не прерывается (try/except, logger.warning);
- при **закрытии** окна API возвращает `journal_pending` (entry_id + url) через `get_pending_slot_entry`; CTA «Заполнить детали журнала» в session_detail;
- на /journal секция «Требуются детали» (warning-стиль) с формой `POST /journal/entries/{id}/complete` — детали **обязательны** при закрытии; JSON-версия `POST /api/v2/journal/entries/{id}/complete`.

**Relief-only сохранён (PD-013):** журнал без игровой интеграции; авто-запись — приватный факт, не геймплей.
**Supersedes:** нет (новое). Расширяет ADR-088.
**Status:** ✅ реализовано (Шаг 14b). 11/11 новых тестов (медиа/activity-link/timer-auto/close-complete/JSON) + 197 регрессионных ✅, ruff ✅, i18n 1082/1082, single head ✅. Прод не тронут.

### ADR-090 — Personal Care (ROADMAP §7 4B, Шаг 15)
**Date:** 2026-08-17
**Decision:** Реализован третий срез ухода личного контура — **Personal Care** (PRODUCT_OVERVIEW §8): уход, косметика, гигиена, процедуры и внешность. **Relief-only (PD-013)**: никакой игровой интеграции, никаких штрафов; все записи Private Record (DATA_LIFECYCLE.md).

**Модель (2 таблицы, миграция 047, single head):**
- `care_routines` — каталог процедур/рутин: `name`, `area` (face/body/hair/hands/feet/other), `kind` (home/salon), `frequency_days` (частота в днях, необязательно), `notes`;
- `care_entries` — факты выполнения: `routine_id` (FK SET NULL), `entry_date`, `duration_minutes`, `skin_reaction` (1–5), `notes`, `cycle_phase`/`cycle_day` (снимок расчётной фазы Cycle, не факт — §9.4).

**Связи (PRODUCT_OVERVIEW §8/§9.4):**
- **Personal Care ↔ Cycle**: при создании записи вычисляется и сохраняется снимок расчётной фазы (`_cycle_snapshot` из health-хелперов) — помечен как оценка, не факт. Если Cycle недоступен — (None, None).
- **Медиа**: `owner_type=care_entry` добавлен в media registry + ALLOWED_OWNER_TYPES; `POST /care/entries/{id}/media` (save_media → MediaAsset, owner-scoped, чужой entry → 404); фото-плитки (160×120, thumbnail) в истории — фото динамики.

**API:** страница `/care` (форма процедуры + журнал ухода + каталог рутин + история), CRUD-формы (routine/entry create+delete), JSON `/api/v2/care` (bearer: сводка + процедуры + записи, POST routines/entries). Object-level auth: чужой routine_id отклоняется (400); удаление процедуры обнуляет ссылки в записях (SET NULL на уровне приложения).

**Дашборд-блок** `dash-block-care` (процедуры за 30д / последняя / число рутин), настраиваемый в /settings (DASH_BLOCKS); nav-пункт «Уход» (иконка `routine.svg` из пакета), feature flag `care_enabled` (default true).

**Supersedes:** нет (новое). Следует паттерну Medication (11b) / Health (13) / Journal (14) — вертикальный срез личного контура.
**Status:** ✅ реализовано (Шаг 15). 17/17 таргетных + 126 регрессионных (journal/health/medication/shell/design/icon/media) ✅, ruff ✅, i18n 1105/1105, single head ✅. Прод не тронут.

### ADR-091 — Универсальный каталог активностей (сквозной, Шаг 16)
**Date:** 2026-08-17
**Decision:** По решению владельца «каталог сквозной, должен иметь возможность применяться в любых активностях». Ранее виды активностей были разрознены: Entity-каталог трекера (с параметрами/геймификацией/опт-ином), собственный `care_routines`, у журнала `activity_type` — свободная строка. Теперь — единый универсальный каталог по образцу Entity.

**Модель (1 таблица, миграция 048, single head):**
- `activity_catalog` — `name`, `description`, `category_id` (FK `activity_categories`, SET NULL), `tags` (JSON), `domains` (JSON-список контекстов: journal/care/timer/tracker; пусто/None = «сквозная», применима везде), `owner_id` (NULL = системная запись, видна всем; иначе — пользовательская, только владельцу), `is_public`, `created_at`/`updated_at`.

**Замена свободных полей на FK-ссылку (все SET NULL):**
- `sj_entries.catalog_item_id` — вид активности в Sexual Journal (форма/complete/JSON);
- `care_routines.catalog_item_id` — вид процедуры ухода (форма/JSON);
- `lock_slot_rules.catalog_item_id` — причина/цель окна таймера (форма слота session_detail);
- `entities.catalog_item_id` — трекер-задача ссылается на универсальный вид (форма my_entities).
Свободный ввод остаётся только через создание своей записи каталога (пользовательская, видна только владельцу).

**API:** страница `/catalog` (просмотр/создание/удаление, фильтр по domain, системные + личные), JSON `/api/v2/catalog` (bearer), хелпер `catalog_options(domain)` для пикеров (системные + свои, фильтр по domain). Object-level auth: чужая запись недоступна.

**Каталог нейтрален (relief-only, PD-013):** это справочник без игровой интеграции (XP/баллы/штрафы); игровые параметры остаются в Entity-каталоге трекера.

**Supersedes:** нет (новое). Унифицирует разрозненные «каталоги» видов активностей.
**Status:** ✅ реализовано (Шаг 16). 18/18 таргетных + 154 регрессионных (journal/care/locktimer/entities/dashboard/design/icon) ✅, ruff ✅, i18n 1120/1120, single head ✅. Прод не тронут.

### ADR-092 — Care Products: средства/косметика с привязкой к инвентарю (Шаг 16b)
**Date:** 2026-08-17
**Decision:** По решению владельца «добавить каталог средств/косметики для ухода с привязкой к инвентарю». Расширяет Personal Care (ADR-090): помимо процедур/рутин — каталог конкретных средств, которые использует пользователь.

**Модель (2 таблицы, миграция 049, single head):**
- `care_products` — позиция средства: `name`, `category` (cleanser/toner/serum/moisturizer/mask/exfoliant/sun/body/hair/other), `brand`, `notes`, **`inventory_item_id`** (FK `inventory_items`, SET NULL — остаток/список покупок ведётся в инвентаре), `created_at`/`updated_at`;
- `care_entry_products` — many-to-many `care_entries` ↔ `care_products` (оба FK CASCADE): какие средства использованы в записи ухода.

**Связи:**
- **Care Product ↔ Inventory**: `inventory_item_id` FK SET NULL; валидация владельца — чужой предмет → 400; пикер инвентаря — активные позиции без мигрированных в лекарства.
- **Entry ↔ Products**: мультиселект в форме записи ухода; замена набора join-строк на уровне приложения (`_set_entry_products`, delete+insert); удаление продукта чистит join-строки приложения + CASCADE в БД.

**API:** страница `/care` — секция «Средства и косметика» (форма: название/категория/бренд/связанный предмет инвентаря; список с инвентарным бейджем и счётчиком использований). JSON `/api/v2/care`: `POST /products` (201), `DELETE /products/{id}` (204), `product_ids` в записях и сводке.

**Relief-only (PD-013):** справочник без игровой интеграции (XP/баллы/штрафы).

**Supersedes:** нет (новое). Расширяет ADR-090 (Personal Care).
**Status:** ✅ реализовано (Шаг 16b). 13/13 таргетных + 151 регрессионный (care/journal/catalog/health/medication/shell/design/icon/mobile) ✅, ruff ✅, i18n 1166/1166, single head ✅. Прод не тронут.

### ADR-093 — Personal Insights (ROADMAP §7 4E, Шаг 17)
**Date:** 2026-08-17
**Decision:** По решению владельца «сделать следующий модуль личного контура: 4E Personal Insights». **Personal Insights** — явно запрошенный кросс-модульный LLM-анализ личных данных (PRODUCT_OVERVIEW §12 / TARGET_ARCHITECTURE §3.10): тенденции и связи между активностями (Tracker), Chastity Timer, сексуальной жизнью (Journal), состоянием (Health), уходом (Care), тренировками и диетами.

**Модель (2 таблицы, миграция 050, single head):**
- `insight_runs` — запуск анализа: `period_start`/`period_end`, `sections` (JSON, выбранные разделы), `status` (completed/failed), `summary` (общий вывод), `usage_tokens`/`usage_cost`, `error`, `created_at`/`completed_at`;
- `insight_findings` — находки анализа (`run_id` FK CASCADE): `section`, `title`, `summary`, `used_data` (JSON — какие данные использованы, прозрачность).

**LLM-пайплайн** (`app/llm/pipeline/insights.py` + `insights_prompts.py`):
- контекст собирается **только из выбранных разделов за выбранный период** (`build_insights_context`, 7 разделов);
- промпт требует показывать использованные данные (`used_data`) и **не объявляет корреляцию причиной** (правило PRODUCT_OVERVIEW §12);
- режим `prefs.llm_mode` (safe/expanded, ADR-087) расширяет рамку; usage трекается на активном LLMProviderConfig.

**API:** страница `/insights` (пикер разделов чекбоксами + период + «Запустить анализ» + результат + история с удалением), `POST /insights/run`, `POST /insights/runs/{id}/delete`; JSON `/api/v2/insights` (bearer: GET список, POST запуск, GET /runs/{id}). Object-level auth: чужой run → 404; удаление run каскадит findings.

**Дашборд-блок** `dash-block-insights` (последний запуск / число находок / период), настраиваемый в /settings (DASH_BLOCKS); nav-пункт «Инсайты» (иконка `insights.svg` из пакета), feature flag `insights_enabled` (default true).

**Relief-only (PD-013):** анализ без игровой интеграции (XP/баллы/штрафы); все записи Private Record (DATA_LIFECYCLE.md).

**Supersedes:** нет (новое). Следует паттерну Health (13) / Journal (14) / Care (15) — вертикальный срез личного контура.
**Status:** ✅ реализовано (Шаг 17). 11/11 таргетных + 164 регрессионных (care/journal/catalog/health/medication/shell/design/icon/mobile) ✅, ruff ✅, i18n 1196/1196, single head ✅. Прод не тронут.
