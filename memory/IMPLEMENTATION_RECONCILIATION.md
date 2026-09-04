# IMPLEMENTATION_RECONCILIATION — Матрица примирения (R0, 2026-08-21)

> Источник: `examples/PRACTICE_LOOP_RETHINK_REFACTOR_MASTER.md` (раздел 18-B).
> Evidence-based: код + миграции + БД prod (134 таблицы) + 1334 теста + 543 роута.
> Обозначения: ✅ реализовано и проверено; ⚠️ частично/неполно; ❌ отсутствует/мёртвое.

## 0. Базовые факты репозитория

| Метрика | Значение |
|---|---|
| Ветка / HEAD | `main` @ `98759c21` (memory ADR-135) |
| Несогласованные док-файлы | CURRENT_STATE/FUNCTIONAL/PRODUCT/PRODUCT_DECISIONS/PRODUCT_VISION/README/ROADMAP (правки владельца, не закоммичены) |
| Модели (`__tablename__`) | 133 (118 в app/models + 15 в app/platform/social/models.py) |
| Таблицы в БД prod | 134 (включая alembic_version) |
| Модель без таблицы | **0** |
| Таблица без модели | **0** |
| Миграции | 83 файла, prod на head `083_community_membership` |
| Роуты | 543 (206 `/api`, 36 social, 20 communities, 19 admin, …) |
| Шаблоны | 108 (88 app/templates/*.html + компоненты) |
| Тесты | 1334 collected, **1332 passed**, 1 skipped, 2 failed (test-инфраструктура: реальный `.env` перекрывает tmp_path — не код) |
| БД prod: entities | 194 (все system/one_time) |
| БД prod: activity_catalog | 25 (все system) |

## 1. Модели, заявленные в FUNCTIONAL.md как «без миграций» — ПРОВЕРЕНО

FUNCTIONAL.md §6.1 декларировал 17+ таблиц как «models declared without migrations».
По факту миграции **добавлены** (082/083 и др.), prod на head, все таблицы существуют:

| Таблица | Модель | Миграция | Роут | UI | Тест | Статус |
|---|---|---|---|---|---|---|
| subscription_tiers | ✅ | 082 | `/api/v2/admin/tiers` | admin_tiers | ⚠️ | ✅ schema, биллинг частичный |
| tier_feature_grants | ✅ | 082 | там же | там же | ⚠️ | ✅ schema |
| temporary_feature_promotions | ✅ | 082 | там же | там же | ⚠️ | ✅ schema |
| payment_invoices | ✅ | 082 | `/api/v2/billing` | billing.html | ⚠️ | ✅ schema, showcase |
| promo_codes | ✅ | 082 | `/api/v2/promocodes` | promocodes | ⚠️ | ✅ schema |
| communities | ✅ | 082+083 | 20 роутов | community_list/detail | ✅ 21 | ✅ полно |
| community_posts | ✅ | 082+083 | community_agent | там же | ✅ | ✅ |
| community_top_agents | ✅ | 082+083 | там же | там же | ✅ | ✅ |
| community_member_delegations | ✅ | 082+083 | там же | там же | ✅ | ✅ |
| community_tournaments(+entries) | ✅ | 082+083 | там же | там же | ✅ | ✅ |
| community_member_roles | ✅ | 082+083 | `/moderators/*` | detail | ✅ 8 | ✅ полно |
| automation_triggers | ✅ | 082 | ❌ **нет роутов** | ❌ | ❌ | ⚠️ **мёртвая модель** |
| one_time_media_tokens | ✅ | 082 | media_vault_v2/media_exposure | media | ⚠️ | ✅ |
| user_agent_personas | ✅ | 082 | persona-builder | agent_chat | ⚠️ | ✅ |
| user_league_tiers | ✅ | 082 | ❌ **нет роутов** | ❌ | ❌ | ⚠️ **мёртвая модель** |
| user_duels | ✅ | 082 | ❌ **нет роутов** | ❌ | ❌ | ⚠️ **мёртвая модель** |

## 2. Статусы модулей (матрица зрелости)

### CORE_STABLE (работает без AI/партнёра)
| Модуль | Модель | Миграция | API/SSR | UI | Тест | Замечание |
|---|---|---|---|---|---|---|
| auth/identity | users | 001 | auth.py | login/register | ✅ | JWT cookie |
| каталог задач | entities | 002+ | entities/catalog | catalog | ✅ | 194 system-entity |
| сессии | activity_sessions | 003+ | sessions | sessions_* | ✅ | +history |
| таймер | lock_* | 025/026 | locktimer | locktimer | ✅ | bounded context |
| тренировки | training_* | 005/015 | training | training | ✅ | |
| диеты | diets+ | 018–020 | diets | diets | ✅ | |
| лекарства | medications+ | 041–043 | medication | medications | ✅ | +ERP 065 |
| здоровье | health_* | 044 | health | health | ✅ | relief-only |
| журнал | sj_entries | 045/046 | journal | journal | ✅ | relief-only |
| уход | care_* | 047–053 | care | care | ✅ | |
| замеры/инвентарь | body_measurements/inventory | 023/064 | v2 | v2 pages | ✅ | |
| календарь | calendar_* | 007/011 | calendar | calendar | ✅ | |
| медиа | media_assets | 027/037 | media | media | ✅ | |
| напоминания | reminder_log | 052 | reminders | reminders | ✅ | scheduler |
| инсайты | insight_* | 050 | insights | insights | ✅ | |

### BETA (нужно хардненить)
| Модуль | Статус | Замечание |
|---|---|---|
| social (36 роутов) | ⚠️ | Tracker adapter реализован; TimerSocialAdapter поддерживает ownership/read projection/verify, write actions остаются вне scope |
| D/s делегирование | ⚠️ | CapabilityGrant ✅, scope_medication слишком грубый |
| зашифрованные медиа | ⚠️ | media_vault_v2, one_time_tokens |
| адаптивные программы | ⚠️ | adaptive_programs, LLM-адаптация |
| аналитика v2 | ⚠️ | insights_analytics + correlations |
| квесты | ⚠️ | quests/user_quests, 072 |

### EXPERIMENTAL / НЕПОЛНОЕ
| Модуль | Статус | Замечание |
|---|---|---|
| community + agent | ✅ полно (после 083) | но турниры без e2e-монетизации |
| **automation_triggers** | ❌ мёртвое | модель+таблица есть, **API/UI/тестов нет** |
| **leagues/duels** | ❌ мёртвое | user_league_tiers/user_duels: модель+таблица есть, **API/UI/тестов нет** |
| billing | ⚠️ showcase | роуты есть, реальных платежей нет, monetization_enabled=False |
| сертификаты | ⚠️ | публичная верификация, без UI-точки входа |
| 2FA PIN Shield | ⚠️ stub | минимальный PIN, полный TOTP — roadmap |
| voice TTS | ⚠️ stub | payload/logging |
| voice STT | ⚠️ | эвристика, LLM-fallback зарезервирован |
| Telegram Broadcast | ⚠️ | payload/logging stub |

## 3. Подтверждённые пропуски реализации (FUNCTIONAL.md §6.2)

| Пропуск | Проверено | Действие |
|---|---|---|
| TimerSocialAdapter write actions | ⚠️ `app/platform/social/adapters.py` реализует ownership, redacted projection и verify-capabilities; `execute_authorized_action` пока возвращает `not_implemented` | Отдельное решение и action-контракт для Social write operations |
| 2FA PIN Shield — минимальный stub | ✅ `app/api/security_2fa.py` | keep roadmap |
| TTS — payload/logging stub | ✅ `app/telegram/voice_tts.py` | keep roadmap / флаг |
| STT — эвристика | ✅ | keep roadmap |
| LockSession `validating`/`cancelled_by_system` зарезервированы | ✅ | не трогать |
| OCR/LLM-верификация seal/media реализована; OCR кодов лекарств не входит в текущий контур | ✅ | ADR-181 + P11 |
| Password recovery не реализовано | ✅ нет роута | roadmap |
| Verified email change не реализовано | ✅ | roadmap |
| Invitations не реализованы | ✅ | roadmap |
| Admin audit trail отдельный — нет | ✅ | P1 |
| Starter catalog: legacy reset был `entities=0`, затем каталог импортирован заново | ✅ | PLAN.md S8a/P1: 41 approved entity в актуальном production-состоянии |
| Billing/community/automation e2e | ⚠️ | community ✅; billing showcase; automation мёртвое |

## 4. Подтверждённые противоречия документ ↔ код

### 4.1. Medication `relief-only` vs XP (FUNCTIONAL.md §7.1)
- `app/api/health.py`, `app/api/journal.py` — декларируют relief-only, no gamification (PD-013).
- `app/telegram/bot.py:1136/1207` — `/med` вызывает `on_medication_taken` → **adherence XP + achievements**.
- **Конфликт подтверждён.** Требуется решение: запрет домена / опция / generic-политика.

### 4.2. Entity vs activity_catalog (FUNCTIONAL.md §7.3)
- `entities` (194, system) + `entities.activity_catalog_id` FK (SET NULL) на `activity_catalog` (25, system).
- Перекрытие полей (name/real_name, categories, tags, owner/publication). **Дублирование подтверждено.**
- Требуется target-модель до миграций (см. TARGET_ARCHITECTURE_V2).

### 4.3. SocialGrant vs CapabilityGrant (FUNCTIONAL.md §7.5)
- `social_grants` (subject-based) + `capability_grants` (D/s) + `community_member_delegations` + `community_member_roles`.
- **4 системы делегирования.** Нужен общий словарь (см. Capability в TARGET_ARCHITECTURE_V2).

### 4.4. Feature flags vs user composition (FUNCTIONAL.md §7.6)
- Deployment flags в `app/config.py` (locktimer_core_enabled, social_enabled…) vs
  user prefs (`user_prefs`, consent_records) — используются оба, различие не формализовано.

## 5. Связанность / дублирование (аудит)

- **Кросс-доменный ORM-импорт:** 120 файлов импортируют `app.models.user`, 41 `activity_log`, 29 `care`, 26 `locktimer`, 24 `entity` — прямые обращения к чужим моделям повсеместны.
- **JSON-колонки:** 3 `JSON().with_variant(JSONB)` (entity params_schema, session rules, grants) — скрытые схемы.
- **Schedulers:** 3 отдельных (app/services/scheduler.py, app/reminders/scheduler.py, app/training/scheduler.py) + auto-analysis + timer jobs — единой job-модели нет.
- **Крупные роутеры:** dashboard 1464, care 1427, medication 1299, journal 1117 строк — логика в роутерах.
- **Telegram bot:** 1811 строк — бизнес-логика в хендлерах.
- **D/s duplication:** `CapabilityGrant` vs `SocialGrant` vs `CommunityMemberDelegation`.

## 6. Рекомендованные целевые статусы

| Модуль | Текущий | Целевой |
|---|---|---|
| identity, catalog, sessions, timer, training, diet, med, health, journal, care, inventory, calendar, media, reminders, insights, measurements | Core | CORE_STABLE |
| social, D/s, encrypted media, adaptive, analytics v2, quests | Beta | BETA (hardening) |
| community+agent, tournaments | ✅ работает | BETA (e2e-монетизация позже) |
| automation_triggers, leagues, duels | мёртвые | **disable** до реализации ИЛИ удалить |
| billing | showcase | EXPERIMENTAL (монетизация=False) |
| 2FA, TTS, STT, broadcast | stub | EXPERIMENTAL (флаг) |
