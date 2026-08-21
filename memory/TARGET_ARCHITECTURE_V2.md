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

## 9. Каталог: целевая модель (Fork-on-Opt-In + UI Readability)

**Архитектура каталога и персонализации:**
1. **Эталонный каталог (`ActivityCatalogItem` / `data/seed/`):**
   - Неизменяемый системный источник истины (типы, категории, анатомические зоны, базовые диапазоны).
   - Загружается скриптом / кнопкой сидинга из 23 файлов `data/seed/`.
2. **Персонализация при добавлении (Fork-on-Opt-In):**
   - При добавлении активности в разрешенные (`user_entity_opt_in` / `Entity` с `owner_id = user.id`) пользователь может скорректировать параметры под себя:
     - Личные границы длительности (min/max), интенсивность, персональный инвентарь, заметки.
     - Личные настройки сохраняются как независимый пользовательский экземпляр.
   - ИИ-генератор и пайплайн сессий читают **персональные диапазоны пользователя**, а не абстрактный эталон.
   - Обновления системного каталога безопасны и не затирают пользовательские настройки.
3. **UI Readability (Отказ от сырого JSON):**
   - Полный отказ от `<pre>{{ params_schema | tojson }}</pre>`.
   - Замена на визуальные бейджи и чипы (`components/parameter_badges.html`): ⏱ время, ⚡ интенсивность, 🎯 зоны воздействия, 🧰 предметы инвентаря.
   - Удобные слайдеры и селекты в модальном окне персонализации вместо редактирования JSON.

## 10. Миграционная стратегия

1. Не переписывать стабильные таблицы ради чистоты имён.
2. Аддитивные миграции; адаптеры при переносе концептов.
3. Сохранять ID (кросс-доменные ссылки).
4. JSON-схемы — в Pydantic/domain types.
5. DB-constraints для инвариантов, сейчас только в UI.
6. Каждая миграция тестируется на PostgreSQL, не только SQLite (S4).
7. Downgrade — не единственный recovery; backup перед деструктивными.

## 11. Снятие избыточных точек безопасности (v1.0 Relaxed Gates)

1. **Граница одобрения:** Opt-in пользователя = полное одобрение (ADR-106). `risk_level` — информационные метаданные для ИИ, а не блокирующие гейты.
2. **Медикаменты и уход:** Разрешено начисление очков дисциплины (adherence XP) и включение в шаги Протоколов.
3. **2FA / PIN Shield:** Кэширование доступа в сессии браузера на 15–30 минут (без навязчивого ввода PIN на каждый клик).
4. **Двухуровневый D/s-контроль:** Свободная эмуляция в мягком режиме / эмуляция с записью нарушения в строгом режиме сессии.

## 12. Унифицированный примитив гибкой длительности и расписаний (Flexible Duration Component)

- **Отказ от жестких рамок:** Нигде в системе нет захардкоженных интервалов (только 15м/30м или только 24ч). Поддерживаются как длинные периоды, так и короткие статические упражнения / задержки дыхания / сенсорные воздействия в секундах.
- **UI-компонент ввода (`components/duration_picker.html`):**
  - **5 полей точного ввода:** `[Месяцы]` `[Дни]` `[Часы]` `[Минуты]` `[Секунды]`.
  - **Быстрые пресеты-чипы:**
    - Секунды: `10с`, `15с`, `20с`, `30с`, `45с`, `60с`, `90с`.
    - Минуты: `2м`, `5м`, `10м`, `15м`, `20м`, `30м`, `45м`.
    - Часы: `1ч`, `2ч`, `4ч`, `8ч`, `12ч`, `24ч`.
    - Дни/Месяцы: `2д`, `3д`, `7д`, `14д`, `30д`, `90д`.
  - При клике на пресет поля заполняются автоматически, но пользователь может ввести любое произвольное значение (напр. 45 секунд, 17 минут, 36 часов, 45 дней).
- **Сквозное применение:** Активности (диапазоны min/max в секундах/минутах), Сессии (таймауты), LockTimer (длительность блокировки, интервалы слотов), Dead Man's Switch (интервал и grace period), Протоколы (смещения `T - X` .. `T + Y`), Курсы ухода/медикаментов, Media Showcase (время экспозиции и кнопки продления).
- **Хранение в БД:** Абсолютные секунды (`duration_seconds: int`), преобразование через хелпер `timeutils.py`.

## 13. Унифицированный примитив гибкого количества, повторений и дозировок (Flexible Quantity & Reps Component)

- **Отказ от дискретных ограничений:** Любые активности с числовой нагрузкой поддерживают произвольное точное количество.
- **UI-компонент ввода (`components/quantity_picker.html`):**
  - **Поля точного ввода:** `[Мин. порог / Мин]` `[Макс / Цель]` `[Единица измерения]`.
  - **Селектор единиц:**
    - Повторения / раунды: `раз`, `подходов`, `циклов`, `кругов`.
    - Воздействия: `ударов`, `серий`, `импульсов`.
    - Дозировки / объём: `мл`, `капель`, `таблеток / шт.`, `г`, `мг`, `порций`.
    - Длина / дистанция: `шагов`, `метров`, `км`.
    - Вес / нагрузка: `кг`, `баллов`.
  - **Быстрые пресеты-чипы:**
    - Повторы: `5`, `10`, `15`, `20`, `25`, `30`, `50`, `100`, `200`.
    - Объёмы: `1 шт`, `2 шт`, `50 мл`, `100 мл`, `250 мл`, `500 мл`.
  - Возможность ввести любое произвольное число (напр. 33 повторения, 75 капель, 12 подходов).
- **Сквозное применение:** Активности каталога, программы тренировок/дисциплин, дозировки препаратов/БАДов, шаги ухода (помпы/капли), гидратация (вода в мл).

## 14. Архитектурный принцип: Ports & Adapters (Гексагональная архитектура границ)

### Фундаментальный закон:
> **Adapter-first at boundaries, service-first inside domains.**
> - На внешних границах и междоменных стыках: взаимодействие ТОЛЬКО через стабильный Port (Protocol/Interface) и Registry адаптеров.
> - Внутри одного bounded context: простые доменные сервисы и ORM-модели напрямую, БЕЗ искусственного нагромождения адаптеров ради адаптеров.

### Ключевые порты и реестры адаптеров (Замена прямых кросс-импортов):

| Порт / Интерфейс (Port) | Реестр адаптеров (Registry) | Существующий прямой импорт (Что заменяем) | Выигрыш в расширяемости |
|---|---|---|---|
| **1. `PaymentGatewayPort`** | `PaymentGatewayRegistry` (`StripeGateway`, `StarsGateway`, `NowPaymentsGateway`, `YuKassaGateway`, `MockGateway`) | Прямые ссылки и эмуляции в `app/billing/gateways.py` | Добавление любого нового банка/провайдера в 1 класс-адаптер без правки роутеров. |
| **2. `InsightContextProviderPort`** | `InsightProviderRegistry` (`HealthInsightAdapter`, `CareInsightAdapter`, `MedicationInsightAdapter`, `TrainingInsightAdapter`, `LockTimerInsightAdapter`, `ProtocolInsightAdapter`) | `app/analytics/engine.py` и `app/agent/tools.py` напрямую импортируют 8 моделей из разных доменов (`CareEntry`, `HealthState`, `MedIntake`, `TrainingDay`...) | Добавление нового модуля (напр. `Protocols` или `Breathplay`) не требует правок в аналитическом движке: модуль сам регистрирует свой `InsightContextProvider`. |
| **3. `HealthContextProviderPort`** | `HealthContextProvider` (Recovery score, Energy, Sleep, Cycle phase, State flags) | `training_generator.py` и `context_builder.py` читают `HealthState` и `BodyCycle` напрямую через SQL | Генератор тренировок и сессий получает стандартизированный снимок восстановления без знания схемы таблиц здоровья. |
| **4. `ProtocolStepHandlerPort`** | `ProtocolStepHandlerRegistry` (`ActivityStepHandler`, `MedicationStepHandler`, `CareStepHandler`, `MeasurementStepHandler`, `PhotoCheckinHandler`, `LockTimerActionHandler`) | Потенциальное разрастание `if step_type == ...` в исполнителе протоколов | Любой новый тип шага (напр. дыхательная гимнастика или звуковой сигнал) регистрируется как отдельный плагин-обработчик. |
| **5. `NotificationChannelPort`** | `NotificationDispatcher` (`InAppChannel`, `TelegramBotChannel`, `EmailChannel`, `WebPushChannel`) | Разрозненные вызовы `broadcast.py`, `aiogram` и in-app логов из роутеров задач/DMS | Домены вызывают `await notify(user_id, event, payload)`; диспетчер сам маршрутизирует сообщения в активные каналы. |
| **6. `CapabilityAuthorizerPort`** | `CapabilityAuthorizerRegistry` (`SocialGrantAdapter`, `DsGrantAdapter`, `CommunityDelegationAdapter`, `DirectCapabilityAdapter`) | 4 разных таблицы и разрозненные проверки в `api/ds.py`, `api/social/`, `api/communities.py` | Единая точка авторизации `can_act(actor_context, capability_code, resource_id)`. |

### Где адаптеры НЕ создаются (Anti-Boilerplate Guard):
Внутри `app/locktimer/domain/`, `app/services/tasks.py`, `app/services/smart_albums.py` используются прямые вызовы внутренних функций и моделей своего домена.

## 15. Глобальная чистка неиспользуемого кода и фронтенд-ассетов (Dead Code & Asset Cleanup)

- **Аудит неиспользуемых шаблонов:** сканирование `app/templates/` на предмет заброшенных файлов прототипа, не вызываемых ни в одном `TemplateResponse`.
- **Очистка статических ассетов:** удаление устаревших CSS/JS-скриптов и иконок, не входящих в `app/static/icons/sprite.svg`.
- **Удаление мёртвого Python-кода:** аудит неиспользуемых импортов, вспомогательных функций и неподключенных роутов.

## 16. Запреты (anti-goals)

Не monolith «core»; не растворять Lock Timer; не делать AI обязательным; не делать D/s-роль
обязательной при онбординге; не удалять Diet/Medication/Health/Care; не создавать ещё одну
делегацию до конвергенции Capability; не выставлять automation/leagues/duels как production;
не хардкодить жесткие временные или количественные рамки без возможности точного ручного ввода;
не плодить прямые вызовы внешних SDK или прямые кросс-доменные SQL-запросы в обход портов.
