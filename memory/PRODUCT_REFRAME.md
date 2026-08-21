# PRODUCT_REFRAME — Рекомпозиция продукта (Master Brief 2026-08-21)

> Источник: `examples/PRACTICE_LOOP_RETHINK_REFACTOR_MASTER.md` (раздел 18-A).
> Статус: рабочий документ, создан по итогам R0-аудита (см. `IMPLEMENTATION_RECONCILIATION.md`).

## 1. Текущее определение продукта

> **Пользователь-центричная (personal-first), kink-aware операционная система для активностей,
> сессий, таймеров, рутин, подготовки, личных протоколов, трекинга и рефлексии — с опциональными
> слоями AI-помощи, виртуальных динамик и доверенного человеческого делегирования.**

Продукт вырос из личного трекера активностей с Lock Timer в платформу из ~90 модулей.
Рекомпозиция — не «добавить ещё фич», а примирить реальную систему и сделать основу когерентной.

## 2. Четыре слоя продукта

| Слой | Название | Что входит | Требование |
|---|---|---|---|
| **A** | Personal Core | Каталог, задачи, сессии, таймеры, расписание, журнал, уход, диеты, тренировки, лекарства, здоровье, замеры, инвентарь, медиа, напоминания, история, импорт/экспорт | Работает полностью без AI и без другого человека |
| **B** | Intelligence | Пропозалы задач/сессий/таймеров, генерация диет, анализ тренировок, адаптивные программы, инсайты, корреляции, саммари, медиа-тегирование, LLM Exchange | Опционально; по умолчанию — анализ/предложения, не автономные действия |
| **C** | Virtual Dynamics | Персоны, делегированные AI-действия, скрытые задачи, последствия, квесты, виртуальный кихолдинг, правила/триггеры | Оверлей над Core, не замена |
| **D** | Human/Social | Отношения, шеринг, публикации, верификация, гранты способностей, портал кихолдера, D/s, сообщества | Строится на гранулярных способностях, не на ролях страниц |

## 3. Manual-first принцип

Базовый режим — ручной. Пользователь должен мочь (без AI/социалки/партнёра):

- создать каталог активностей и отметить допустимые;
- вручную собрать сессию;
- вручную настроить и запустить таймер;
- создать и вести план тренировок и диету;
- вести уход, лекарства/БАДы, инвентарь;
- записывать состояние, замеры, журнал, медиа;
- смотреть историю и статистику.

Это не fallback — это фундамент.

## 4. AI — прогрессивный и опциональный

Прогрессия: Manual → Analyze → Assist → Propose → Automate → Persona → Human delegation.
Пользователь может остаться на любом уровне. Нет архитектурного допущения, что все «прогрессируют»
к AI-власти или человеческому делегированию.

## 5. Agency (кто может решать/выполнять)

Не один глобальный уровень, а конфигурация по домену/способности:

```text
MANUAL | ANALYZE_ONLY | ASSISTED | PROPOSE_AND_CONFIRM | AUTOMATED_WITHIN_POLICY | DELEGATED_AI | DELEGATED_HUMAN
```

Пример: sessions=MANUAL, timer=PROPOSE_AND_CONFIRM, diet=ASSISTED, training=AUTOMATED_WITHIN_POLICY,
care=MANUAL, protocols=DELEGATED_HUMAN, insights=ANALYZE_ONLY.
В коде уже есть фрагменты: ручное создание, детерминированная генерация, LLM-генерация,
LockTimer LLM-пропозалы, SocialGrant, CapabilityGrant, AI-персона, automation-триггеры.
Цель — не реализовывать Agency отдельно в каждом модуле.

## 6. Protocol (переиспользуемая последовательность)

Protocol ≠ Activity/Session/Diet/MedicationSchedule/CareCourse/TrainingProgram.
Это переиспользуемая упорядоченная или по расписанию последовательность шагов и правил:

- Preparation Protocol (T-24h → T-12h → T-2h → T → T+1h → T+12h);
- Daily Protocol (08:00 → item A, 20:00 → item B);
- Care Protocol (clean → product A → wait → product B → log).

Шаги могут ссылаться: Activity/Entity, препарат/БАД/расходник, Care-рутина, диета, таймер-действие,
журнал/чек-ин, медиа/отчёт, свободное действие. Protocol может быть ручным, повторяющимся,
привязанным к сессии/таймеру, AI-предложенным, подтверждённым, авто-запущенным по правилам,
частично делегированным.

**Важно:** не сливать все таблицы в одну мега-таблицу. Сначала абстракция + адаптеры; миграции инкрементальны.

## 7. Dynamic (оркестрация)

High-level контейнер, не обязательно D/s-объект: title, purpose, даты, персона (опц.), agency-матрица,
допустимый поднабор каталога, правила, профиль последствий, политика отчётов/таймеров, протоколы,
AI-поведение, человеческие гранты, тон уведомлений, состав фич. Примеры: self-directed routine,
personal challenge, virtual submission, strict keyholder, training block, human-guided dynamic.

Не реализовывать, пока не mapped overlap с ActivitySession, LockSession, persona, grants.

## 8. Capability (единый примитив делегирования)

Сейчас минимум две системы: Platform Social grants и D/s CapabilityGrant (+ community delegation/roles).
Цель — сойтись к одному примитиву авторизации: issuer, recipient/actor, capability_code,
resource_scope, constraints, valid_from/until, state, accepted/revoked_at, metadata, audit.

Примеры: session.view/propose/manage; task.view/propose/verify; timer.view/propose/extend/open_slot/verify;
protocol.view/start/pause/reschedule_within_window/request_confirmation/edit_definition;
inventory.view/manage; health.view_summary; media.request/view/verify.
Не моделировать широкий контроль как один boolean `scope_medication`.

## 9. Интерпретация «generic»-модулей

Medication/Diet/Care/Health/Inventory — НЕ удалять и не принижать. Они питают цикл
PLAN → EXECUTE → OBSERVE → ADAPT. Health/State — кросс-доменный контекст-провайдер через
стабильные проекции (current_state, recent_state, cycle_context, recovery_context, selected_metrics),
а не прямое чтение таблиц из каждого модуля. Inventory — общий реестр ресурсов.

**Definition vs Execution — раздельные способности** (делегированный может запускать готовый протокол,
но не редактировать определение).

## 10. AI-архитектура (не параллельная реализация домена)

```text
Domain state/projection → Context Builder → AI request → Structured Proposal/Analysis
→ Validation → Optional confirmation → Existing application service → Audit
```

Правила: AI использует те же сервисы, что и ручной UI; никакого обхода owner-scoping/капч;
proposal state ≠ applied state; агентность запрашиваема и аудируема; персона меняет presentation,
не создаёт второй rules-engine; LLM Exchange идёт через тот же pipeline.

## 11. Границы доменов (target bounded contexts)

identity, preferences, catalog, activity, sessions, timer, protocols, training, diet, care,
medication, health_state, journal, inventory, media, gamification, insights, agency, relationships,
community, billing, notifications, ai.

Не всё сразу отдельными пакетами. Аудит определяет: dependency graph, cyclic imports,
прямой кросс-доменный ORM-доступ, дублирование хелперов/owner-checks/timezone-логики,
soft-ID ссылки без адаптеров, JSON-blobs как скрытые схемы.

## 12. Инварианты

1. User ownership — конфигурация пользователя первична.
2. Manual completeness — у каждого core-флоу есть non-AI путь.
3. Progressive automation — без принуждения.
4. Personal-first privacy — Personal Core не тонкий клиент над Social; Social потребляет проекции.
5. Lock Timer остаётся bounded context (не растворять).
6. Специализированные модули сохраняют доменную семантику.
7. One command path — ручной UI, AI, Telegram, mobile, делегированный человек → одни сервисы.
8. Actor/source — owner_manual, owner_mobile, telegram_owner, ai_proposal_confirmed, ai_automated,
   human_delegate, system_scheduler, admin — расширяемо, без one-off boolean.

## 13. Анти-цели

Не переписывать в новый фреймворк; не заменять SSR/HTMX только из-за роста; не сливать модули
в одну универсальную таблицу; не делать AI/Persona/D/s-роль обязательными; не удалять Diet/Medication/
Health/Care как «generic»; не убирать ручное создание таймера/сессии; не плодить ещё одну делегацию;
не добавлять community/game фичи до примирения; не переписывать исторические ADR молча;
не выставлять полу-реализованные модели как production; не считать FUNCTIONAL.md доказательством
работоспособности; не делать массовую миграцию без стратегии совместимости.
