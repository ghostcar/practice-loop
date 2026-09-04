# TECH_DEBT_V2 — Реестр технического долга (R0, 2026-08-21)

> Источник: `examples/PRACTICE_LOOP_RETHINK_REFACTOR_MASTER.md` (раздел 18-C).
> Каждая позиция: приоритет | evidence | влияние | цель | зависимости.

## 1. Схема/миграции

| # | Долг | Приоритет | Evidence | Влияние |
|---|---|---|---|---|
| S1 | 3 модели без API (automation_triggers, user_league_tiers, user_duels) — таблицы созданы 082 | ~~P0~~ ✅ | **Закрыто (ADR-186, 2026-09-04): удалены** миграцией 094 (таблицы пусты в production), модели/agent-движки и их тесты удалены; agent-логика была прототипной, automation-штрафы конфликтовали с «без авто-эскалации» (ADR-106). Восстановление — из git-истории |
| S2 | 2 failed теста — тест-инфраструктура (.env перекрывает tmp_path) | P1 | `tests/memory/test_vectors.py:95` | Слепое пятно в CI |
| S3 | JSONB-колонки как скрытые схемы (params_schema, rules, grants) | P2 | 3 `JSON().with_variant(JSONB)` | Нет валидации/миграций контракта |
| S4 | Миграции не тестируются на чистом PostgreSQL (только SQLite) | P1 | тесты на SQLite в conftest | Риск деплоя (пройдено вручную 083) |
| S5 | Soft-ID ссылки (activity_catalog_id SET NULL и т.п.) без cleanup-семантики | P2 | `app/models/entity.py:39` | Осиротевшие строки |

## 2. Stubs / неполная реализация

| # | Долг | Приоритет | Evidence |
|---|---|---|---|
| I1 | TimerSocialAdapter: write-action execution не реализован | P1 | `app/platform/social/adapters.py`: ownership/read projection/verify реализованы, `execute_authorized_action` возвращает `not_implemented` |
| I2 | 2FA PIN Shield — минимальный, полный TOTP в roadmap | P2 | `app/api/security_2fa.py` |
| I3 | TTS — payload/logging stub | P2 | `app/telegram/voice_tts.py` |
| I4 | STT — эвристика, LLM-fallback зарезервирован | P2 | `app/agent/voice_hydration.py` |
| I5 | Telegram Broadcast — payload/logging stub | P2 | bot.py |
| I6 | Password recovery / verified email change / invitations / admin audit — отсутствуют | P1 | нет роутов |
| I7 | OCR-верификация кодов лекарств — отдельная интеграция не реализована | P3 | ADR-181 покрывает seal/media OCR; medication-specific OCR route отсутствует |
| I8 | Billing — showcase (monetization_enabled=False, нет реальных платежей) | P2 | `app/api/billing.py` |

## 3. Дублированные концепты

| # | Долг | Приоритет | Evidence |
|---|---|---|---|
| D1 | Entity vs activity_catalog (два каталога, FK между ними) | P1 | `entities` 194 + `activity_catalog` 25 |
| D2 | 4 системы делегирования: SocialGrant, CapabilityGrant, CommunityMemberDelegation, CommunityMemberRole | P1 | models social + ds_suite + community |
| D3 | Medication relief-only vs adherence XP — **решено ADR-137** (prefs.med_gamification, default ON, positive-only) | ~~P1~~ ✅ | `app/prefs.py`, `app/gamification/medication.py` |
| D4 | CareCourse/MedicationSchedule/Training/AdaptiveProgram/Diet/ScheduleRule/LockTaskRule — кандидаты под Protocol | P2 | 7+ моделей с похожей семантикой последовательностей |
| D5 | Feature flag vs user composition vs agency — один boolean на 4 смысла | P1 | config.py flags vs user_prefs |

## 4. Кросс-доменная связанность

| # | Долг | Приоритет | Evidence |
|---|---|---|---|
| C1 | 120 файлов импортируют User, 41 activity_log, 29 care — прямой ORM между доменами | P2 | grep `from app.models.` |
| C2 | Бизнес-логика в роутерах: 16 файлов ✅ | Partial | 16 файлов вынесены в services (ADR-161..176) |
| C3 | Telegram bot 1811 строк — логика в хендлерах | P1 | `app/telegram/bot.py` |
| C4 | 3 scheduler-системы (services/reminders/training) без единой job-модели | P2 | app/services, app/reminders, app/training |
| C5 | Дублирование owner-checks и timezone-логики | P2 | повсеместно |

## 5. API/mobile parity

| # | Долг | Приоритет | Evidence |
|---|---|---|---|
| M1 | Bearer-аутентификация есть в ~5 роутерах; полный JSON-parity не выверен | P2 | grep bearer |
| M2 | Часть страниц SSR без JSON-эквивалента | P2 | audit_frontend_coverage.py |

## 6. UX/композиция

| # | Долг | Приоритет | Evidence |
|---|---|---|---|
| U1 | Навигация показывает все модули, а не composition | P1 | base.html sidebar 7 групп |
| U2 | Нет Agency-настроек, Protocol UX, manual-first onboarding | P2 | PRODUCT_REFRAME §4–5 |
| U3 | Экспериментальные фичи не помечены | P2 | нет status-бейджей |

## 7. Docs drift

| # | Долг | Приоритет | Evidence |
|---|---|---|---|
| V1 | Закрыт: FUNCTIONAL.md больше не утверждает `entities=0` как текущее состояние | — | PLAN.md фиксирует исторический reset и последующий импорт 41 approved entity |
| V2 | Закрыт: документационные изменения проходят отдельными memory-коммитами | — | git status и memoryctl facts |
| V3 | Закрыт ADR-137: medication/health/journal границы и положительное adherence-XP разделены явно | — | `app/gamification/medication.py`, ADR-137 |
