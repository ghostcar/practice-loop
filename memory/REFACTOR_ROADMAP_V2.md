## R0 — Repository Reconciliation & Architecture Revision 2 ✅
- [x] Анализ фактической кодовой базы, 83 миграций и 134 таблиц.
- [x] Утверждены принципы: User Sovereignty, Fork-on-Opt-In, Flexible Duration/Quantity, Pluggable Adapters.
- [x] Документы памяти актуализированы.

## R1 — Целостность схемы БД и базовые фичер-флаги ✅
- [x] **R1.1 [Model: Flash/Fast]** Создать миграцию `084_add_media_exposure_and_dms.py` (`media_exposure_drops`, `dead_mans_switch_rules`).
- [x] **R1.2 [Model: Flash/Fast]** Изолировать черновики моделей за флагами в `config.py` (`experimental_leagues=False`, `experimental_billing=False`).
- [x] **R1.3 [Model: Pro/Reasoner]** Тест чистой миграции PostgreSQL (`alembic upgrade head` на чистой БД).
- [x] **Exit:** 100% моделей покрыты миграциями; чистый старт на Postgres.

## R2 — Каталог: Starter Packs, Fork-on-Opt-In и Flexible UI Pickers ✅
- [x] **R2.1 [Model: Flash/Fast]** CLI-сидер `app/cli/seed_catalog.py`: парсит 3 манифеста из `data/seed/` (taxonomy → `ActivityCategory`, full catalog → `ActivityCatalogItem`, inventory → `InventoryItem`); idempotent, dry-run по умолчанию, `--apply` (ADR-105). Инвентарь user-scoped (`user_id` NOT NULL, `is_system` нет) — грузится только с `--user-id`.
- [x] **R2.2 [Model: Flash/Fast]** Jinja-макрос `components/parameter_badges.html`: человекочитаемый рендеринг параметров (timer/flame/target/tools — PracticeLoop icon pack, не эмодзи) вместо `<pre>{{ params_schema | tojson }}</pre>`; подключён в `catalog.html`.
- [x] **R2.3 [Model: Flash/Fast]** Универсальные UI-компоненты гибкого ввода:
  - `components/duration_picker.html`: 5 полей ввода (`Месяцы`, `Дни`, `Часы`, `Минуты`, `Секунды`) + быстрые пресеты (`10с..90с`, `2м..45м`, `1ч..24ч`, `2д..90д`), режимы minmax/single.
  - `components/quantity_picker.html`: поля точного ввода (`Мин`, `Макс`, `Цель`) + селектор единиц (`раз`, `ударов`, `подходов`, `мл`, `капель`, `шт`, `кг`) + пресеты.
- [x] **R2.4 [Model: Pro/Reasoner]** Модель Fork-on-Opt-In: при добавлении в разрешенные создается личный `Entity` / `UserPractice` с `custom_params` пользователя (не мутируя эталонный каталог).
- [x] **R2.5 [Model: Flash/Fast]** Модальное окно персонализации (`catalog_personalize_modal.html`): слайдеры/поля с `duration_picker` и `quantity_picker`, селектор инвентаря, уровень желания.
- [x] **R2.6 [Model: Pro/Reasoner]** Связка генератора задач: генератор читает персональные диапазоны пользователя (`custom_params`).
- [x] **Exit:** 0 сырых JSON в UI каталога; стартовый пак загружается в 1 клик; персональные настройки сохраняются независимо.

## R3 — User Sovereignty & Agency V2 ✅
- [x] **R3.1 [Model: Pro/Reasoner]** Модель `AgencyPolicy` (user_id, domain, default_level, operation_overrides: JSONB, constraints: JSONB) — ручной режим `MANUAL` по умолчанию.
- [x] **R3.2 [Model: Flash/Fast]** Снятие блокирующих гейтов: `risk_level` переводится в информационный статус; opt-in пользователя = полное одобрение (ADR-106). Пользовательские границы становятся строгими системными лимитами.
- [x] **R3.3 [Model: Flash/Fast]** Разрешение очков дисциплины (adherence XP) для медикаментов/ухода по выбору пользователя.
- [x] **R3.4 [Model: Flash/Fast]** 2FA PIN Session Caching: кэширование доступа к Media Vault на 15–30 минут в сессии.
- [x] **R3.5 [Model: Pro/Reasoner]** Двухуровневый D/s-контроль: свободная эмуляция (Soft) vs эмуляция с фиксацией нарушения и штрафом (Strict Audit).
- [x] **Exit:** Пользователь обладает полной автономией; ИИ действует строго в рамках разрешенных границ.

## R4 — Capability Convergence (Единая авторизация акторов) ✅
- [x] **R4.1 [Model: Pro/Reasoner]** Доменная модель `CapabilityGrant` (issuer, recipient, actor_type, capability_code, resource_scope, constraints, valid_until).
- [x] **R4.2 [Model: Pro/Reasoner]** Адаптеры совместимости для `SocialGrant`, D/s `CapabilityGrant` и `CommunityMemberDelegation`.
- [x] **R4.3 [Model: Flash/Fast]** Гранулярные права на протоколы и медикаменты (`protocol.view`, `protocol.start`, `protocol.confirm`, `protocol.edit_definition`).
- [x] **Exit:** Единая точка проверки прав `CapabilityAuthorizer.check()`; старые таблицы работают через адаптеры.

## R5 — Protocol Foundation (Протоколы подготовки и рутин) ✅
- [x] **R5.1 [Model: Pro/Reasoner]** Доменная модель `ProtocolDefinition` + `ProtocolStep` + `ProtocolRun` + `ProtocolStepLog` с типизированным таймингом `TimingSpec` (`T-X`..`T+Y`, `rel_before`, `rel_after`, `window`).
- [x] **R5.2 [Model: Flash/Fast]** Реестр обработчиков шагов `ProtocolStepHandler` (активность, препарат, уход, замер, чек-ин).
- [x] **R5.3 [Model: Flash/Fast]** UI конструктора и трекера протоколов (`protocol_builder.html`, `protocol_run.html`).
- [x] **R5.4 [Model: Pro/Reasoner]** Интеграция с сессиями и LockTimer (запуск подготовки перед стартом и восстановления после).
- [x] **Exit:** Пользователь может собрать и пройти протокол подготовки/восстановления полностью вручную без ИИ.

## R6 — Dynamic Orchestration (Контейнеры сценариев) ✅
- [x] **R6.1 [Model: Pro/Reasoner]** Доменная модель `DynamicDefinition` (профиль с Agency overlay, набором протоколов, Persona и грантами) и `DynamicRun` с иммутабельным Frozen Snapshot.
- [x] **R6.2 [Model: Flash/Fast]** Дашборд активного режима `dynamic_active.html` / `dynamics.html`.
- [x] **Exit:** Запущенный динамический режим изолирован снимком правил; ручные пользователи могут игнорировать динамики.

## R7 — Pluggable Adapter Registry & AI Convergence ✅
- [x] **R7.1 [Model: Pro/Reasoner]** Реестр платежных шлюзов `PaymentGatewayRegistry` (`StripeGateway`, `TelegramStarsGateway`, `NowPaymentsCryptoGateway`, `YuKassaGateway`, `MockGateway`). Единый чекаут-эндпоинт.
- [x] **R7.2 [Model: Pro/Reasoner]** Реестр каналов уведомлений `NotificationDispatcher` (In-App, Telegram, Email, Push).
- [x] **R7.3 [Model: Pro/Reasoner]** Реестр контекст-провайдеров аналитики `InsightProviderRegistry` (`HealthInsightAdapter`, `CareInsightAdapter`, `MedicationInsightAdapter`, `TrainingInsightAdapter`, `ProtocolInsightAdapter`) — устранение прямых кросс-доменных импортов 8 моделей в `app/analytics/engine.py`.
- [x] **R7.4 [Model: Pro/Reasoner]** Единый `HealthContextProvider` (Recovery score, Energy, Sleep, Cycle phase) для генераторов тренировок и сессий.
- [x] **R7.5 [Model: Pro/Reasoner]** Единый AI Proposal Pipeline: Persona и AutomationTrigger маршрутизируются через общий сервисный слой команд.
- [x] **Exit:** Все внешние интеграции и междоменные аналитические запросы вынесены в адаптеры; ИИ не мутирует домен напрямую.

## R8 — Social & D/s Hardening + ActorContext Audit ✅
- [x] **R8.1 [Model: Pro/Reasoner]** Сквозной `ActorContext` (owner_manual, owner_mobile, telegram, ai_proposal_confirmed, ai_automated, human_delegate, scheduler, admin) во всех application services.
- [x] **R8.2 [Model: Flash/Fast]** Реализация `TimerSocialAdapter` на базе Capability-ядра.
- [x] **Exit:** Каждая мутация в БД содержит прозрачный контекст автора; D/s и Social полностью согласованы.

## R9 — Глобальная чистка неиспользуемого кода и шаблонов (Dead Code & Asset Cleanup)
- [x] **R9.1 [Model: Flash/Fast]** Аудит шаблонов: сканирование `app/templates/` и удаление неиспользуемых файлов-черновиков прототипа (`live_camera_observer.html`, `dashboard.html` legacy).
- [x] **R9.2 [Model: Flash/Fast]** Очистка статических файлов: вынос inline-скриптов в `app/static/js/pages/`, актуализация пакета SVG-иконок (142 шт).
- [x] **R9.3 [Model: Flash/Fast]** Удаление мертвого Python-кода и неиспользуемых импортов.
- [ ] **Exit:** 0 мусорных файлов в проекте; чистый репозиторий.

## R10 — Рекомпозиция интерфейса («Тёмный архив») и Closed Beta Release Candidate (v1.0)
- [x] **R10.1 [Model: Flash/Fast]** Обновление `sidebar.html` и мобильной панели: группировка в 5 разделов (*Сегодня / План / Тело & Рутина / Связи / Система*), скрытие выключенных модулей.
- [x] **R10.2 [Model: Flash/Fast]** Вынос inline-скрипта из `llm_exchange.html` в `app/static/js/pages/llm_exchange.js` (CSRF из meta); allowlist `test_audit_s57.py` обновлён.
- [x] **R10.3 [Model: Pro/Reasoner]** Фоновый async-воркер DMS & Reminder Scheduler в `lifespan` FastAPI + Telegram алерты.
- [x] **R10.4 [Model: Pro/Reasoner]** Сквозной E2E регрессионный тест критических путей (`tests/test_v1_rc_critical_paths.py`).
- [x] **R10.5 [Model: Flash/Fast]** Прогон полного pytest-сьюта (1340+ тестов), `ruff check`, `memoryctl facts && lint`, обновление документации (`FUNCTIONAL.md`, `README.md`, `CURRENT_STATE.md`, `PRODUCT.md`).
- [ ] **Exit:** Release Candidate v1.0.0-rc1 готов к продуктовому деплою для закрытого бета-теста.
