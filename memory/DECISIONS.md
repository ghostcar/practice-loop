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
| ADR-096 | 2026-08-17 | Шаг 17d: Event-напоминания + настройки и таймер в боте | По решению владельца «настройки и таймер в боте, плюс напоминания не только в фиксированное время, но и не задолго до события». **Relief-only (PD-013)**. (1) **Event-напоминания (ADR-096)**: в reminder engine добавлен режим `event` — коллекторы `med_dose` (доза в конкретное `times_of_day`-время, lead-окно) и `timer_slot_upcoming`/`timer_task_due` (lead-окно вместо 24ч); дедуп `med_dose:{schedule}:{date}:{HH:MM}` и occurrence-ключи таймера; scheduler теперь два каденса — daily (`reminder_time`) + event (`reminder_event_interval_minutes`, default 15m; lead `reminder_event_lead_minutes`, default 30m). (2) **Настройки в боте**: `/settings` расширен — язык + discretion (off/always/schedule) + llm_mode (safe/expanded) инлайн-меню. (3) **Таймер в боте (полное управление)**: `/lock_slots` (открыть/закрыть окно), `/lock_tasks` (reveal/complete/skip), `/lock_close <номер бирки>` (закрыть окно с биркой, `require_tag`), `/lock_tag <номер>` (проверка бирки через `lookup_tag`), ownership-проверки во всех inline-действиях. Без миграций. 6/6 новых + 31 таргетный (reminders/telegram) ✅, ruff ✅, i18n без изменений (бот — EN hardcoded). | принято |
| ADR-097 | 2026-08-17 | Шаг 17e: Команды бота для личного контура (med/health/cycle/care) | По решению владельца «доделывать команды бота». 4 команды (relief-only, PD-013; без миграций, бот EN-hardcoded как ранее): (1) **`/med`** — приёмы на сегодня (`_schedule_summary`) + инлайн «Taken» → `MedIntake` + `on_medication_taken` (adherence XP, positive-only); (2) **`/health`** — чек-ин mood/energy инлайн 1–5 (upsert `HealthState` на сегодня); **`/cycle`** — фаза/день цикла/оценка след. месячных (`_get_cycle_context`); (3) **`/care`** — due-рутины по `frequency_days` + сеансы курсов, инлайн «Done» → `CareEntry` / отметка сеанса. `/start` help обновлён. 3/3 новых + 80 таргетных (telegram/medication/health/care/reminders) ✅, ruff ✅. | принято |
| ADR-098 | 2026-08-17 | Шаг 17f: Reminder time/tz на пользователя | По решению владельца «reminder_time/reminder_tz на пользователя вместо глобальных REMINDER_*». (1) **Prefs**: `users.prefs.reminder_time` (HH:MM) + `reminder_tz` (IANA); пустое/невалидное = наследовать глобальный `REMINDER_TIME`/`REMINDER_TZ` (default 09:00 UTC — теперь дефолт, не единственное значение); `_valid_hhmm` ужесточена (0–23/0–59). (2) **Engine**: `run_reminder_cycle_for_user(db, user, mode, tz_name)` — «сегодня»/«сейчас» в tz пользователя; `run_reminder_cycle` итерирует пользователей с per-user tz. (3) **Scheduler**: daily-триггер per-user (локальное время ≥ reminder_time и не запускалось сегодня — устойчиво к дрейфу 60s-цикла); event-цикл — глобальный каденс с per-user «сейчас»; auto-insights — раз в день по глобальному дефолту. (4) **UI /settings**: секция «Напоминания» (time input + tz datalist). Без миграций. 4/4 новых + 34 таргетных (reminders/settings) + 7 discretion ✅, ruff ✅, i18n 1210/1210. | принято |
| ADR-099 | 2026-08-17 | Шаг B2: Chastity device care (уход за устройством) | По решению владельца (этап B, §6.2). Журнал ухода за физическим устройством во время ношения: `chastity_device_events` (миграция 054) — event_type comfort/problem/maintenance/cleaning/inspection, comfort_level 1–5, severity low/medium/high, device_id (FK inventory SET NULL), session_id (FK SET NULL). **Relief-only (PD-013)**. JSON `/api/v2/devices/events` (GET/POST/DELETE) + form `/device-events` + секция «Уход за устройством» на session detail. 4/4 теста ✅, ruff ✅, i18n parity 0. | принято |
| ADR-100 | 2026-08-17 | Шаг B3/C2: Chastity wear check-ins + LLM-верификация фото | По решению владельца (этап B/C, §6.6, Q13). `chastity_check_ins` (миграция 055) — mood/comfort_level 1–5, notes, media_id, verification_result_id, session_id. Верификация `POST .../{id}/verify` переиспользует `media_verify` (chastity_closed/code_match, HMAC-код, сервер — авторитет, авто-потребление challenge при match). **Relief-only (PD-013)**. JSON `/api/v2/chastity/check-ins` + form `/chastity-checkins` + секция «Чекины» на session detail. 5/5 теста ✅, ruff ✅, i18n parity 0. | принято |
| ADR-101 | 2026-08-17 | Шаг C1: Aftercare — отдельный модуль | По решению владельца «Aftercare — отдельный модуль». `aftercare_entries` (миграция 056) — kind physical/emotional/debrief/hydration/rest/other, comfort_level, notes; journal_entry_id (FK sj_entries SET NULL), timer_session_id (по ID). **Relief-only (PD-013)**. Страница `/aftercare` + JSON `/api/v2/aftercare` (GET/POST/DELETE) + дашборд-блок + nav + флаг `aftercare_enabled`. 6/6 теста ✅, ruff ✅, i18n parity 0. | принято |
| ADR-102 | 2026-08-17 | Шаг C3: Consent records (согласия) | По решению владельца «Оба (consent + check-in)». `consent_records` (миграция 057) — consent_type llm_expanded/media_verification/data_processing/custom, state granted/revoked, scope, version (каждое изменение — новая запись), granted_at/revoked_at. **Relief-only (PD-013)**. Страница `/consent` + JSON `/api/v2/consent` (GET/POST/DELETE) + nav + флаг `consent_enabled`. 6/6 теста ✅, ruff ✅, i18n parity 0. | принято |
| ADR-103 | 2026-08-17 | Шаг C4: Today projection (единый экран дня) | По решению владельца (этап C, §10.1). Страница `/today` — view-level сшивка сводок модулей (Tracker/Timer/Medication/Health/Cycle/Care/Aftercare/Journal/Training/Diet), новой агрегированной модели нет. Nav: дашборд → «Дашборд», новый пункт «Сегодня». 2/2 теста + 168 регрессионных ✅, ruff ✅, i18n parity 0. | принято |
| ADR-104 | 2026-08-18 | Durable purpose/version consent + BYOK disclosure | Одно согласие на цель/версию действует до отзыва или смены условий; модули запрашиваются при первом входе/включении; история append-only; BYOK отдельно фиксирует ответственность пользователя за выбор и настройку внешнего провайдера. | принято |
| ADR-105 | 2026-08-18 | P1 18+ каталог: хранение safety contract | По решению владельца — типизированный `safety_contract` JSONB + `automation_allowed`/`adult_only`/`content_status`/`content_version` на `Entity` (без пересмотра ADR-031). Foundation 7 карточек приняты как есть (`reviewed`); automation выключен у всех 34 editorial candidates до первого прод-прогона. | принято |
| ADR-106 | 2026-08-19 | P1c: одобрение пользователя — граница автоматизации | По решению владельца: **опт-ин = одобрение по умолчанию** для всех активностей (каталог/профиль/привнесённые); `risk_level`/`automation_allowed` — информационные метаданные, не гейты. Отменяет риск-гейт REM §5.2 в рантайме (`filter_automation_eligible` → passthrough). Остаются жёсткими: stop/отказ всегда, медиа не обязательно, без штрафа за отказ, без обхода safety-фильтров, без авто-эскалации. | принято |
| ADR-107 | 2026-08-19 | Care: место проведения процедуры | По решению владельца: в блоке ухода и процедур должно быть место проведения (салон, название, может быть адрес) и показываться пользователю. `place_name` + `place_address` на care_routines/care_entries/care_courses (миграция 062); формы, списки, JSON API, i18n EN/RU. | принято |
| ADR-108 | 2026-08-19 | Множественные параллельные сессии | По решению владельца: сессий может быть запущено несколько одновременно; механизм дочерних сессий внутри длительной — отдельная задача, не реализуется. Снят partial unique index `ix_activity_sessions_one_active` (миграция 013 → 063); `create_session`/`json_create_session` всегда создают новую сессию; дашборд и `/today` показывают все активные сессии. | принято |
| ADR-109 | 2026-08-19 | ERP-аптечка и LLM-поиск аналогов | По решению владельца: расширение модуля Аптечки до уровня фарм-справочника ERP (МНН `active_ingredient`, аналоги `analogues` JSON, форма `form`, дозировка `strength`, производитель `manufacturer`, хранение `storage_conditions`, рецепт `prescription_required`), миграция `065_medication_pharmacy_erp`. LLM-ассистент: `POST /medications/{id}/find-analogs` (поиск дженериков и аналогов по МНН с дисклеймером). UI `/medications` с категориальными табами и 1-click действиями. | принято |
| ADR-110 | 2026-08-19 | Абстрактное имя пользователя вместо email в шапке | По решению владельца: email не показывается в шапке/меню — вводится `users.display_name` (миграция 066), пользователь задаёт его в настройках; без него — нейтральный фолбэк («User»/«Пользователь»). Email остаётся только на приватной странице `/account`. | принято |
| ADR-111 | 2026-08-19 | Гендерно-инклюзивный Дневник Здоровья и Календарь Ритмов | По решению владельца: расширение Health & Cycle до инклюзивного комплекса с поддержкой ГТ (HRT / ZHT), эмуляции циклов (`natural_menstrual`, `hrt_emulated`, `biorhythm_custom`, `disabled`), отслеживанием post-session откликов (drop / bruising / skin sensitivity) и расчётом фаз (миграция 067). Интерактивные настройки профиля, отметки ГТ и гибкие события. | принято |
| ADR-112 | 2026-08-19 | Шаг 20: Оперативный Дашборд и Плашка Предупреждений (Alert Bar & Quick Actions) | По решению владельца: расширение главного Дашборда (`/dashboard` и `/today`) динамической плашкой предупреждений Alert Bar (остатки препаратов/инвентаря, Post-session Drop, активный замок ограничения доступа, приём ГТ) и панелью 1-Click быстрого доступа к чек-инам и отметкам. | принято |
| ADR-113 | 2026-08-19 | Шаг 21: Chastity Suite & Keyholder Dynamics (Chaster.app paradigm) | По решению владельца: полная адаптация модуля Chastity к стандарту и терминологии Chaster.app (`Chastity`, `Lock`, `Keyholder Bot`, `Extensions`, `Tag Check-in`, `Emergency Key`, привязка девайсов из Инвентаря), миграция 068. Интеграция с LLM AI Keyholder Bot для оценки продлений, отчётов и авто-паузы при `Post-session Drop` или тяжелых фазах здоровья. | принято |
| ADR-114 | 2026-08-19 | Шаг 22: Тренировки, Дисциплина и Оборудование (Training & Equipment) | По решению владельца: привязка тренировок и практик к имеющемуся Инвентарю (оборудование, снаряды, средства дисциплины, миграция 069), авто-адаптация нагрузок под состояние здоровья (`recovery`, `post_session_drop`, `skin_sensitivity`) и фазы ритмов/ГТ с участием LLM-Инструктора. | принято |
| ADR-115 | 2026-08-19 | Шаг 23: Настройка Отключения Авто-Снижения Нагрузок и Автоматизация Aftercare | По решению владельца (осознанный выбор): введение в настройки пользователя `health_adaptation_mode` (`auto_reduce` / `strict_no_reduction`) и градаций чувствительности `health_adaptation_sensitivity` (`gentle` / `moderate` / `strict`), миграция 070. Автоматизация Aftercare-протоколов: `CareRoutine.aftercare_trigger_drop`, привязка препаратов Аптечки (`medication_ids`) и LLM-Ассистент Aftercare (`POST /api/v2/care/aftercare/generate`). | принято |
| ADR-116 | 2026-08-19 | Шаг 24: Гендерно-Инклюзивные Профили Партнёров и ИИ-Консультант по Динамике и Границам | По решению владельца: расширение модуля Журнала до инклюзивных Профилей Партнёров (`sj_partners` + `roles`, `identity_notes`, `hard_limits`, `soft_limits`, `safewords`, `aftercare_preferences`, миграция 071) и внедрение LLM-Консультанта по динамике (`POST /api/v2/journal/partners/{id}/analyze`). | принято |
| ADR-117 | 2026-08-19 | Шаги 25-26: Интерактивный Визуальный Конструктор Схем и Единый Кросс-Модульный ИИ-Агент | По решению владельца: создание Интерактивного Визуального Конструктора схем параметров (`app/templates/components/schema_builder.html` + `/admin/schema-builder`), внедрение Единого Персона-Движка ИИ (`app/llm/pipeline/persona.py`) с выбором ролей (Наблюдатель, Ключник, Ведущий/Верхний) и 1-Click экспортом медицинского/личного отчёта (`POST /api/v2/insights/export-report`). | принято |
| ADR-122 | 2026-08-19 | Отложенный Бэклог Социальных и Межпользовательских Фич (Deferred Social Scope) | По решению владельца: все межпользовательские интерактивные функции (включая Live WebSocket Pair Session Sync, мульти-пользовательский стрим и социальные шеринги) перманентно помещаются в отложенный бэклог под флагом `SOCIAL_ENABLED=false`. Основной акцент портала — на индивидуальном и парном личном пространстве (Private Record). | принято |
| ADR-123 | 2026-08-19 | Стратегическое Видение: Специализированный ИИ-Ассистент PracticeLoop (Autonomous Practice Agent) | Решение владельца: эволюция LLM-ядра PracticeLoop в автономного специализированного ИИ-Ассистента (аналог Hermes Agent / OpenClaw для взрослых практик, BDSM, Chastity и Care). Агент работает через Tool Calling (`check_session`, `generate_task`, `trigger_aftercare`, `record_health`), поддерживает долгосрочную контекстную память, персоны Ключника/Верхнего/Заботливого гида и событийно-ориентированный проактивный трекинг в Telegram/In-App. | принято |
| ADR-118 | 2026-08-19 | Расширение Telegram-бота v3 (Chastity Keyholder, Aftercare Protocol & Medical Report) | По решению владельца: добавление интерактивных команд и inline-кнопок в Telegram-бот (`app/telegram/bot.py`): `/keyholder` (`/chastity`) с вызовом оценки ИИ-Ключника (`keyholder_eval`), `/aftercare` для мгновенной генерации Aftercare-протокола (`aftercare_gen`) и `/report` для 1-Click выгрузки медицинско-персонального отчёта. | принято |
| ADR-119 | 2026-08-19 | P1g: полный каталог 18+ (принудительное продвижение всех 163 записей) | По решению владельца: все подготовленные данные приведены к seed-ready; исключённые (`manual_reference`/`rewrite_required`/`research_backlog`) принудительно включены; нейтральные имена заменены на прямые принятые термины 18+/БДСМ/кинк. `tools/adult_catalog_promote.py` генерирует `adult_activity_full_catalog.v1.json` (154 карточки = 34 candidates + 120 promoted), флип гейтов (`seed_ready=true`, `import_allowed=true`, `owner_override=true`), дополнительные названия как `alternate_names`. Safety-инварианты сохранены: `automation_allowed=false` у всех promoted, `research_backlog` (вкл. breath) → `content_kind=reference` (неисполняемые, без таймеров). Importer читает full catalog (161 сущность = 7 foundation + 154). Дополнено: синонимы 85→226 (транслитерации → английские термины), 33 extension-карточки для 4 категорий (итог 187 карточек / 194 сущности), фитнес/трекер-шум (55 названий) помечен `noise=true`+`seed_ready=false` и исключён из пула синонимов. | принято |
| ADR-095 | 2026-08-17 | Шаг 17c: Reminders+Telegram, курсы процедур, авто-инсайты, Cycle-инсайты | По решению владельца «давай отложенное реализовывать, в том числе уведомления через телеграм» (все типы + курсы + авто-инсайты + Cycle). **Relief-only (PD-013)**: напоминания/курсы без очков/штрафов. (1) **Reminder engine** `app/reminders/` + `reminder_log` (миграция 052): коллекторы (медикаменты due/low/expiring; средства low-stock/expiring; процедуры по frequency_days; курсы next-session; таймер окна/задачи), дедуп unique (user,kind,key), доставка in-app + Telegram + push, discretion-нейтрализация; asyncio-планировщик (reminder_time/tz, REMINDER_ENABLED). (2) **Курсы процедур** `care_courses`+`care_course_sessions` (миграция 053): N сеансов с интервалом, прогресс, next-session reminder, секция /care + JSON /api/v2/care/courses. (3) **Авто-инсайты**: prefs.insights_auto/insights_auto_days + `app/insights/scheduler.run_auto_insights`. (4) **Cycle-инсайты**: раздел `cycle` в INSIGHT_SECTIONS + `_ctx_cycle` (фазы + агрегаты mood/satisfaction/skin по фазам, без причинности §9.4). 13/13 таргетных + 121 регрессионный ✅, ruff ✅, i18n 1206/1206, single head ✅. | принято |
| ADR-094 | 2026-08-17 | Шаг 17b: Care Products — остатки/сроки/фото + кросс-модуль | По решению владельца «каталог средств дорабатывать и кросс-модульное взаимодействие» (8 направлений). **Relief-only (PD-013)**: без игровой интеграции. Доработка `care_products` (+quantity остаток, +expiry_date срок, +catalog_item_id FK activity_catalog SET NULL — связь с универсальным каталогом), фото средства (owner_type=care_product, POST /care/products/{id}/media), join `care_routine_products` (рекомендуемые средства для процедуры, CASCADE). Кросс-модульные мягкие ссылки JSON по ID (DATA_LIFECYCLE.md): `lock_slot_rules.care_product_ids` (средства окна таймера), `entities.care_product_ids` (средства для трекер-задачи), `sj_entries.care_product_ids` (использованные средства в журнале); средства в контексте Insights (расход/регулярность/low-stock). Валидация владельца во всех местах (чужое → 400); JSON-колонки хранят строки UUID. Миграция 051, single head. 12/12 таргетных + 97/97 регрессионных (care/journal/catalog/insights) + 100/100 locktimer ✅, ruff ✅, i18n 1197/1197. | принято |
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

### ADR-094 — Care Products: остатки/сроки/фото + кросс-модуль (Шаг 17b)
**Date:** 2026-08-17
**Decision:** По решению владельца «каталог средств дорабатывать и кросс-модульное взаимодействие» (8 направлений). Доработка каталога средств/косметики (Шаг 16b) и связывание его с остальными модулями личного контура.

**Доработка средства (`care_products`, миграция 051, single head):**
- `quantity` (остаток, default 0), `expiry_date` (срок годности), `catalog_item_id` (FK `activity_catalog` SET NULL — связь с универсальным каталогом, домен care);
- low-stock/expiring-бейджи на странице /care (quantity ≤ 1; expiry ≤ today+30д);
- фото средства через `owner_type=care_product` в media registry/allowlist + `POST /care/products/{id}/media`.

**Кросс-модульные связи (мягкие ссылки JSON по ID, DATA_LIFECYCLE.md — без FK, отдельное удаление):**
- `care_routine_products` — join-таблица рекомендуемых средств для процедуры (CASCADE) + мультиселект в форме рутины;
- `lock_slot_rules.care_product_ids` — средства для окна таймера (пикер в форме слота + отображение в открытом окне);
- `entities.care_product_ids` — средства для трекер-задачи (пикер в my_entities);
- `sj_entries.care_product_ids` — использованные средства в записи журнала (мультиселект в форме/complete + JSON);
- Insights: контекст care дополнен расходом средств (сколько раз использовалось) + low-stock (низкий остаток/истёкший срок).

**Валидация:** чужое средство → 400 во всех местах; JSON-колонки хранят строки (UUID не сериализуется в JSON). Relief-only (PD-013): без игровой интеграции.

**Supersedes:** дополняет ADR-092 (Care Products) и ADR-091 (Activity Catalog).
**Status:** ✅ реализовано (Шаг 17b). 12/12 таргетных + 97/97 регрессионных (care/journal/catalog/insights) + 100/100 locktimer ✅, ruff ✅, i18n 1197/1197, single head ✅. Прод не тронут.

### ADR-095 — Reminders+Telegram, курсы процедур, авто-инсайты, Cycle-инсайты (Шаг 17c)
**Date:** 2026-08-17
**Decision:** По решению владельца «давай отложенное реализовывать, в том числе уведомления через телеграм». Реализованы четыре связанных направления (все relief-only, PD-013).

**1. Reminder engine (`app/reminders/` + `reminder_log`, миграция 052):**
- коллекторы напоминаний: медикаменты (due today по расписанию / низкий остаток / истекающие), средства ухода (`care_products`: low-stock quantity≤1 / expiring ≤30д), процедуры ухода (`care_routines` по `frequency_days`), курсы (next session), таймер (предстоящие окна/задачи в lookahead 24ч);
- дедупликация через `reminder_log` (unique user_id+kind+dedupe_key): daily-пункты пересрабатывают ежедневно, state-пункты — разово, occurrence-пункты — разово на occurrence;
- доставка: in-app `Notification` (type=reminder) + Telegram (`send_telegram_notification`) + push (`dispatch_push`), тексты нейтрализуются при discretion (`neutral_notification`, ADR-081);
- asyncio-планировщик (`app/reminders/scheduler.py`, `reminder_time`/`reminder_tz`/`REMINDER_ENABLED`, default 09:00 UTC) в lifespan.

**2. Курсы процедур (серии) — `care_courses` + `care_course_sessions`, миграция 053:**
- курс из N сеансов (`total_sessions`, `interval_days`, `start_date`, `area`, `catalog_item_id`); сеансы генерируются при создании (номер + дата), статус pending/done/skipped, мягкая ссылка `entry_id` на запись ухода;
- секция на /care (форма + прогресс-чипы + «done» по клику), JSON `/api/v2/care/courses`;
- напоминание о следующем сеансе (`care_course_session`) через reminder engine.

**3. Авто-инсайты (`app/insights/scheduler.py`):** `prefs.insights_auto` + `insights_auto_days`; `run_auto_insights` выполняется в цикле reminder-планировщика для opted-in пользователей с активным LLM-конфигом (lookback window, всё секции).

**4. Cycle-инсайты:** раздел `cycle` в `INSIGHT_SECTIONS` + `_ctx_cycle` (фаза по дням периода, агрегаты mood/satisfaction/skin_reaction по фазам — без причинности, расчётная фаза §9.4).

**Supersedes:** дополняет ADR-093 (Insights) / ADR-090 (Care) / ADR-084 (Medication).
**Status:** ✅ реализовано (Шаг 17c). 13/13 таргетных + 121 регрессионный (care/insights/medication/health/shell) ✅, ruff ✅, i18n 1206/1206, single head ✅. Прод не тронут.

### ADR-096 — Event-напоминания + настройки и таймер в боте (Шаг 17d)
**Date:** 2026-08-17
**Decision:** По решению владельца «настройки и таймер в боте, плюс напоминания не только в фиксированное время, но и не задолго до события». Три направления (relief-only, PD-013; без миграций).

**1. Event-напоминания («незадолго до события»):**
- `app/reminders/engine.py` — режим `collect_reminders(..., mode="event")`: коллекторы `_medication_dose_reminders` (доза в конкретное `times_of_day`-время, срабатывает в `[доза - lead, доза]`, дедуп `med_dose:{schedule_id}:{date}:{HH:MM}`) и `_timer_reminders` (окно/задача в lead-окне, occurrence-дедуп). `_lead_minutes()` = `settings.reminder_event_lead_minutes` (default 30).
- `app/config.py` — `reminder_event_interval_minutes` (default 15) и `reminder_event_lead_minutes` (default 30).
- `app/reminders/scheduler.py` — два каденса в одном asyncio-цикле: daily-батч (`reminder_time`, плюс авто-инсайты) + event-цикл каждые `reminder_event_interval_minutes`.
- Daily-батч сохранён (due-сводка/остатки/истекающие/рутины/курсы); таймер переехал в event (lead-окно вместо 24ч lookahead).

**2. Настройки в боте:** `/settings` расширен — язык (EN/RU), discretion (off/always/schedule), llm_mode (safe/expanded) инлайн-меню с re-render текущего состояния; пишутся в `users.prefs` через `sanitize_prefs`.

**3. Таймер в боте (полное управление):**
- `/lock_slots` — предстоящие/открытые окна с кнопками Open/Close;
- `/lock_tasks` — задачи с Reveal/Complete/Skip;
- `/lock_close <номер бирки>` — закрыть открытое окно (при `require_tag` номер обязателен);
- `/lock_tag <номер>` — проверка номерной бирки через `lookup_tag` (совпадает/не найдена);
- inline-действия (`slot_open`/`slot_close`/`slot_close_confirm`/`task_reveal`/`task_complete`/`task_skip`) вызывают сервисы `app/locktimer/services/execution.py` с ownership-проверкой (сессия владельца).

**Supersedes:** дополняет ADR-095 (reminder engine), ADR-028/ADR-003 (Telegram-бот), ADR-066 (номерные бирки).
**Status:** ✅ реализовано (Шаг 17d). 6/6 новых event-тестов + 31 таргетный (reminders/telegram) ✅, ruff ✅, i18n без изменений (бот — EN hardcoded, как ранее), single head без изменений (миграций нет). Прод не тронут.

### ADR-097 — Команды бота для личного контура (Шаг 17e)
**Date:** 2026-08-17
**Decision:** По решению владельца «доделывать команды бота» (личный контур). В `app/telegram/bot.py` добавлены 4 команды (relief-only, PD-013; без миграций, бот остаётся EN-hardcoded как ранее).

**1. `/med` — медикаменты:** данные из `_schedule_summary` (`app.api.medication`): due-приёмы + expiring + low stock. Инлайн «Taken» (`med_take:{schedule_id}`) — создаёт `MedIntake(status=taken)` и вызывает `on_medication_taken` (ADR-085: adherence XP + достижения, positive-only, никогда не штрафует).

**2. `/health` + `/cycle`:** `/health` — сегодняшний `HealthState` (mood/energy/sleep) с инлайн-кнопками mood/energy 1–5 (`health_mood:`/`health_energy:`, upsert строки на сегодня). `/cycle` — `_get_cycle_context` (`app.api.health`): фаза, день цикла, длина; оценка даты следующих месячных `today + (cycle_length − day + 1)`. Фаза всегда «estimated» (§9.4, не выдаётся за факт).

**3. `/care`:** due-рутины по `frequency_days` (последняя `CareEntry`); инлайн «Done» (`care_done:{routine_id}`) — `CareEntry` на сегодня + снимок фазы Cycle (`_cycle_snapshot`); активные курсы (`care_courses`) — ближайший pending-сеанс + «Done» (`care_course_done:{session_id}`) → `status=done` + `completed_at`.

**4. `/start` help** — дополнен 4 новыми командами.

**Supersedes:** дополняет ADR-096 (бот), ADR-084 (medication), ADR-086 (health/cycle), ADR-090/ADR-095 (care).
**Status:** ✅ реализовано (Шаг 17e). 3/3 новых теста + 80 таргетных (telegram/medication/health/care/reminders_event) ✅, ruff ✅, импорт приложения ✅. Прод не тронут.

### ADR-098 — Reminder time/tz на пользователя (Шаг 17f)
**Date:** 2026-08-17
**Decision:** По решению владельца «reminder_time/reminder_tz на пользователя вместо глобальных REMINDER_*». Глобальные `REMINDER_TIME`/`REMINDER_TZ` становятся **дефолтами**, а не единственным значением. Без миграций.

**1. Prefs (`app/prefs.py`):** новые поля `users.prefs.reminder_time` (HH:MM) и `reminder_tz` (IANA). Пустое или невалидное значение = наследовать глобальный `settings.reminder_time`/`settings.reminder_tz`. Валидация `_valid_hhmm` ужесточена (0–23 час, 0–59 мин — ранее «25:99» считалось валидным); tz проверяется через `zoneinfo.ZoneInfo`.

**2. Engine (`app/reminders/engine.py`):** `run_reminder_cycle_for_user(db, user, mode, tz_name)` — считает «сегодня»/«сейчас» в tz пользователя (`prefs.reminder_tz or tz_name`), что делает границы суток и время доз корректными для пользователя. `run_reminder_cycle` итерирует всех пользователей с per-user tz (tz_name — фолбэк).

**3. Scheduler (`app/reminders/scheduler.py`):** daily-триггер стал per-user — для каждого пользователя локальное время `>= reminder_time` и цикл ещё не запускался в его локальный день (устойчиво к дрейфу 60-секундного цикла, в отличие от точного совпадения минуты). Event-цикл (ADR-096) — глобальный каденс, но «сейчас» для каждого пользователя в его tz. Auto-insights (ADR-095) — раз в день по глобальному дефолтному расписанию.

**4. UI (`/settings`):** секция «Напоминания» — время (`<input type=time>`) + часовой пояс (IANA, `<datalist>`), пустое поле показывает эффективный глобальный дефолт.

**Supersedes:** дополняет ADR-095 (reminder engine), ADR-096 (event-напоминания/бот), ADR-081 (prefs).
**Status:** ✅ реализовано (Шаг 17f). 4/4 новых + 34 таргетных (reminders/settings) + 7 discretion ✅, ruff ✅, i18n 1210/1210. Прод не тронут.

### ADR-099 — Chastity device care (уход за устройством, Шаг B2)
**Date:** 2026-08-17
**Decision:** По решению владельца (этап B — глубина Chastity, PRODUCT_OVERVIEW §6.2). Журнал ухода за физическим устройством во время ношения: комфорт, проблемы, обслуживание. **Relief-only (PD-013)** — без игровой интеграции.

**Модель:** `chastity_device_events` (миграция 054): `event_type` (comfort/problem/maintenance/cleaning/inspection), `comfort_level` (1–5), `severity` (low/medium/high), `notes`; `device_id` — мягкая ссылка на inventory item (FK SET NULL), `session_id` — мягкая ссылка на сессию ношения (FK SET NULL).

**API/UI:** JSON `/api/v2/devices/events` (GET/POST/DELETE, owner-scoped) + form `/device-events` → redirect; секция «Уход за устройством» на session detail таймера.

**Status:** ✅ реализовано. 4/4 теста + 168 регрессионных ✅, ruff ✅, i18n parity 0, single head.

### ADR-100 — Chastity wear check-ins + LLM-верификация фото (Шаг B3/C2)
**Date:** 2026-08-17
**Decision:** По решению владельца (этап B/C, PRODUCT_OVERVIEW §6.6, Q13). Регулярный check-in ношения (состояние/комфорт/отчёт) + опциональная LLM-верификация фото. **Relief-only (PD-013)**.

**Модель:** `chastity_check_ins` (миграция 055): `mood`/`comfort_level` (1–5), `notes`, `media_id` (FK SET NULL), `verification_result_id` (мягкая ссылка), `session_id` (FK SET NULL).

**Верификация (B3/Q13):** `POST /api/v2/chastity/check-ins/{id}/verify` переиспользует `app/llm/pipeline/media_verify` (`verify_media_with_llm`): типы `chastity_closed`/`code_match`; код не пишется plaintext (HMAC), сервер — авторитет сверки; авто-потребление challenge при `match` (ADR-075).

**Status:** ✅ реализовано. 5/5 теста + 168 регрессионных ✅, ruff ✅, i18n parity 0, single head.

### ADR-101 — Aftercare — отдельный модуль (Шаг C1)
**Date:** 2026-08-17
**Decision:** По решению владельца «Aftercare — отдельный модуль» (этап C). Структурированный журнал заботы после сцены (PRODUCT_OVERVIEW §5.3/§7). **Relief-only (PD-013)**.

**Модель:** `aftercare_entries` (миграция 056): `kind` (physical/emotional/debrief/hydration/rest/other), `comfort_level` (1–5), `notes`; `journal_entry_id` (FK sj_entries SET NULL), `timer_session_id` (по ID без FK).

**API/UI:** страница `/aftercare` + JSON `/api/v2/aftercare` (GET/POST/DELETE) + дашборд-блок `dash-block-aftercare` + nav + флаг `aftercare_enabled`.

**Status:** ✅ реализовано. 6/6 теста + 168 регрессионных ✅, ruff ✅, i18n parity 0, single head 056.

### ADR-102 — Consent records (Шаг C3)
**Date:** 2026-08-17
**Decision:** По решению владельца «Оба (consent + check-in)». Журнал явных согласий на чувствительную обработку: расширенный LLM-режим, фото-верификация, обработка данных. **Relief-only (PD-013)**.

**Модель:** `consent_records` (миграция 057): `consent_type` (llm_expanded/media_verification/data_processing/custom), `state` (granted/revoked), `scope`, `version` (каждое изменение — новая запись, история не перезаписывается), `granted_at`/`revoked_at`.

**API/UI:** страница `/consent` + JSON `/api/v2/consent` (GET/POST/DELETE) + nav (system group) + флаг `consent_enabled`.

**Status:** ✅ реализовано. 6/6 теста + 168 регрессионных ✅, ruff ✅, i18n parity 0, single head 057.

### ADR-103 — Today projection (Шаг C4)
**Date:** 2026-08-17
**Decision:** По решению владельца (этап C, PRODUCT_OVERVIEW §10.1). Единый спокойный экран дня `/today`: view-level сшивка существующих сводок модулей (Tracker-задачи + активная сессия, Timer, Medication, Health/Cycle, Care, Aftercare, Journal, Training, Diet). **Новой агрегированной модели не создаётся**.

**Nav:** пункт «Сегодня» (`/today`), дашборд переименован в «Дашборд» (ранее label «Сегодня»).

**Status:** ✅ реализовано. 2/2 теста + 168 регрессионных ✅, ruff ✅, i18n parity 0.

### ADR-104 — Durable purpose/version consent и BYOK disclosure
**Date:** 2026-08-18
**Decision:** По решению владельца согласие запрашивается один раз для конкретной цели и версии
условий и действует всё время пользования порталом — до явного отзыва либо существенного
изменения условий. На первом входе запрашиваются согласия включённых модулей; новый модуль
запрашивает отдельное согласие при включении в профиле. Отключение модуля не является отзывом.

**Целостность:** журнал append-only; DELETE отдельной записи удалён. Grant/revoke сериализуется
по пользователю, версии защищены unique constraint `(user_id, consent_type, version)`, принятое
раскрытие фиксируется `terms_version`. Повторный grant той же версии идемпотентен.

**Enforcement:** актуальное согласие обязательно для expanded LLM, media verification и
подключения/активации BYOK. BYOK-раскрытие прямо говорит, что пользователь сам выбрал и настроил
провайдера, endpoint и ключ, принимает внешние условия и отвечает за выбор/конфигурацию.
Practice Loop не снимает с себя ответственность за собственную безопасность и обработку данных.

**Supersedes:** уточняет ADR-102; продуктовый контракт — PD-022.
**Status:** 🚧 реализация завершена локально; до закрытия нужны PostgreSQL concurrency/regression
и migration roundtrip 057→058.

### ADR-105 — P1 18+ каталог: хранение safety contract
**Date:** 2026-08-18
**Decision:** По решению владельца (сводный owner review P1) физическое хранение safety contract —
типизированный `safety_contract` JSONB на `Entity` плюс отдельные колонки `automation_allowed`,
`adult_only`, `content_status`, `content_version`. Нормализация в отдельные таблицы не выполняется,
ADR-031 остаётся в силе.

**Owner review P1:** 7 foundation-карточек приняты как есть (`status=reviewed`, `review_required=false`);
automation выключен у всех 34 editorial candidates (`automation_allowed=false`) до первого
прод-прогона — lint теперь требует false для всех candidates.

**Запрещено независимо от хранения:** автоматизация elevated/manual-only/research, штраф за
stop/отказ/check-in, обязательное медиа-подтверждение, запрет выключения таймера, автоматическая
эскалация длительности/интенсивности/повторов.

**Status:** ✅ решение принято. Импортер и production import — следующий gate после dry-run importer.

### ADR-106 — P1c: одобрение пользователя — граница автоматизации
**Date:** 2026-08-19
**Decision:** По решению владельца (продолжение сессии после обрыва, философия «пользователь сам
устанавливает рамки»): **опт-ин пользователя — это граница одобрения по умолчанию**. Абсолютно
все активности — и сгенерированные платформой (каталог), и разрешённые пользователем в профиле
(опт-ин), и привнесённые пользователем (личные/импортированные) — считаются одобренными
пользователем по умолчанию. Уровень риска и прочие агентские условности не ограничивают выбор:
`risk_level` и `automation_allowed` остаются информационными метаданными (показываются
пользователю, который сам решает), но не блокируют автоматический выбор LLM из опт-ин набора.

**Supersedes:** риск-гейт REM §5.2 в актуальном коде — `filter_automation_eligible` теперь
passthrough (опт-ин гарантирован выше, в `_get_allowed_entities`); конвенция P1
«automation_allowed=false → manual only» для рантайма (в данных поля сохраняются как метаданные
и provenance). `allow_elevated` сохранён для обратной совместимости, no-op.

**Остаётся жёстким (не отменено):** остановка/отказ всегда доступны; медиа-подтверждение никогда
не обязательно; штраф за stop/отказ/пропуск check-in запрещён; никакого обхода safety-фильтров
провайдеров и кодирования контента для сокрытия от LLM; автоматическая эскалация
длительности/интенсивности/повторов — до отдельного решения владельца.

**Status:** ✅ реализовано: `filter_automation_eligible` → passthrough, метаданные
`automation_allowed`/`adult_only` добавлены в контекст, комментарии pipeline обновлены, тесты
переписаны (test_audit_s57, test_training), документация скорректирована.

### ADR-107 — Care: место проведения процедуры
**Date:** 2026-08-19
**Decision:** По решению владельца: в личном контуре, в блоке ухода и процедур, должно быть
место проведения (салон, название, может быть адрес) и показываться пользователю.

**Модель:** `place_name` (String 200) + `place_address` (String 300) на `care_routines`,
`care_entries` и `care_courses` (миграция 062, `f0e1d2c3b4a5`); дефолты NULL (место не было
известно). **Relief-only (PD-013)** — уход остаётся без игровой интеграции.

**API/UI:** формы добавления процедуры/записи/курса + отображение в списках (иконка location),
JSON `/api/v2/care` (routines/entries/courses) + i18n EN/RU (4 ключа).

**Status:** ✅ реализовано. 2 новых теста (form+display, JSON) — 22/22 test_care ✅, ruff ✅,
i18n parity 0, single head 062.

### ADR-108 — Множественные параллельные сессии
**Date:** 2026-08-19
**Decision:** По решению владельца: сессий может быть запущено несколько одновременно.
Механизм «внутри одной длительной сессии запускается много дочерних коротких» — отдельная
задача, в этой итерации не реализуется.

**Модель:** миграция 013 создала partial unique index `ix_activity_sessions_one_active`
(`owner_id WHERE status IN ('created','active')`) — одна незавершённая сессия на пользователя.
Миграция 063 (`9c8d7e6f5a4b`) удаляет индекс — теперь разрешено любое число параллельных
сессий на пользователя.

**API/UI:** `create_session` (POST /sessions) и `json_create_session` (POST /api/v2/sessions)
больше не идемпотентны — каждый вызов создаёт новую сессию (303/201). Дашборд и `/today`
показывают **все** активные сессии (счётчик + чипы), а не одну. Страница `/sessions` уже
показывала все сессии.

**Status:** ✅ реализовано и проверено на реальном PostgreSQL 15 (throwaway): 5 параллельных
сессий созданы (303/303/303 + 201/201) и запущены (все `active`), индекс удалён, дашборд
«Active session: 5», today «(5)». 12/12 test_sessions + 112 таргетных ✅, ruff ✅, single head
`9c8d7e6f5a4b`.


### ADR-110 — Абстрактное имя пользователя вместо email в шапке
**Date:** 2026-08-19
**Decision:** По решению владельца: header/menu и мобильный sheet не показывают `user.email`
(privacy-инвариант из `test_social_privacy_audit`). Вводится понятие абстрактного имени
пользователя: поле `users.display_name` (String(100), nullable, миграция 066
`066_add_user_display_name`, поверх `065_medication_pharmacy_erp`).

**UI:** шапка (аватар-буква, подпись кнопки, dropdown, мобильный sheet) показывает
`display_name`; пусто → нейтральный фолбэк `t.user_display_fallback` («User»/«Пользователь»).
Поле редактируется в `/settings` (секция «Профиль»), очистка возвращает фолбэк. Email остаётся
только на приватной странице `/account`.

**Status:** ✅ миграция применена на throwaway PG 15 (063→064→065→066), single head,
`test_social_privacy_audit` ✅, settings-password 6/6 ✅, ruff ✅, i18n-паритет 1399/1399 ✅.


### ADR-119 — P1g: полный каталог 18+ (принудительное продвижение всех 163 записей)
**Date:** 2026-08-19
**Decision:** По решению владельца: все подготовленные данные приведены к seed-ready;
ранее исключённые записи (`manual_reference` / `rewrite_required` / `research_backlog`)
принудительно переведены во включённые к загрузке; нейтральные/иносказательные имена заменены
на прямые принятые термины 18+/БДСМ/кинк (скат, копрофагия, урофилия, золотой дождь,
waterboarding, breath play, wax play, хогтай, спредер-бар и т.д.).

**Инструмент:** `tools/adult_catalog_promote.py` — генератор `adult_activity_full_catalog.v1.json`
(154 карточки = 34 owner-reviewed candidates + 120 promoted; 7 foundation отдельно). Идемпотентно
флипует гейты: source inventory `seed_ready=true`, review-файлы `import_allowed=true` +
`owner_override=true` + `user_discoverable_after_moderation=true`, additional titles
`import_allowed=true` + `seed_ready=true`. Дополнительные названия прикрепляются к карточкам как
`alternate_names` (совпадение токенов).

**Safety-инварианты сохранены:** `automation_allowed=false` у всех promoted-карточек;
`research_backlog` (включая breath restriction) → `content_kind=reference` — обнаруживаемые, но
неисполняемые (без таймеров, прогрессии, исполняемых инструкций); fluid/enema без параметров
объёма (`no_automatic_volume`/`no_medical_volume`).

**Importer:** `tools/adult_catalog_import.py` читает foundation + full catalog (161 сущность =
7 foundation + 154 promoted), `content_status=approved`, idempotent по slug. Lint-правила обновлены
под owner-промоушн; `# ruff: noqa` per-file для C408/E501 в SPECS-таблице данных.

**Status:** ✅ 154 карточки сгенерированы, все 163 записи покрыты, гейты флипнуты; 51/51 тестов
manifest+import ✅, ruff ✅, dry-run импортёра `entities=161` (low 63 / elevated 98; auto 7 /
manual 154). Прод не тронут — отдельный prod-импорт по подтверждению.


### ADR-124 — Двухуровневая Библиотека Промптов (System & User Prompts) и Админ-Хаб (/admin/prompts)
**Date:** 2026-08-20
**Decision:** Централизация всех захардкоженных ИИ-промптов портала в единой двухуровневой Библиотеке Промптов (`PromptLibraryItem`, миграция `073_prompt_library_table.py`).

1. **Разделение на 2 Категории**:
   - **Системные промпты (System Prompts)**: системные роли ИИ-Ассистентов, Персон (Keyholder, Controller, Care Guide, Observer) и Vision AI-инспекторов.
   - **Пользовательские промпты (User Prompts)**: шаблоны задач, генераторов Aftercare и медицинских отчетов для врачей.

2. **Плейсхолдеры Переменных (`{{var}}`)**:
   - Шаблоны поддерживают переменные подстановки (`{{safety_context}}`, `{{user_history}}`, `{{care_products}}`).

3. **Админ-Хаб (`/admin/prompts`) & Управление**:
   - Воркбенч редактирования с вкладками для системных и пользовательских промптов.
   - Поддержка мгновенного сброса к заводским настройкам (`Reset to Default`).
   - Функция `get_prompt_template(db, key)` возвращает кастомизированный промпт из БД или дефолтный fallback.

**Status:** ✅ Модель `PromptLibraryItem`, миграция 073, хаб `/admin/prompts` и регистратор `app/prompt_library.py` реализованы и закоммичены.


### ADR-125 — Dynamic Adaptive Training Program Engine & Interactive Hub (/training/adaptive)
**Date:** 2026-08-20
**Decision:** Реализация механизмов динамических многодневных адаптивных тренировочных программ (контроль мочевого пузыря и удержания, Chastity Ramp-Up, выносливость поз).

1. **Модели & Миграция `074_add_adaptive_training_tables.py`**:
   - `AdaptiveProgram` & `AdaptiveProgramStep`: хранят параметры программы, текущую сложность и историю динамических шагов.

2. **Динамическая Адаптация ИИ-Ассистентом (`app/agent/training_adaptive.py`)**:
   - При логировании шага пользователь указывает оценку комфорта (1-5), время удержания и ощущения.
   - ИИ-Ассистент автоматически пересчитывает будущие дни:
     - Оценка >= 4 (легко) → Ramp-Up планового времени (+10 мин).
     - Оценка <= 2 (дискомфорт) → Вставка разгрузочного дня Aftercare / ухода и снижение нагрузки.

3. **Интерактивный UI-Хаб (`/training/adaptive`)**:
   - Конструктор программ с модальным вызовом, шкала времени шагов и модальное окно обратной связи.

**Status:** ✅ Модели, сервисы, миграция 074 и UI-хаб `/training/adaptive` реализованы, проверены тестами (`200 OK`) и закоммичены.



### ADR-135 — Передача владения сообществом и со-модераторы (CommunityMemberRole)
**Date:** 2026-08-21
**Decision:** Расширена модель управления сообществами (миграция `082_community_roles.py` уже создала `community_member_roles`; подключена в этой сессии).

1. **Передача владения (`/communities/{id}/transfer`)**: владелец передаёт `owner_id` активному участнику; роли `owner`/`member` в `community_members` меняются местами. У нового владельца автоматически снимается избыточная роль `co_top`.
2. **Со-модераторы**: владелец назначает/снимает роли `co_top`, `tournament_organizer`, `keyholder`, `trainer`, `care_curator` активным участникам (`/moderators/add`, `/moderators/remove`).
3. **Права доступа**: `_require_manager` (owner ИЛИ co_top/tournament_organizer) вместо `_require_owner` во всех управляющих эндпоинтах агента (квесты, турниры, очки, cockpit). Передача владения и назначение ролей — только владелец.
4. **UI**: в `community_detail.html` — панель «Управление сообществом» (назначение ролей, список активных ролей со снятием, форма передачи владения); в `community_agent.html` — управление по флагу `can_manage` (owner или модератор) вместо `is_owner`.
5. **Бейджи**: участник с ролью модератора помечается «Модератор» в списке участников.

**Status:** ✅ Реализовано, 8 новых тестов (`test_community_governance.py`), полный цикл проверен в браузере на проде (назначение co_top → права модератора → передача владения → 403 бывшему владельцу). Коммит `da58c930`.

### ADR-136 — Рекомпозиция продукта: R0-аудит и 5 документов примирения (Master Brief)
**Date:** 2026-08-21
**Decision:** По `examples/PRACTICE_LOOP_RETHINK_REFACTOR_MASTER.md` проведён R0-аудит (без кода) и созданы 5 deliverables:

1. `memory/PRODUCT_REFRAME.md` — product definition: Personal Core / Intelligence / Virtual Dynamics / Human Dynamics, manual-first, AI опционален, Agency/Protocol/Dynamic/Capability, anti-goals.
2. `memory/IMPLEMENTATION_RECONCILIATION.md` — evidence-based матрица: 134 таблицы / 0 моделей без таблиц / 83 миграции (prod head 083) / 543 роута / 1332 из 1334 тестов.
3. `memory/TECH_DEBT_V2.md` — реестр долга (мёртвые модели, stubs, дублирование, связность, docs drift).
4. `memory/TARGET_ARCHITECTURE_V2.md` — bounded contexts, AgencyPolicy, единый Capability-примитив, Protocol-каркас, Dynamic как проекция, AI proposal/apply pipeline.
5. `memory/REFACTOR_ROADMAP_V2.md` — фазы R0–R9 с exit criteria и первым безопасным батчем.

**Ключевые находки:** automation_triggers / user_league_tiers / user_duels — таблицы без API (мёртвые, флаг или удаление — R1-P0); TimerSocialAdapter — скелет; medication relief-only (health/journal) конфликтует с adherence XP (Telegram /med) — требуется решение; Entity vs activity_catalog — дублирование (FK между ними); 4 системы делегирования (SocialGrant/CapabilityGrant/CommunityDelegation/CommunityRole). 2 failed теста — тест-инфраструктура (.env перекрывает tmp_path), не код.

**Решение:** аудит подтверждает manual-first направление брифа; следующие фазы (R1+) начинать только после согласования первого безопасного батча с владельцем. Бриф раздел 21 (anti-goals) — обязателен.

**Status:** ✅ Документы созданы и закоммичены. Код не менялся (R0 = только аудит).

### ADR-137 — Лекарства: настраиваемая positive-only геймификация (смягчение PD-013, ADR-085)
**Date:** 2026-08-21
**Decision:** Разрешение противоречия «medication relief-only vs adherence XP» (Master Brief §7.1, TECH_DEBT_V2 D3). Геймификация лекарств **НЕ запрещена доменом** — это пользовательская, конфигурируемая политика положительного подкрепления.

1. **Настройка `prefs.med_gamification`** (default **ON** — сохраняет существующее поведение ADR-085; отсутствие значения = ON для legacy-профилей). Управляется в `/settings` (секция «Геймификация лекарств»).
2. **Positive-only:** при включённой настройке своевременный приём даёт XP (фикс, cap/день) и достижения `med_first`/`med_adherence_3/7/30`. При выключенной — приём фиксируется как обычно (MedIntake, напоминания), но **без XP, достижений и уведомлений о них**.
3. **Негативная геймификация здоровья запрещена безусловно:** пропуск/мисс никогда не отнимает баллы и не наказывается. Медицинский сигнал остаётся relief-only (открыть окно/смягчить/пауза/стоп).
4. **Документация обновлена:** docstrings `app/api/health.py`, `app/api/medication.py` уточнены (ранее «никакой игровой интеграции» противоречило фактическому коду); i18n RU/EN (4 ключа, паритет 1421/1421).
5. **Права:** настройка per-user (не глобальный флаг деплоя) — первый шаг к Agency-модели (R3) для домена medication; в перспективе гранулярные Capability (definition vs execution) вместо `scope_medication` (R4).

**Status:** ✅ Реализовано (prefs.py, gamification/medication.py, settings.py, settings.html, i18n, docstrings) + 3 новых теста (`TestMedicationGamificationToggle`). 18/18 medication+telegram, 58/58 settings+medication+health, икон-пак 6/6 ✅.
| ADR-138 | 2026-08-21 | R2.1–R2.3 / R10.2 (Flash-батч) | 1) `app/cli/seed_catalog.py`: парсинг 3 манифестов data/seed → activity_categories / activity_catalog_items / inventory_items; idempotent (slug для категорий, name+category для каталога, name+user для инвентаря); dry-run по умолчанию + `--apply` (ADR-105 gate). 2) `components/parameter_badges.html`: человекочитаемые чипы параметров (иконки timer/flame/target/tools из PracticeLoop icon pack) вместо `<pre>{{ params_schema | tojson }}</pre>` в catalog.html; поддержка ADR-041 list и legacy map. 3) `components/duration_picker.html` (5 полей + пресеты 10с..90с и т.д., режимы minmax/single) и `components/quantity_picker.html` (Мин/Макс/Цель + 7 единиц + пресеты) — задел под R2.5 персонализацию. 4) Вынос inline-JS из llm_exchange.html в `static/js/pages/llm_exchange.js` (CSRF из meta), allowlist S57 обновлён. InventoryItem остаётся user-scoped (нет is_system) — инвентарь сидится только с `--user-id`. | принято |
| ADR-139 | 2026-08-21 | R2.1–R2.3 (Flash-батч v2, уточнение промптов) | 1) `render_param_badges(params_schema)` — основной макрос parameter_badges.html (алиас `parameter_badges` сохранён); подключён в catalog.html (catalog_items.html не содержит params_schema — это универсальный каталог без параметров). 2) `duration_picker(field_name_prefix, default_seconds=0)` — 5 полей + пресеты 10с..30д (клик заполняет поля), default_seconds раскладывается по полям. 3) `quantity_picker(field_name_prefix)` — Мин/Макс-Цель + единицы (раз/ударов/подходов/мл/капель/шт/кг) + чипы 5..100. 4) `seed_catalog.py` расширен: читает ВСЕ 22 JSON из data/seed (cards из full_catalog+foundation+extensions+editorial, дедуп по slug → 194), создаёт системные Entity (owner_id=NULL, is_public=True, content_status по манифесту) + activity_catalog_items + inventory_items (--user-id). Idempotent проверен на sqlite. | принято |
| ADR-140 | 2026-08-21 | R5.3 (Flash №4) — UI протоколов | Созданы `app/api/protocols.py` (страницы /protocols, /new, /{id}/edit, /{id}/run + create/update/delete/start/complete-step; мутации через сервисы app/services/protocol.py, ActorContext owner_manual) и шаблоны `protocols.html` (список + активные раны), `protocol_builder.html` (шаги: тип, тайминг, offset, duration_picker; steps собираются в steps_json), `protocol_run.html` (интерактивный чеклист с прогрессом и завершением шагов). Nav-пункт «Протоколы» в base.html (Group 3). 39 i18n-ключей RU/EN (паритет 1491/1491). Полный цикл проверен тестом: create → edit → start → run → complete-step. protocol_builder.html добавлен в S57 inline-allowlist. R5.1 (модели) и R5.2 (реестр хендлеров) сделаны ранее про-моделью. | принято |
| ADR-141 | 2026-08-21 | R9/R10.1 (Flash №6–7) — удаление мёртвых шаблонов + навигация «5 разделов» | Flash №6: скан всех TemplateResponse/include/extends/macro-import/тестов подтвердил ровно 2 мёртвых шаблона — `app/templates/dashboard.html` (заменён dashboard_v2.html) и `app/templates/components/live_camera_observer.html`; удалены. Flash №7: навигация в base.html переструктурирована из 7 групп в 5 продуктовых разделов — «Сейчас/Сегодня» (dashboard, today, tasks, sessions, journal, points, locktimer), «План» (catalog, training, diets, quests, schedule, protocols), «Тело & Рутина» (health, care, aftercare, medication, measurements, inventory, body_parts, media, media_progress), «Связи» (D/s, сообщества, social, consent_matrix; секция по composition.social_operational с fallback на consent_matrix), «Система» (calendar, achievements, агент, аналитика, конструкторы, llm_exchange, ambient, locations, import). Новые i18n-ключи nav_group_plan/nav_group_body (RU/EN, паритет 1493/1493). Иконки: в пакет добавлены layers, shield-check, sliders (нужны параллельным agency.html/dynamics.html про-модели — икон-пак обновлён через tools/generate_icon_pack.py, 142 иконки). Мелочь: в protocol_builder.js/protocol_builder.html эмодзи-фолбэк ✕ заменён на plIcon('close')/текст — вынос inline-скрипта в .js делала про-модель. Смоук-тест навигации — tests/test_nav_restructure.py. | принято |
| ADR-142 | 2026-08-21 | R2.5 (Flash №8) — модальное окно персонализации карточки каталога | Реализовано `components/catalog_personalize_modal.html`: нативная `<dialog>`-модалка «Настроить» на каждой карточке каталога — длительность через `duration_picker` ×2 (мин/макс, поля в месяцах/днях/часах/минутах/секундах, JS собирает секунды в hidden `duration_min`/`duration_max`), повторения через `quantity_picker` (prefix `reps` → поля `reps_min`/`reps_max` напрямую в эндпоинт), селектор инвентаря и средств ухода (чекбоксы → hidden comma-строки), уровень желания, кастомное имя (Fork-on-Opt-In, ADR-106). Backend: `_personalize_hint()` в entities.py извлекает duration/reps-границы из params_schema (оба формата ADR-041; duration конвертируется в секунды с учётом unit) для префилла data-атрибутов; эндпоинт `POST /entities/{id}/personalize` расширен полем `assigned_inventory_ids` → сохраняется как типизированный параметр `inventory_ids = {type: inventory_selector, selection_mode: multiple, value: [...]}` (ADR-041). Контекст каталога обогащён `care_products`/`inventory_items` (мягкие ссылки, до 200, без archived). `parameter_badges` теперь join'ит list-значения вместо Python-синтаксиса. i18n: 17 ключей cpm_* RU/EN (паритет 1510/1510). Тесты: +3 в tests/test_catalog_personalize.py (inventory_ids, рендер модалки с префиллом 3–20 мин → 180–1200 с, чекбокс-группы инвентаря/ухода). | принято |
| ADR-143 | 2026-08-21 | R9.3 (Flash №9) — удаление мёртвого Python-кода и неиспользуемых импортов | Скан app/ (AST: модули без единого импорта, top-level defs без ссылок; ruff F401/F841/F811/F822/F823). Удалено 3 мёртвых модуля: `app/seed_v2.py` (устаревший сидер, ноль импортов; заменён app/seed.py + app/cli/seed_catalog.py), `app/schemas/auth.py` и `app/schemas/llm_config.py` (классы RegisterRequest/LLMConfigCreate нигде не используются; остальные schemas — живы). Удалены 6 мёртвых функций: `_entry_product_ids` (api/care.py), `_require_active_config` (api/prompt_templates.py — пустая заглушка), `_now_iso` (api/protocols.py), `_coerce_number` (gamification/dsl.py, + импорт Any), `_check_social_access` (platform/social/api/profile.py, + импорт SocialProfile), `_hmac_csrf` (security.py, + импорт hashlib). Починены F401: `is_valid_moderator_role` и `CommunityMemberRole` в api/communities.py; `select` в tests/test_community_governance.py; F841 `inc` + мёртвая `include_prefixes()` в scripts/audit_frontend_coverage.py. НЕ тронуты (параллельная работа про-модели): registry-импорты в app/models/__init__.py (нужны Alembic для 084–088) и JSONB в models/agency.py. Остаток F-ошибок: только эти 13 в файлах про-модели. Проверено: 1356 тестов коллектируются, 217 релевантных прошли. Отметку [x] в REFACTOR_ROADMAP_V2.md не ставил — файл параллельно переработан про-моделью (не коммичу чужую работу). | принято |
| ADR-144 | 2026-08-21 | R10.1 (Flash №10) — скрытие выключенных модулей в навигации по feature-флагам | Навигация `nav_groups()` в base.html (десктоп-сайдбар + мобильный drawer) теперь гейтит пункты теми же флагами `ProductComposition`, что и регистрация роутов в main.py: journal→journal_enabled, catalog→catalog_enabled, health→health_enabled, care→care_enabled, aftercare→aftercare_enabled, medication→medication_enabled, insights_analytics→insights_enabled, consent_matrix→consent_enabled (в обеих ветках «Связи»), locktimer→timer_operational, social→social_operational (уже было). Условие `{% if not composition or composition.X_enabled %}` — навигация не ломается при отсутствии контекста. `composition` уже инжектится во все шаблоны (templates_setup._composition_context). Группировка в 5 разделов сделана в Flash №7 (ADR-141); этот ADR закрывает вторую половину R10.1. Тесты: tests/test_nav_restructure.py +2 (скрытие выключенных модулей при medication/health/journal/consent_enabled=False; показ при дефолте). base.html закоммичен в чистой версии (HEAD + мой гейтинг) — параллельные добавления про-модели (nav_item dynamics/capabilities/agency, path-детекция, титулы) восстановлены в рабочем дереве, не коммитились. | принято |
| ADR-146 | 2026-08-21 | R10.5 (Flash №11) — полный pytest-прогон, ruff-чистка, memoryctl, документация | Полный прогон: **1356 passed, 2 failed** — обе в `tests/memory/test_vectors.py`: реальные `OMNIROUTE_*` из проекта протекали в `os.environ` теста, нарушая контракт «tmp-репо без конфига». Починено `monkeypatch.delenv` (теперь 13/13). ruff по всему репо: 113 ошибок → 69 автофикс (в т.ч. мои файлы) + 44 ручных. Добавлен per-file-ignore `alembic/versions/*.py = [E501]` в pyproject.toml (длинные RU/EN докстринги миграций — контент, не код; паттерн как у tools/adult_catalog_promote.py). Исправлены E501 в app/api/protocols.py (3 места — многострочные select), стиль в tests/test_nav_restructure.py и scripts/audit_frontend_coverage.py. НЕ тронуты 23 оставшиеся ruff-ошибки в незакоммиченных файлах про-модели (models/__init__.py registry F401 — нужны Alembic; UP042/E501 в models/agency|capability|dynamic|protocol.py). Документация: FUNCTIONAL.md + секции 57–60 (Protocol Engine R5, Community Governance, Agency & Capability, Навигация 5 разделов) — закоммичены только мои секции, чужие (37–56, README/CURRENT_STATE/PRODUCT) оставлены про-модели. memoryctl facts && lint — 0 ошибок. | принято |
| ADR-147 | 2026-08-21 | RC v1.0.0-rc1 — сводный аудит (Release Candidate Exit) | Сводный аудит после отчёта про-модели о готовности WIP (agency/capabilities/dynamics/protocol + миграции 084–088). **Все гейты зелёные:** полный pytest **1360 passed, 1 skipped**; **ruff 0 ошибок** (починены 25: 2 мои + 23 в файлах про-модели — UP042→enum.StrEnum в models/agency+protocol, E501-переносы в models/capability+dynamic+protocol+agency, 12 F401 в models/__init__.py закрыты через `__all__` = 43 имени — registry-импорты для Alembic остаются валидными); memoryctl facts+lint 0; i18n паритет 1510/1510; 116 шаблонов компилируются; S57+icon-pack+nav 29 passed; frontend-coverage: 88 страниц, 0 orphan-роутов; RC critical paths passed; prod-смоук SMOKE_OK; новые страницы /agency /capabilities /dynamics /protocols — 200/H1/валидные иконки. Прочее: `.playwright-mcp/` в .gitignore; roadmap R9.3/R10.1/R10.5 → [x]. Решение владельца: **один RC-коммит** всех 70 файлов (WIP про-модели + правки аудита + доки) с последующим деплоем. | принято |
| ADR-148 | 2026-08-23 | Редирект авторизованных с /register и /login на /dashboard | Квирк найден в E2E: CSRF применяется только при авторизованной сессии, а формы регистрации/логина не несут csrf_token → повторная регистрация/логин при залогиненной сессии давали 403 (молчаливая перерисовка формы). Исправление: GET и POST /auth/register и /auth/login принимают `Depends(get_optional_user)`; при авторизованном пользователе — 303 Redirect на /dashboard (все 4 роута), аккаунт не создаётся. Тесты: +4 в tests/test_auth.py (GET-редиректы обеих страниц, POST /auth/register не создаёт второй аккаунт, POST /auth/login без повторной авторизации). Всего 20 passed. | принято |
| ADR-149 | 2026-08-23 | csrf_token во всех нативных POST-формах (аудит auth-флоу) | Аудит страниц аутентификации в браузере (забытый пароль / смена пароля / logout) выявил: CSRF-middleware применяется только при авторизованной сессии, но 14 нативных POST-форм не несли hidden csrf_token (admin_ai_generator, admin_prompts ×4, agent_chat, discretion_bailout logout, insights_medical_exporter, insights_trajectory, persona_builder, quests claim, training_adaptive ×2, login, register) — сабмит для залогиненного давал 403 (нативный submit не шлёт X-CSRF-Token-заголовок, который добавляют fetch/htmx-обёртки app.js). Подтверждено в браузере на /discretion/bailout и /agent/chat (403). Фикс: hidden input `{{ csrf_token or '' }}` добавлен во все формы (context processor app/templates_setup.py даёт токен глобально; для авторизованных cookie всегда уже установлена). После фикса — 0 форм без токена, сабмиты bailout logout и agent chat работают (редирект вместо 403). Заодно проверены: смена пароля /settings/password (статусы invalid/length/mismatch/same/changed, редирект после смены, старый пароль → 401, новый → ок, ApiToken-инвалидация), logout через base (POST, куки сброшены), CSRF-гвард auth-страниц для авторизованных (ADR-148). Не реализовано: forgot/reset password (нет SMTP-инфраструктуры — только админский reset в admin.py); при добавлении email-доставки нужен флоу «забыли пароль». E2E 2 passed, 34 серверных passed. | принято |
| ADR-150 | 2026-08-23 | Редирект на /login с уведомлением при истёкшем токене | HTML-обработчик 401 (main.py http_exception_handler) редиректил на /auth/login — POST-only эндпоинт, GET даёт 405: браузер с протухшим JWT попадал на error-страницу, а битая кука оставалась (каждая защищённая страница вечно давала 401). Исправление: 303 → /login?session_expired=1 + delete_cookie(access_token) (кука сбрасывается, цикл 401 прерывается); login.html показывает переведённое уведомление (RU/EN login_session_expired, янтарный alert role="alert", иконка warning) с приоритетом над registered-уведомлением; JSON-клиенты (mobile/bearer) по-прежнему получают голый 401. Тесты: +2 в tests/test_auth.py (303 + location + set-cookie очистка; рендер уведомления). Проверено в браузере: битый токен → /login?session_expired=1, alert виден. 22 auth + 34 смежных passed. | принято |
| ADR-151 | 2026-08-23 | Enforcing CSP (nonce) + 5 иконок в пакет; закрытие Exit-гейтов R9/R10 | **CSP**: `Content-Security-Policy-Report-Only` → enforcing (ADR-151). Inline-скрипты (18 шаблонов, ~1300 строк) получили per-request nonce (secrets.token_urlsafe в security_headers_middleware ДО call_next; контекст-процессор `csp_nonce` в templates_setup). 60 inline-обработчиков в 36 шаблонах + 17 в JS-строках (innerHTML) мигрированы на data-action/data-change/data-input/data-confirm + делегаты в app.js (click/change/input/submit; `$this` в data-args → элемент; historyBack/copyImportUrl спец-кейсы). `script-src 'self' 'nonce-...'` без unsafe-inline; style-src оставлен unsafe-inline (Tailwind runtime). Обновлены тесты: test_audit_s57 (гейт: 0 inline-скриптов без nonce рекурсивно), test_audit_gatea (enforcing + nonce), test_catalog_personalize (data-action). Полный pytest **1366 passed**. **Иконки**: heat/cup/gift/journal/grid добавлены в пакет (147 иконок, генератор + svg/ + sprite синхронны), подключены: aftercare (Тёплый Компресс/Травяной Чай), quests (Забрать XP), nav «Журнал» (journal.svg вместо aftercare), insights_analytics (матрица → grid). **Гейты**: R9 Exit и R10 Exit в REFACTOR_ROADMAP_V2.md закрыты (R9 — чистый репозиторий; R10 — RC v1.0.0-rc1 готов, ADR-147). | принято |

### ADR-152: Real 2FA PIN with Session Cache (replaces simulation)

**Date:** 2026-08-24
**Status:** Accepted

Replaces the simulated PIN check (`pin_code == "1234" or len(pin_code) == 4`) with real bcrypt-hashed PIN stored in `users.pin_hash`, backed by an in-memory session cache (20-min TTL).

**Changes:**
- `users.pin_hash` column (String(255), nullable) — bcrypt hash of user's 4–16 digit PIN
- `POST /security/set-pin` — set initial PIN
- `POST /security/change-pin` — change PIN (requires current)
- `POST /security/clear-pin` — remove PIN (requires current)
- `POST /security/verify-pin` — real bcrypt check + cache TTL
- `GET /security/pin-status` — has_pin + session_cached flags
- In-memory `_PinCache` with 20-min TTL per user
- UI: PIN section in settings.html via HTMX fragment (`components/pin_form_fragment.html`)
- i18n keys EN/RU for all PIN operations
- 10 new tests in `tests/test_pin.py`, 1 updated legacy test
- Migration: `089_add_user_pin_hash`

### ADR-153: NotificationDispatcher channels are real (was stubs)

**Date:** 2026-08-24
**Status:** Accepted

Replaced the stub notification channels (`logger.info` + always `return True`) with real implementations:

| Channel | Before | After |
|---|---|---|
| InAppChannel | `logger.info` + True | Writes a `Notification` row into the `notifications` table (visible in /notifications) |
| TelegramBotChannel | `logger.info` + True | Calls `send_telegram_notification` from bot.py → real aiogram send to `user.telegram_chat_id`; returns False when no linked chat |
| EmailChannel | `logger.info` + True | Honest `logger.warning` + returns False (no SMTP infra) |
| PushChannel (new) | none | Calls `dispatch_push` from app/push/dispatcher.py → M4 push registry |

**Channel routing (default mode):**
- If `channels` is explicitly passed → use as-is
- Otherwise: `["in_app"]` always, + `"telegram"` if `user.telegram_chat_id` is set

**DMS worker** now actually delivers alerts (was silently dropping them).

**Reminders engine** already wrote real notifications (not affected).

### ADR-154: ActorContext in all mutation services (R8.1 completed)

**Date:** 2026-08-24
**Status:** Accepted

Added `ActorContext` (optional, defaults to `ActorContext(actor_id=user_id)`) to all application services with DB mutations, closing the R8.1 gap.

| Service | Functions | Audit storage |
|---|---|---|
| agency.py | set_user_agency_policy | `__audit__` key in constraints JSON |
| dead_mans_switch.py | record_activity_heartbeat | debug log |
| dynamic.py | create_dynamic_definition, start_dynamic_run, end_dynamic_run | `__audit__` key in frozen_dynamic_snapshot / agency_overlay JSON |
| scheduler.py | set_next_due, set_retry_block | debug log |
| notifications.py | dispatch_notification | `__audit__` key in payload → stored in Notification.body |

Read-only services (media, uploads, media_registry, personal_export, smart_albums, pharma_enricher, health, insights, payment_gateways) do not require ActorContext — they delegate to ORM or external APIs without mutating state.

### ADR-155: Protocol ↔ Timer bridge (R5.4 completed)

**Date:** 2026-08-24
**Status:** Accepted

Soft integration: timer-bound protocols are launched/aborted alongside timer session lifecycle events. No protocols = timer behaviour unchanged.

**Hooks:**
- `start_session` → `create_protocol_runs_for_timer_event(category="prep")` — prep protocols launch
- `safety_stop` → `complete_runs_for_timer_event()` aborts active runs → `create_protocol_runs_for_timer_event(category="recovery")` — recovery protocols launch

**Bridge functions** in `app/services/protocol.py`:
- `create_protocol_runs_for_timer_event()` — queries active timer_bound protocols by category, calls `start_protocol_run` for each
- `complete_runs_for_timer_event()` — marks active runs as aborted, pending steps as skipped

**UI:** `locktimer/session_detail.html` shows attached `protocol_runs` with status badges (active/completed/aborted), linked to `/protocols/run/{id}`.

## ADR-156 — Dashboard Refactor: Sessions Extraction + Module Gating

**Date:** 2026-08-24
**Decision:** Extract sessions from dashboard.py → app/api/sessions.py (616 lines). Gate all 7 dashboard summary blocks by `enabled_modules` from user prefs.

**Rationale:**
- dashboard.py was ~650 lines with sessions mixed in — hard to maintain
- Dashboard summary blocks (medication, health, journal, care, aftercare, insights, timer) were always rendered even if the module was disabled via `prefs.enabled_modules`
- No sessions → dashboard template had Jinja2 nesting bugs (orphan `</div>` outside `{% if enabled %}` checks, missing `{% endif %}` for outer if-elif chain)

**Changes:**
- Created `app/api/sessions.py` with all session CRUD + JSON API + interactive pages
- `app/api/dashboard.py`: removed sessions, simplified imports, added `enabled_modules` to template context
- `app/templates/dashboard_v2.html`: fixed nesting — moved `</div>` INSIDE `{% if 'module' in enabled_modules %}` for all 7 blocks, added closing `{% endif %}` for outer chain before `{% endfor %}`
- `app/main.py`: registers `sessions_router` + `sessions_json_router` from `app.api.sessions`

**Verification:** 1380 tests pass.

## ADR-157 — R1.2: Feature flags for draft models

**Date:** 2026-08-24
**Decision:** Added `experimental_leagues: bool = False` and `experimental_billing: bool = False` to `config.py`.

**Rationale:** The `UserLeagueTier` model and `Promocodes` model exist in the codebase but have no routes or active logic. The flags guard them for safe future rollout per ROADMAP R1.2.

## ADR-158 — R4.3: Protocol capability codes

**Date:** 2026-08-24
**Decision:** Added `_require_protocol_capability()` helper to `app/api/protocols.py` with `CapabilityAuthorizer.can_act()` checks on all mutation endpoints.

**Capability codes registered:**
- `protocol.create` — POST /protocols/create
- `protocol.edit_definition` — POST /protocols/{id}/update
- `protocol.delete` — POST /protocols/{id}/delete
- `protocol.start` — POST /protocols/{id}/start
- `protocol.confirm` — POST /protocols/runs/{id}/complete-step

**Owner always passes** (CapabilityAuthorizer returns True when actor_id == issuer_user_id). Delegated partners must have an active CapabilityGrantV2, D/s grant, SocialGrant, or CommunityMemberDelegation.

**Verification:** 1380 tests pass.

## ADR-160 — P7: Remove all legacy db.commit() from routers (ADR-015 debt closed)

**Date:** 2026-08-24
**Decision:** Remove all 70 `db.commit()` calls from 26 legacy router files in `app/api/`. Transactions are now exclusively owned by `get_db()` (auto-commit after endpoint).

**Changes:**
- Removed `await db.commit()` from 26 files (importers/*, points/*, core routers)
- Added `await db.flush()` in 7 files where `db.refresh()` needed the object to be persisted first (calendar, diets, references, attachments, verification, points/profiles)
- Added `await db.flush()` in `scheduler.py` service (`set_retry_block`) for same-session visibility
- `LEGACY_COMMIT_ROUTERS` in `test_transaction_boundary.py` set to empty set

**Verification:** 1380 tests pass, 0 `db.commit()` in `app/api/`, boundary test green.

## ADR-161: care.py → care_service.py (Service Layer Extraction)

**Статус:** принят, реализован.
**Контекст:** care.py (1417 строк) — монолит с бизнес-логикой, HTTP-парсингом и сериализацией в одном файле.

**Решение:**
- `app/services/care_service.py` (1161 строк) — вся бизнес-логика: CRUD, валидация, сериализация, Pydantic-модели
- `app/api/care.py` (478 строк, было 1417) — тонкие HTTP-обёртки: парсинг формы/JSON → вызов сервиса → ответ

**Паттерн:** каждый HTTP-хендлер — 3-10 строк: try → service call → except ValueError → redirect/JSON

**Рефакторинг其他大型 файлов (care.py -> care_service.py) — ADR-161.**

## ADR-162: medication.py → med_service.py (Service Layer Extraction)

**Статус:** принят, реализован.
**Контекст:** medication.py (1303 строк) — монолит с бизнес-логикой и HTTP-хендлерами.

**Решение:**
- `app/services/med_service.py` (1069 строк) — вся бизнес-логика: CRUD, расписания, приёмы, аптечки, экспорт, миграция
- `app/api/medication.py` (536 строк, было 1303) — тонкие HTTP-обёртки
- `app/services/errors.py` (7 строк) — `NotFoundError` для разделения 400/404

**Паттерн «thin routes»**: каждый хендлер 3-10 строк: try → service call → except → redirect/JSON

**Кросс-модульные импорты:** `_schedule_summary` переэкспортируется из `medication.py` → `med_service.schedule_summary`

## ADR-163: health.py → health_service.py (Service Layer Extraction)

**Статус:** принят, реализован.
**Контекст:** health.py (970 строк) — монолит с бизнес-логикой и HTTP-хендлерами.

**Решение:**
- `app/services/health_service.py` (770 строк) — cycle helpers, state/labs/cycle CRUD, LLM analysis, body-cycle
- `app/api/health.py` (385 строк, было 970) — тонкие HTTP-обёртки

**Кросс-модульные переэкспорты:** `_cycle_phase`, `_day_of_cycle`, `_get_cycle_context`, `_health_summary`
(используются в care_service, journal, today, dashboard, telegram, insights, tests)

## ADR-164: journal.py → journal_service.py (Service Layer Extraction)

**Статус:** принят, реализован.
**Контекст:** journal.py (1117 строк) — монолит с бизнес-логикой и HTTP-хендлерами.

**Решение:**
- `app/services/journal_service.py` (987 строк) — entries CRUD, partners, timer bridge, media, serializers, LLM
- `app/api/journal.py` (313 строк, было 1117) — тонкие HTTP-обёртки

**Кросс-модульные переэкспорты:** `ensure_timer_slot_entry`, `get_pending_slot_entry`, `journal_summary`
(используются в locktimer, today, dashboard, tests)

## ADR-165: entities.py → entities_service.py (Service Layer Extraction)

**Статус:** принят, реализован.
**Контекст:** entities.py (780 строк) — монолит с бизнес-логикой и HTTP-хендлерами.

**Решение:**
- `app/services/entities_service.py` (640 строк) — catalog/my pages, entity CRUD, opt-in, personalize fork
- `app/api/entities.py` (246 строк, было 780) — тонкие HTTP-обёртки

## ADR-166: training.py → training_service.py (Thin Routes)
- **Статус:** принят
- **Дата:** 2026-08-24
- **Контекст:** training.py 750 строк — монолит с бизнес-логикой, HTTP-хендлерами и вспомогательными функциями.
- **Решение:** Вынесены все CRUD, LLM-пайплайн, serializers, validators в `app/services/training_service.py` (597 строк).
  HTTP-хендлеры (299 строк) — только парсинг форм + вызов сервиса + ответ.
- **Последствия:**
  - `_render_log_entry_row` (UI-рендер) остался в training.py с re-export в тестах.
  - `complete_once()` требует User object — в service делается lookup User по user_id.
  - LLM-ошибки (JsonRepairError) ловятся broad `except Exception` → 303 redirect.
- **Коммит:** (pending)

## ADR-167: dashboard.py → dashboard_service.py (Thin Routes)
- **Статус:** принят
- **Дата:** 2026-08-24
- **Контекст:** dashboard.py 678 строк — монолит с контекстом дашборда (today tasks, diets, training, schedule, meals, sessions, locktimer, модульные summary, alerts), achievements, notifications, privacy, Telegram linking.
- **Решение:** Вынесены все queries, summaries, alerts, achievement CRUD, notification CRUD, TG code generation в `app/services/dashboard_service.py` (499 строк).
  HTTP-хендлеры в `app/api/dashboard.py` (223 строк, было 678) — тонкие обёртки.
- **Последствия:**
  - `_safe_summary()` загружает модульные summary через service-файлы (med_service, health_service, journal_service) напрямую, а не через route re-exports.
  - aftercare и insights ещё не декомпозированы — импортируются из api модулей.
- **Коммит:** (pending)

## ADR-168: insights.py → insights_service.py (Thin Routes)
- **Статус:** принят
- **Дата:** 2026-08-24
- **Контекст:** insights.py 635 строк — монолит с LLM-анализом, medical exporter, correlation matrix, report stats.
- **Решение:** Вынесены serializers, dashboard summary, LLM run execution, delete, medical exporter, correlation matrix, report stats в `app/services/insights_service.py` (341 строк).
  HTTP-хендлеры в `app/api/insights.py` (335 строк, было 635) — тонкие обёртки.
- **Последствия:**
  - `_insights_summary` re-export из insights_service для dashboard_service.
  - Лёгкие статические страницы (trajectory, report) без бизнес-логики остаются в routes.
- **Коммит:** (pending)

## ADR-169: sessions.py → sessions_service.py (Thin Routes)
- **Статус:** принят
- **Дата:** 2026-08-24
- **Контекст:** sessions.py 616 строк — монолит с CRUD, lifecycle, JSON API, interactive pages.
- **Решение:** Вынесены helpers (owned_session, record_event, serializer), page contexts, CRUD (create/accept/start/end), lifecycle (complete/interrupt live), task attach/detach, history в `app/services/sessions_service.py` (393 строки).
  HTTP-хендлеры в `app/api/sessions.py` (371 строк, было 616) — тонкие обёртки.
- **Последствия:**
  - `NotFoundError` (app/services/errors.py) используется для ownership check (→ 404).
  - `ValueError` используется для status conflicts (→ 409).
  - `create_session()` использует `**kwargs.pop("title", "Session")` для гибкости.
- **Коммит:** (pending)

## ADR-170: tasks.py → tasks_service.py (Thin Routes)
- **Статус:** принят
- **Дата:** 2026-08-24
- **Контекст:** tasks.py 513 строк — генерация задач (LLM + deterministic + weekly), ручное создание, complete/interrupt.
- **Решение:** Вынесены page context, LLM generation, deterministic fallback, weekly generation, manual task creation, entity lookup, complete/interrupt в `app/services/tasks_service.py` (377 строк).
  HTTP-хендлеры в `app/api/tasks.py` (229 строк, было 513) — тонкие обёртки.
- **Последствия:**
  - `NotFoundError` для entity not found (cross-user, params form) → 404.
  - `ValueError` для validation errors (no LLM, no practices) → redirect with error.
  - `coerce_param()` вынесен как переиспользуемый helper.
- **Коммит:** (pending)

## ADR-171: ds.py → ds_service.py (Thin Routes)
- **Статус:** принят
- **Дата:** 2026-08-24
- **Контекст:** ds.py 630 строк — D/s Suite: keyholder dashboard, portal, submissive CRUD, lock actions, duties, delegation (grants), check-ins, AI spin, TG code.
- **Решение:** Вынесены все queries, CRUD, lock actions, duty verification, delegation (create/claim/revoke grants), check-ins (OCR), AI spin, TG code generation в `app/services/ds_service.py` (442 строки).
  HTTP-хендлеры в `app/api/ds.py` (297 строк, было 630) — тонкие обёртки.
- **Последствия:**
  - `NotFoundError` для ownership checks (submissive, duty, grant) → 404.
  - `claim_grant_invite()` возвращает string result ('success'/'rate_limited'/'invalid'/'self_claim') вместо raises.
  - telegram-code endpoint возвращает redirect (303) на portal, не JSON.
- **Коммит:** (pending)
| ADR-172 | Service layer extraction: diets.py → diets_service.py (529→386 thin routes, 422 service) | thin routes | 2026-08-25 | 1fc7b628 | accepted |
| ADR-173 | Service layer extraction: prompt_templates.py → prompt_templates_service.py (505→307 thin routes, 350 service) | thin routes | 2026-08-25 | 085e9a85 | accepted |
| ADR-174 | Service layer extraction: import_data.py → import_data_service.py (493→148 thin routes, 422 service) | thin routes | 2026-08-25 | 8b5c3953 | accepted |
| ADR-175 | Service layer extraction: calendar.py → calendar_service.py (426→207 thin routes, 323 service) | thin routes | 2026-08-25 | f6a83229 | accepted |
| ADR-176 | Service layer extraction: protocols.py → protocols_service.py (404→230 thin routes, 360 service) | thin routes | 2026-08-25 | 1d5e74b6 | accepted |
| ADR-177 | P0: Onboarding wizard — 3-step flow (LLM config → modules → consent → dashboard) with skip; stored in user.prefs.onboarding_completed | feature | 2026-08-25 | 07421c75 | accepted |
| ADR-178 | Service layer extraction: communities/admin/catalog/community_agent/aftercare (5 files, ~1713 lines total) | thin routes | 2026-08-25 | 1d5e74b6 | accepted |

| ADR-180 | 2026-08-25 | Roadmap v0.9.1 → v1.1 (OCR→Social→Multi+D/s) | Зафиксирован трёхэтапный план в `ROADMAP_V1.md`: (1) v0.9.1 — OCR верификация (pytesseract + vision), 1–3 сессии, 1400+ тестов; (2) v1.0 — Social to Production (enablement, профили, фид, сообщества, модерация), 3–5 сессий, 1450+ тестов; (3) v1.1 — Multi-User & D/s Contour (partner linking, controller portal, delegation, OCR seal chain, keyholder timer), 3–5 сессий, 1500+ тестов. Детальный пошаговый план в `ROADMAP_V1.md` (5 разделов: A–D OCR, E–H Social, I–L Multi+D/s). Сознательно за v1.1: TOTP/Passkeys, Media CDN, public comment threads, Telegram social, mobile PWA, billing. | принято |
| ADR-183 | 2026-08-25 | v1.0 Stage I: public Vitrina + launch | Публичная витрина `/vitrina` (public_router, без авторизации): обезличенный топ участников (discoverable social profiles + реальные UserProgress XP/level/streak/compliance), последние достижения сообщества (is_hidden=false, рендер Anonymous), счётчики сообщества (профили/публикации/kudos). Email и user id не рендерятся. Ссылка с лендинга для анонимов. ADR-183 в docs/adr/. Этап I завершён: CI green (1397 тестов, ruff 0, memoryctl 0/0), тег v1.0.0. | принято |
