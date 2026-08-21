# REFACTOR_ROADMAP_V2 — Исполняемая дорожная карта рефакторинга (R0, 2026-08-21)

> Источник: `examples/PRACTICE_LOOP_RETHINK_REFACTOR_MASTER.md` (раздел 18-E, 19).
> Фазы с exit criteria. Нет фазы «переписать всё».

## R0 — Repository reconciliation ✅ (этот аудит)

- [x] Git state: main @ 98759c21, 7 некоммиченных док-файлов владельца
- [x] Тесты: 1332/1334 passed (2 — тест-инфраструктура, S2)
- [x] Миграции: 83, prod head 083; модели↔таблицы: 0/0 расхождений
- [x] Матрица зрелости: 134 таблицы, 543 роута
- [x] Подтверждены пропуски: TimerSocialAdapter скелет, automation/leagues/duels мёртвые, billing showcase, 2FA/TTS/STT stubs
- [x] Противоречия: medication relief-only vs XP; Entity vs activity_catalog; 4 системы делегирования
- [ ] **Exit:** закоммитить 7 док-файлов владельца (или согласовать); зафиксировать 2 failed теста

## R1 — Schema completeness (ближайшая)

- [ ] **P0-1:** пометить/отключить мёртвые модели (automation_triggers, user_league_tiers, user_duels)
      за feature-флагом ИЛИ удалить таблицы миграцией 084 (рекомендация: флаг `experimental_leagues=False`,
      дефолт выключен — не плодить удаление данных)
- [ ] **P1-1:** починить 2 теста test_vectors (monkeypatch .env чтения вместо реального файла)
- [ ] **P1-2:** добавить тест чистой PostgreSQL-миграции (upgrade head на пустой БД) в CI-скрипт
- [ ] Exit: `alembic upgrade head` на чистом PG; приложение стартует со всеми включёнными интент-модулями;
      матрица покрытия миграций полная (уже: 0 моделей без таблиц)

## R2 — Product composition & feature states

- [ ] Формализовать статусы (CORE_STABLE/BETA/EXPERIMENTAL/STUB/DISABLED) в конфиге/доке
- [ ] Выровнять deployment flags (config.py) vs user composition (user_prefs/consent)
- [ ] Скрыть/пометить неполные страницы: billing (EXPERIMENTAL), 2FA/TTS/STT (STUB)
- [ ] Навигация по составу: Today/Plan/Personal/Review/Connections/System (бриф §13) — сначала
      wire-level IA, валидация существующего использования
- [ ] Exit: неполные фичи не выглядят production-ready; доступность модулей детерминирована и тестируется

## R3 — Agency foundation

- [ ] Маппинг существующих LLM/manual/delegated флоу (session, timer, diet, training)
- [ ] Модель `AgencyPolicy` (user_id, domain, level, constraints) + API/UI-настройки
- [ ] AI-пропозалы маршрутизируются через существующие application services (не параллельный домен)
- [ ] Exit: session и timer демонстрируют общую Agency-семантику; manual-флоу не изменены;
      тесты доказывают: AI опционален

## R4 — Capability convergence

- [ ] Сравнить SocialGrant / CapabilityGrant / CommunityMemberDelegation / CommunityMemberRole
- [ ] Общий словарь capability_code (session.view, timer.extend, protocol.start…)
- [ ] Adapter/migration path: старые фичи через compatibility; новые гранты — целевая модель
- [ ] Гранулярные medication/protocol caps вместо `scope_medication`
- [ ] Exit: одна документированная модель способностей; старые фичи работают; revoke распространяется консистентно

## R5 — Protocol foundation

- [ ] Анализ CareCourse/MedicationSchedule/Training/AdaptiveProgram/Diet/Timer rules — общая семантика
- [ ] Модель Protocol + ProtocolStep + Run + StepLog (см. TARGET_ARCHITECTURE_V2 §5)
- [ ] Адаптеры шагов (activity/medication/care/diet/timer/journal/media/free)
- [ ] Manual protocol builder + Session/Timer binding + reminders/execution log
- [ ] AI-пропозал протокола — только после работы manual
- [ ] Exit: пользователь создаёт и запускает протокол с полностью выключенным AI;
      Medication/Care и пр. продолжают работать; нет дублирующего scheduler-движка без обоснования

## R6 — Dynamic / orchestration

- [ ] Решение: персистентная модель или composition projection (рекомендация: проекция, §6 TARGET)
- [ ] Биндинг Agency + Persona + protocols + timer/session templates + grants
- [ ] «Active dynamic» dashboard
- [ ] Exit: Dynamic снижает фрагментацию UX; не обязательная обёртка; manual-пользователи игнорируют

## R7 — AI/persona/automation consolidation

- [ ] Persona использует Agency/capabilities (не второй rules-engine)
- [ ] Automation triggers — **реализовать или отключить** (сейчас мёртвые)
- [ ] LLM Exchange → proposal pipeline; adaptive training → target services
- [ ] Каждая мутация: actor + source + audit
- [ ] Exit: ни одна AI-подсистема не мутирует домен через unique bypass

## R8 — Human/social/community integration

- [ ] Реализовать TimerSocialAdapter (через Capability-ядро)
- [ ] Миграция D/s grants; community roles/delegation — shared capabilities
- [ ] Изоляция publication projection
- [ ] Exit: personal core изолирован; человеческий контроль capability-scoped; revoke консистентен

## R9 — Production hardening & release candidate

- [ ] E2E critical flows; concurrency; PostgreSQL; backup/restore
- [ ] Feature flag matrix; API/mobile parity; logging/metrics
- [ ] Scheduler/outbox durability (конвергенция 3 scheduler-систем)
- [ ] Billing — только если полностью реализован (иначе EXPERIMENTAL)
- [ ] Smoke suite (scripts/prod_smoke.sh расширить)
- [ ] Exit: воспроизводимый clean deploy и upgrade; документированная зрелость модулей; нет stubs как production

## Порядок первого безопасного батча (после этого аудита)

1. **R1-P0-1** — feature-flag для мёртвых моделей (без удаления данных)
2. **R1-P1-1** — починить 2 теста (инфраструктура)
3. **R2** — статусы фич + пометка EXPERIMENTAL в UI (billing/2FA/TTS)
4. **R3** — AgencyPolicy (только чтение/настройки, без изменения флоу)
5. **R5** — Protocol manual builder (без AI) — самая крупная продуктовая ценность из брифа

## Риски (бриф §9)

- Lock Timer — не растворять (инвариант 22.5)
- Medication XP — не удалять молча (противоречие D3 требует явного решения)
- Entity vs activity_catalog — не мигрировать без target-модели
- Мёртвые модели — не удалять данные без backup-стратегии (миграция 16.9)
- Billing — не обещать реальные платежи
- 7 некоммиченных док-файлов — согласовать с владельцем перед коммитом (R0 exit)
