# Practice Loop — продуктовый roadmap

> Статус: принятый порядок развития без календарных обещаний.
> Актуально на: 18 августа 2026 года.
> Текущая контрольная точка и блокеры: `CURRENT_STATE.md`.

## 1. Цель roadmap

Roadmap ведёт Practice Loop от функционального Tracker-прототипа к полноценному Personal-first
продукту, затем к Social и только после этого — к цифровому Dominant/submissive-делегированию и
Community.

Порядок основан на четырёх правилах:

1. сначала владелец должен ежедневно пользоваться Personal сам;
2. каждый этап оставляет работающий и проверяемый продукт;
3. Social не становится зависимостью Personal;
4. D/s не строится на скрытых правах и не появляется до capability/audit foundation.

Календарные даты намеренно не фиксируются: переход к следующему этапу определяется gate, а не
числом в календаре.

## 2. Карта контрольных точек

| Milestone | Результат |
|---|---|
| M0 | Зелёный, воспроизводимый `main` |
| M1 | Завершённый Activity Tracker v2 и рабочий Today |
| M2 | Полноценный личный Chastity Timer |
| M3 | Цельный Personal Suite с журналами, Care и Health foundation |
| M4 | Mobile Foundation + кроссплатформенный мобильный клиент |
| M5 | Social без делегирования управления |
| M6 | Manual Dominant Workspace и затем зарегистрированный D/s |
| M7 | Закрытые пространства и Community |

## 3. Этап 0 — восстановление доказуемого baseline

**Статус: ✅ ДОСТИГНУТ И ПЕРЕПРОВЕРЕН (S2–S3, 18 августа 2026).**

- полный pytest в воспроизводимом Python 3.11 dev image — **1132 passed, 1 skipped ✅**;
- ruff/format ✅; production-like compose health ✅;
- PostgreSQL 15 migration roundtrip ✅ (`base→057→058→057→058`), single head 058;
- секреты из Git вычищены (S51), без uploads/БД/экспортов в репозитории;
- GitHub Actions: CI зелёный, включая docker job.

**Gate M0:** GitHub Actions зелёный; полный test job реально выполнен; migration job зелёный;
Docker image собирается; документация не утверждает результатов, которых CI не подтвердил.
→ **Прогресс: 100%.**

## 4. Этап 1 — Activity Tracker v2

**Статус: ⏳ ~80%.**

### 1A. Backend completion — ✅ в основном

- LLM-контракт planned/actual ✅ (S62);
- единая семантика одиннадцати состояний во всех сервисах ✅;
- XP/Points/penalties для каждого финального результата — ⏳ частично (детализация по новым
  статусам: partially_completed, substituted, not_applicable, review_needed);
- accepted-session freeze и аудит изменений — ⏳ модель есть (`accepted_at`), enforcement не завершён;
- история переходов ✅ (`activity_task_history`);
- import/export новых полей — ⏳ частично;
- Telegram и scheduler без legacy `pending/interrupted` ✅;
- concurrency и idempotency tests ✅.

### 1B. UI completion — ✅ в основном (S61)

- категории и фильтры ✅; динамическая форма типизированных параметров ✅;
- карточка плановых и фактических значений ✅; быстрые допустимые переходы ✅;
- комментарий к результату ✅; история изменений — ⏳ (UI-экран аудита);
- понятные состояния empty/loading/error — ⏳; RU/EN, dark/light, mobile ✅.

### 1C. Today foundation — ✅ реализован, UX-достройка ⏳

Today projection агрегирует задачи, активную Timer-сессию, диеты, тренировки и личные модули;
работают напоминания и быстрые действия. Осталось: единая подача просроченного/требующего решения,
один основной CTA на блок и быстрый переход к разбору.

### Gate M1

Пользователь может создать или получить задание, увидеть причину и параметры, принять сессию,
выполнить/частично выполнить/пропустить/остановить, внести факт и увидеть аудит. Все пути работают
из web и корректно отражаются в личном Telegram.
→ **Прогресс: ~80%.** Остаток: accepted-session enforcement, UI аудита, Today-достройка.

## 5. Этап 2 — Personal Foundation

**Статус: ✅ основной фундамент реализован; операционные расширения продолжаются.**

### Цель

Подготовить общие личные возможности, нужные Chastity Timer и журналам, не превращая Tracker в
монолит.

### Входит

- явные границы Personal-модулей;
- общий Today projection service;
- timezone и quiet hours (timezone уже есть у User);
- надёжные notifications/outbox (задел есть: `lock_outbox_events`);
- Media Vault foundation: original, derivative, ownership, retention (база: `media_assets`);
- durable versioned consent для чувствительной обработки: одно согласие на цель/версию условий,
  запрос при первом входе или включении нового профильного модуля, явный revoke;
- discretion mode и нейтральные уведомления;
- export/restore и проверяемые бэкапы;
- audit primitives;
- единые attachment и inventory links без прямого доступа к чужим таблицам;
- **storage-абстракция** (volume → S3-совместимое объектное хранилище) — PD-019.

Границы и фактические контракты закреплены в `TARGET_ARCHITECTURE.md`, ADR и `FUNCTIONAL.md`.
Остаются storage-абстракция и расширение export/restore/operational evidence.

## 6. Этап 3 — личный Chastity Timer

**Статус: ✅ личный контур реализован; остаются export/restore и polish.**

Ядро LockTimer реализовано полностью: draft/start, immutable snapshot, 6+7+10 state machines,
материализатор (5 slot + 6 task типов, rolling 90d), окна снятия, check-in, задания, одноразовые
коды (`verification_challenges`), скрытый/случайный срок (commitment scheme), продления с лимитами,
штрафы и отработки, safety stop, outbox, media, LLM-предложения, tag-механика, календарь,
compliance, drag&drop.

### 3A. Device inventory — ✅ реализовано

- каталог устройств (тип, название, фото, размер, конфигурация);
- обслуживание, комфорт, проблемы;
- связи с общим Inventory и Care.

### 3B. Честная терминология фронта — ✅ PD-017

Внутренние `lock_*` имена остаются; **фронт и уведомления переводятся на честные термины**
(device, wearer, lock-on, unlock window, keyholder). Это i18n + шаблоны, без миграций.

### 3C–3E. Остальное

- Health/Cycle и care остаются relief-only и не усиливают ограничения ✅;
- Today card/projection ✅, дальнейший UX polish ⏳;
- Personal Telegram Timer-команды ✅;
- одно активное правило vs параллельность — явно решить.

### Gate M2

Полный self-lock flow работает без LLM, Social и другого пользователя. Freeze snapshot и caps
проверены concurrency tests; emergency stop доступен всегда; полный export/restore сохраняет Timer
history.
→ **Прогресс: основной self-lock flow и предметная обвязка готовы; остаётся operational polish.**

## 7. Этап 4 — специализированный Personal Suite

Направления используют общую Personal Foundation. Каждое поставляется вертикальным законченным
срезом.

- **4A. Sexual Journal** — ✅ реализован, включая Aftercare;
- **4B. Personal Care** — ✅ процедуры, средства, курсы, медиа и напоминания;
- **4C. Medication Organizer** — ✅ каталог, остатки, расписание, факты и Telegram;
- **4D. Health and Cycle foundation** — ✅ check-ins, labs, факты и расчётные фазы;
- **4E. Personal Insights** — ✅ opt-in кросс-модульный анализ без утверждения причинности.

### Gate M3

Каждый модуль полезен отдельно; Health не участвует в штрафах; Today не смешивает правила;
межмодульная связь — через ограниченный контракт.

## 8. Этап 5 — Mobile Foundation и мобильный клиент (PD-018)

**Статус: 5A ✅ реализован; 5B ❌ не начат.**

### 5A. Mobile Foundation (технический фундамент)

- **JSON-first контракты** для всех action-эндпоинтов (PD-020) — начать с timer start/safety-stop
  и распространённых действий;
- **bearer-auth** слой рядом с cookie-сессией (access + refresh);
- **push-уведомления** (FCM/APNs) помимо Telegram;
- media URL-контракты для мобильного клиента;
- закладывается **до Social** — Social и так строит JSON API, мобильный клиент переиспользует те же
  контракты.

Реализовано: access/refresh с ротацией и отзывом, push-device registry и provider abstraction,
bearer media URL, dual-mode JSON для ключевых Timer/actions. Расширение JSON-first покрытия остаётся
операционным долгом перед клиентом.

### 5B. Кроссплатформенный клиент

- Flutter или React Native (PQ-008);
- первый клиент Personal: Today, задачи, Chastity Timer, журналы, уведомления;
- после запуска базового портала (по PD-018).

### Gate M4

Мобильный клиент покрывает ключевые Personal-сценарии; все его действия идут через JSON API;
push работает; bearer-auth безопасен.

## 9. Этап 6 — Social Foundation

**Статус: ⚠️ S0–S7 реализованы (сессии 73–76), Social не открыт публично.**

- **6A. Trust and identity** ✅ (профили-псевдонимы, отношения, block graph);
- **6B. Projections** ✅ (subject registry, adapters, redacted snapshots);
- **6C. Verification** ✅ (запросы, голосование, quorum);
- **6D. Chastity Social** — ⏳ не начато (публичный статус, продления с caps, cooldown);
- **6E. Moderation** ✅ (жалобы, скрытие, аудит).

### Осталось до открытия

- решить PQ-003: открыть S0-S7 как есть или сначала Chastity Social;
- rate limits (Q6), email-верификация, welcome-flow;
- нагрузочные тесты под публичный трафик.

### Gate M5

Revoke/block действует немедленно; private original недоступен; публикация содержит только
подтверждённый preview; quorum finalizes exactly once; Social off не меняет Personal.
→ **Прогресс: ~70%** (функции есть, открытие — отдельный gate).

## 10. Этап 7 — Dominant/submissive

### 7A. Manual Dominant Workspace — ❌ не начато

Внешний submissive — локальная сущность, не User; versioned agreements; задания и отчёты;
генератор текста; ручная отметка отправки; ручной импорт ответа и медиа; очередь проверки;
pause/stop/close. Гостевого портала нет.

### 7B. Transport adapters — после ручного flow

### 7C. Registered D/s delegation — после 7A

### 7D. Multiple dynamics

### Gate M6

Ни роль, ни Social relationship не дают скрытых прав; каждая операция доказывает грант и cap;
revoke/block мгновенно останавливает будущие действия.

## 11. Этап 8 — закрытые пространства и Community

Сначала закрытые пространства с модераторами, курируемые шаблоны, ограниченные публикации,
экспорт/выход/блокировка, нагрузочные и abuse tests. Значительно позже — открытая лента, поиск,
рекомендации, marketplace.

### Gate M7

Community не имеет прямого доступа к Personal, Health или D/s grants; moderation и privacy
operations выдерживают публичный трафик; публичность включается отдельным обратимым флагом.

## 12. Future Research — автономные физические устройства

**Статус: идея для исследования, не принято к реализации.** Исходный материал:
`examples/concept-device.md`. Документ является черновой беседой и не считается проверенным
инженерным ТЗ, оценкой безопасности или BOM.

Перспективная гипотеза — отдельный автономный носимый хаб, который может объединять несколько
независимых каналов совместимых аксессуаров, локальные паттерны из памяти и управление с телефона.
В исследовательский контур также могут войти BLE/Wi-Fi/LTE, телеметрия состояния, опциональная
геолокация и интеграция с разрешёнными сторонними устройствами. Портал при этом должен работать
через версионированный device protocol и журнал команд, а критические ограничения остаются внутри
самого устройства и не зависят от сети, телефона, LLM или сервера.

### Обязательные gates до проектирования прототипа

- отдельное решение владельца, явно пересматривающее PD-016; до него Practice Loop не управляет
  физическим устройством;
- независимая экспертиза electrical/biocompatibility safety и применимых стандартов; значения из
  исходного концепта нельзя переносить в схему без верификации профильным инженером;
- hardware fail-safe: локальное безусловное отключение, watchdog, безопасное состояние при потере
  связи/питания, аппаратные лимиты и невозможность удалённо расширить их;
- питание во время использования только от изолированного автономного источника; сетевое питание,
  зарядка и отладочный USB должны быть физически исключены из рабочего контура;
- явное versioned consent отдельно для удалённого управления, телеметрии, биометрии и геолокации;
  геолокация выключена по умолчанию, видима пользователю, ограничена по сроку и мгновенно отзываема;
- signed firmware, device identity, взаимная аутентификация, anti-replay, аудит и ручное локальное
  восстановление; облако и LLM не выполняют safety-critical control loop;
- сначала симулятор и стенд с эквивалентом нагрузки, затем независимые лабораторные испытания;
  испытания на человеке не являются этапом обычной разработки ПО.

### Возможная последовательность после принятия решения

1. Нейтральный device protocol и симулятор без физического выхода.
2. Одноканальный лабораторный стенд и формальная hazard analysis.
3. Независимый аудит hardware/firmware и regulatory classification.
4. Только после прохождения gates — ограниченный многоканальный прототип и интеграция с порталом.

Связанный открытый вопрос: `docs/questions/EQ-0015.md`.

## 13. Сквозные направления

### Scalability (PD-019)

| Ось | Что закладывается сейчас | Когда активируется |
|---|---|---|
| Пользователи | owner-scoped контракт, rate limits (Q6) | При открытии публичного доступа |
| Данные | partition для больших журналов, retention, export/restore | При росте объёмов |
| Инфраструктура | stateless app, очередь (задел `lock_job_receipts`), S3-абстракция, реплика БД | При втором инстансе |

### Security, privacy and consent

На каждом этапе: object-level auth, CSRF, idempotency, concurrency tests, audit, retention,
export/delete, secret scanning.

Согласие действует один раз для конкретных purpose и terms version до явного отзыва; новые
профильные модули запрашивают своё согласие при включении. Для BYOK отдельно раскрывается, что
провайдера и ключ принёс пользователь и он отвечает за выбор провайдера, ToS, расходы и данные;
это не отменяет локальные policy/safety gates портала.

### UX

RU/EN, dark/light, keyboard, 360/768/1280, discretion, нейтральные lock-screen notifications и
понятные empty/error states входят в gate, а не остаются «полировкой потом».

### LLM

Для каждого use case заранее фиксируются входные данные, allowlist действий, deterministic
fallback, server validation, retention и отдельное согласие на чувствительное медиа.

### Operations

Каждый milestone имеет migration plan, backup/restore, feature flags, metrics, rollback и
deployment evidence.

### Documentation

`PRODUCT_DECISIONS.md` обновляется при решении, `CURRENT_STATE.md` — при смене факта,
`ROADMAP.md` — при смене порядка, memory — каждую сессию. Правила в `DOCUMENTATION_MAP.md`.

## 14. Что не должно перескакивать этапы

- Social public нельзя включать до report/block/moderation.
- D/s grants нельзя строить только на строке role.
- Внешние боты нельзя проектировать раньше ручного communication flow.
- Chastity Social нельзя начинать раньше устойчивого личного Timer Core.
- Community нельзя использовать как замену Social Foundation.
- Health нельзя связывать с penalty engine.
- LLM нельзя использовать вместо state machine, policy engine или capability check.
- Новый крупный модуль нельзя начинать при красном baseline без отдельного решения владельца.
- Мобильный клиент не начинать до Mobile Foundation (JSON-first + bearer-auth).
- Физическое устройство нельзя проектировать как исполнительный контур портала до явного
  пересмотра PD-016 и прохождения safety/privacy gates из Future Research.

## 15. Следующая фактическая работа

Ближайший gate — безопасно доставить миграции **054–058** и новый образ в запущенный
production-like compose (S5), сохранив rollback. Затем закрываются остатки M1/Today и выбирается
следующий продуктовый приоритет: mobile client либо limited Social rollout. Конкретная очередь —
в `CURRENT_STATE.md` и `PLAN.md`.
