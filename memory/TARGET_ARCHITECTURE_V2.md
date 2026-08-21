# TARGET_ARCHITECTURE_V2 — Целевая архитектура (R0, 2026-08-21)

> Источник: `examples/PRACTICE_LOOP_RETHINK_REFACTOR_MASTER.md` (раздел 18-D).
> Цель: когерентные границы доменов, единый путь команд, опциональный AI, гранулярные способности.

## 1. Bounded contexts (целевые границы)

```text
identity/  preferences/  catalog/  activity/  sessions/  timer/  protocols/
training/  diet/  care/  medication/  health_state/  journal/  inventory/
media/  gamification/  insights/  agency/  relationships/  community/
billing/  notifications/  ai/
```

**Не всё сразу отдельными пакетами.** Инкрементально: сначала фиксируем направления зависимостей,
устраняем циклы, затем выносим сервисы по мере надобности.

## 2. Направления зависимостей (правило)

```text
UI/API  →  application services  →  domain services  →  ORM models (свой домен)
```

- Доменные модели импортируются **только** внутри своего домена и через сервисы/проекции наружу.
- Сейчас: 120 файлов импортируют `app.models.user` напрямую — целевой порядок: через
  identity-сервис или текущего пользователя из контекста запроса.
- Запрет циклических импортов (проверять `import-linter` или ручной dependency-graph).

## 3. Agency (модель данных — минимальная)

Предлагаемая минимальная персистентность (не проектировать сразу):

```python
class AgencyPolicy(Base):
    user_id: UUID
    domain: str            # sessions | timer | diet | training | care | protocols | insights ...
    level: str             # MANUAL | ANALYZE_ONLY | ASSISTED | PROPOSE_AND_CONFIRM | AUTOMATED_WITHIN_POLICY | DELEGATED_AI | DELEGATED_HUMAN
    constraints: JSONB     # границы (max_strictness, allowed_entities, daily_limit...)
    updated_at: datetime
```

Вопрос из брифа (раздел 23.5): **что персистить** — one user setting, per-domain policy,
per-Dynamic snapshot, комбинация. **Рекомендация:** per-domain policy (user_id, domain, level)
как источник истины; Dynamic-снапшот как оверлей на период. Manual = дефолт при отсутствии записи.

## 4. Capability (единый примитив делегирования)

Конвергенция 4 систем (SocialGrant, CapabilityGrant, CommunityMemberDelegation, CommunityMemberRole)
к единой модели-ядру (адаптер сверху, таблицы можно сохранить):

```python
class Capability(Base):   # целевое ядро (новые гранты)
    id, issuer_id, recipient_id, actor_type  # user | agent | community_role
    capability_code: str      # session.view / timer.extend / protocol.start / health.view_summary ...
    resource_scope: JSONB     # {community_id?, subject_id?, entity_ids?}
    constraints: JSONB        # {window?, max_per_day?, requires_confirm: true}
    valid_from, valid_until, state, accepted_at, revoked_at, metadata, audit
```

- **Definition vs Execution раздельно** — ключ для Medication/Protocol (см. PRODUCT_REFRAME §9).
- Миграция: adapter для CapabilityGrant.scope_medication → granular caps; старые фичи работают
  через compatibility path.

## 5. Protocol (модель + адаптеры)

Не мега-таблица. Предлагаемый минимальный каркас:

```python
class Protocol(Base):
    user_id, title, purpose, state, starts_at, schedule_json(optional)
class ProtocolStep(Base):
    protocol_id, seq, kind      # activity|medication|care_routine|diet_item|timer|journal|media|free
    ref_id (UUID, через адаптер), params_json, offset_or_time, requires_confirm
class ProtocolRun(Base):
    protocol_id, session_id?, timer_id?, started_at, finished_at, actor_source
class ProtocolStepLog(Base):
    run_id, step_id, status, actor_source, recorded_at
```

- Адаптеры: `ProtocolStepExecutor.execute(step, actor, context)`.
- Ссылки owner-scoped; удалённые ссылки — детерминированное поведение (warn + пропуск).
- CareCourse / MedicationSchedule / TrainingProgram — **не сливать**: сначала общая семантика,
  потом адаптеры Protocol поверх них (вопрос 23.3/23.4 брифа).

## 6. Dynamic (решение: составная проекция, НЕ обязательная модель)

**Рекомендация по брифу 23.9:** Dynamic = composition projection поверх существующих конфигов
(agency policies + persona + protocols + timer/session templates + grants), без обязательной
таблицы на старте. Если потребуется персистентность — одна таблица `dynamics` (title, purpose,
date_range, snapshot_json). Не становится обязательной обёрткой для старых данных.

## 7. AI proposal/apply pipeline (единый)

```text
Domain state/projection → Context Builder → AI request → Structured Proposal/Analysis
→ Validation → Optional confirmation → Existing application service → Audit
```

- Proposal state ≠ applied state (отдельные записи/флаги).
- Все мутации имеют actor+source (owner_manual, ai_proposal_confirmed, ai_automated,
  human_delegate, system_scheduler, admin).
- Persona меняет presentation/decision policy, не создаёт второй rules-engine.

## 8. Проекции/context providers

Интерфейсы только там, где реально снижают связанность:

```python
class HealthContextProvider:
    async def get_current_state(user_id, at) ...
    async def get_recovery_context(user_id, period) ...

class InventoryAvailabilityProvider:
    async def get_resources(user_id, ids) ...

class ProtocolStepExecutor:
    async def execute(step, actor, context) ...

class CapabilityAuthorizer:
    async def check(actor, capability, resource) ...
```

## 9. Каталог: целевая модель (ответ на 7.3 брифа)

**Entity vs activity_catalog — рекомендация:** activity_catalog становится системным каталогом-справочником
(типы/категории/шаблоны, is_public, owner NULL), а `entities` — пользовательскими экземплярами
(опт-ин, params, личный каталог) со ссылкой на catalog. Убрать дублирование полей:
переместить name/description/category в catalog, оставить в entity только user-specific (params,
opt-in, риск). Миграция аддитивная; UI-дублирование (catalog vs entities) — объединить в один
раздел навигации.

## 10. Миграционная стратегия

1. Не переписывать стабильные таблицы ради чистоты имён.
2. Аддитивные миграции; адаптеры при переносе концептов.
3. Сохранять ID (кросс-доменные ссылки).
4. JSON-схемы — в Pydantic/domain types.
5. DB-constraints для инвариантов, сейчас только в UI.
6. Каждая миграция тестируется на PostgreSQL, не только SQLite (S4).
7. Downgrade — не единственный recovery; backup перед деструктивными.

## 11. Запреты (anti-goals)

Не monolith «core»; не растворять Lock Timer; не делать AI обязательным; не делать D/s-роль
обязательной при онбординге; не удалять Diet/Medication/Health/Care; не создавать ещё одну
делегацию до конвергенции Capability; не выставлять automation/leagues/duels как production.
