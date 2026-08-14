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
