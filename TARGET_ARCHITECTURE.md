# Practice Loop — целевая архитектура (TARGET_ARCHITECTURE.md)

> Статус: нормативный инженерный документ. Заменяет необходимость угадывать границы модулей.
> Актуально на: 16 августа 2026 года.
> Источник продукта: `PRODUCT_VISION.md`; принятые решения: `PRODUCT_DECISIONS.md`;
> фактическое состояние: `CURRENT_STATE.md` и код текущего HEAD.
> При расхождении с `REMEDIATION_SPEC.md`, `tracker-spec.md` или `LockTimer-Agent-Pack`
> действует этот документ и соответствующая ADR.

## 1. Назначение

Документ фиксирует целевые bounded contexts, межмодульные контракты, события, транспорты,
мобильный API-контракт и правила rollout до начала строительства специализированного
Personal Suite (журналы, Care, Health, Insights, углублённый Media Vault).

Он описывает **цель**, а не только текущий код. Что уже реализовано — помечено `[есть]`;
что проектируется под M3 и далее — `[цель]` / `[позже]`. Фактическая готовность всегда
проверяется по коду, миграциям и тестам, а не по этому файлу.

## 2. Неизменные принципы (из PD-001..016)

1. **Personal — продукт.** Каждый Personal-модуль полезен сам по себе, без партнёра,
   публичности или внешнего keyholder.
2. **Контуры по способу управления:** Personal (владелец сам), Social (проекции + allowlisted
   действия), D/s (явные гранты). Community — поздняя оболочка.
3. **Модуль не лезет в таблицы другого модуля.** Связь — только через явный контракт
   (ID + проекция + adapter). Никаких прямых FK в чужие агрегаты без контракта.
4. **Критические действия детерминированы.** Сроки, лимиты, права, штрафы, safety stop —
   серверные правила; LLM не источник истины.
5. **Health отделён от игры (PD-013).** Медицинский сигнал может только облегчить/паузу/остановку,
   никогда не наказывает.
6. **Safety stop всегда доступен (PD-006).** Игровой результат применяется после, не блокирует выход.
7. **План и факт разделены.** Для задач, Timer, тренировок, лекарств, ухода и журналов.
8. **Один продукт, одна кодовая линия (PD-015).** `timer-only`/fork не создаются без отдельного решения.
9. **Приватность по умолчанию (PD-012).** Публикуется только явно выбранная проекция.

## 3. Карта bounded contexts

```
┌─────────────────────────────────────────────────────────────────────┐
│  Platform Foundation  [есть]                                        │
│  auth/JWT+bearer, security/CSRF, prefs(theme/accent/discretion),    │
│  composition(варианты+feature flags), capabilities, push, i18n      │
└──────┬───────────────┬───────────────┬───────────────┬──────────────┘
       │               │               │               │
  ┌────▼─────┐   ┌─────▼──────┐  ┌─────▼──────┐  ┌─────▼──────────┐
  │ Today    │   │ Media Vault│  │ Insights   │  │ Transports     │
  │ [цель]   │   │ [частично] │  │ [цель]     │  │ [есть/цель]    │
  └──────────┘   └────────────┘  └────────────┘  │ Telegram[есть] │
                                                 │ push[есть]     │
  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │ Activity     │ │ Chastity     │ │ Journals     │ │ Care &       │
  │ Tracker      │ │ Timer        │ │ [цель]       │ │ Health       │
  │ [есть]       │ │ [есть]       │ │ Sexual       │ │ [цель]       │
  └──────────────┘ └──────────────┘ │ Journal      │ │ Medication   │
  ┌──────────────┐ ┌──────────────┐ └──────────────┘ │ Health/Cycle │
  │ Training     │ │ Diet         │                  └──────────────┘
  │ [есть]       │ │ [есть]       │  ┌──────────────┐ ┌──────────────┐
  └──────────────┘ └──────────────┘  │ Gamification │ │ Social       │
                                     │ [есть]       │ │ [есть]       │
                                     └──────────────┘ └──────────────┘
```

### 3.1. Platform Foundation `[есть]`

- **composition root** (`app/platform/composition.py`) — единственное место, где решается,
  какие модули активны (вариант `tracker|timer|combined` + feature flags). Роутеры, навигация и
  jobs читают его, а не разбросанные env-проверки.
- **capabilities** (`app/platform/capabilities.py`) — декларативные способности модулей.
- **auth** — JWT access (+claim `type=access`) + refresh (rotation/revoke, `api_tokens`),
  cookie-сессия для web, bearer для мобильного/JSON.
- **security** — CSRF (не требуется для bearer), Secure-cookie loopback-aware, security-заголовки,
  CSP report-only до Gate C.
- **prefs** — тема/акцент/плотность/блоки дашборда/discretion, `users.prefs` JSONB, ContextVar.
- **push** — `PushSender` protocol + registry + `dispatch_push` (`PUSH_PROVIDER=none|logging|fcm|apns`).
- **i18n** — EN/RU, единый реестр ключей.

### 3.2. Activity Tracker `[есть]`

Каталог (`Entity`), задания (`ActivityLog`), сессии (`ActivitySession`), категории (16),
11 состояний + аудит (`ActivityTaskHistory`), типизированные параметры (DSL, без `eval`),
опт-ин, планировщик/календарь, title-генератор.

### 3.3. Chastity Timer `[есть]` (bounded context `locktimer`)

14 таблиц `lock_*`, state machines (draft/validating/active/completed/safety_stopped…),
snapshot при старте, слоты/задачи, окна, штрафы, номерные бирки (seal), device inventory
(`lock_sessions.device_id`), materializer на будущие дни. Честная предметная модель (PD-004),
нейтральность — только для discretion.

### 3.4. Training и Diet `[есть]`

Отдельные системы программ внутри Personal (PD «Training/Nutrition»). Собственные модели,
LLM-разбор, взаимная синергия.

### 3.5. Gamification `[есть]`

XP/уровни/серии/достижения, Points v2 (гибкая схема), DSL условий, штрафы/redemption/thresholds.
**Не имеет права трогать Health.**

### 3.6. Media Vault `[частично → цель]`

Есть: owner-scoped upload, allowlist+magic bytes+size limit, `/media` галерея, верификация через
vision-LLM (`media_verification_results`). Цель (M3 и далее): **original отдельно от derivatives**,
`Shared Artifact` (намеренная передача копии), access grants, retention, история доступа/отзыва/удаления.
Подробнее жизненный цикл — `DATA_LIFECYCLE.md`.

### 3.7. Journals `[цель]` — Sexual Journal (4A)

Приватная запись факта/ощущений/реакций/aftercare, локальные псевдонимы партнёров, связь
с Timer/Cycle/Health по ID/проекциям. Собственный контекст, не рейтинг, не контроль партнёра.

### 3.8. Care `[цель]` — Personal Care (4B)

Уход/косметика/процедуры/депиляция/расходники, фото динамики. Переиспользует Inventory/Measurements
через контракты; действия могут по желанию становиться заданиями Tracker или окном Timer
(через адаптеры, см. §5).

### 3.9. Health `[цель]` — Medication Organizer (4C) + Health/Cycle (4D)

- **Medication Organizer** — первый Health-срез (шаг 11b): лекарства, аптечки, остатки/сроки,
  расписание, факт приёма (принято/пропущено/перенесено/неизвестно), напоминания о запасе,
  экспорт списка и истории для врача. **Без игровой интеграции.**
- **Health/Cycle** — состояния, сон, энергия, анализы (с исходным диапазоном лаборатории),
  Cycle (факт/расчёт, фаза ≠ факт). Только облегчающие сигналы для Tracker/Timer (PD-013).

### 3.10. Insights `[цель]` (4E)

Явно запрошенный анализ выбранных разделов/периода; объяснение использованных данных; корреляции
без причинности; возможность исключить чувствительный модуль.

### 3.11. Social `[есть, закрыт для внешних]`

Profile/alias, relationships/block graph, проекции (subject registry), verification, comments/
encouragement, moderation. Только `redacted projection`; исходная запись не раскрывается.
`Social off` не меняет Personal.

### 3.12. D/s capability grants `[позже]`

Manual Dominant Workspace (внешний submissive = локальная запись, не User) → transport adapters →
registered grants (object/field/action scope, caps/expiry/cooldown, audit/pause/revoke/block).
Запрет эскалации через Health и emergency stop.

## 4. Сечение данных (PD-012)

| Слой | Что | Правило |
|---|---|---|
| **Private Record** | исходная личная запись | виден только владельцу |
| **Shared Dynamic Record** | договорённость/задание/событие Dynamics | виден участнику Dynamics |
| **Shared Artifact** | намеренно переданный отчёт/медиа | виден получателю до отзыва |
| **Published Projection** | неизменяемый redacted snapshot | виден по выбранной видимости |

Детали retention/export/delete/derivatives — `DATA_LIFECYCLE.md`.

## 5. Межмодульные контракты (допустимые связи, PRODUCT_VISION §16)

Связь идёт через **ID + проекцию + adapter**, а не через прямой доступ к таблицам чужого модуля.

| Источник → получатель | Допустимое влияние |
|---|---|
| Tracker → Personal Care | включить уходовую процедуру в план/сценарий |
| Chastity Timer → Personal Care | гигиеническое окно / обслуживание устройства |
| Health → Tracker/Timer | открыть окно, смягчить, пауза, остановить (только облегчение) |
| Sexual Journal ↔ Cycle | сопоставить факты/ощущения/фазу |
| Training ↔ Nutrition | сопоставить план/факт/энергию/восстановление |
| Social → Personal | только проекция + allowlisted действие |
| D/s → Personal | только действие внутри принятого гранта |
| Insights → несколько разделов | явно запрошенный анализ выбранных данных |

Запрещено: Health ↔ penalty engine; любой модуль ↔ чужие таблицы напрямую; LLM как источник
правил/прав.

## 6. События и adapters

- **Outbox** — единый надёжный транспорт событий (`lock_outbox_events` уже есть для Timer;
  цель — общий `platform outbox` для всех модулей, откуда читают notification/push/Telegram/export).
- **Notification dispatch** — одна точка (`gamification/handler.py` → `app/push.dispatch_push`);
  новые модули регистрируют свои типы уведомлений там же, не плодят собственных отправителей.
- **Adapters** — маленькие stateless функции, которые превращают доменное событие в проекцию
  для другого контура (Social adapter, D/s adapter, Today adapter). Они не содержат бизнес-логики.
- **Background jobs** — `app/services/scheduler.py` (параметр tz: `TG_AUTO_ANALYSIS_TZ`), Timer jobs.
  Новые периодические задачи (напоминания о лекарствах/запасе) регистрируются в том же планировщике.

## 7. Транспорты

| Транспорт | Статус | Назначение |
|---|---|---|
| Web (SSR Jinja + HTMX) | есть | основной интерфейс |
| Personal Telegram | есть | личный клиент: Today, Timer, отметки, напоминания; не социальный бот |
| Push (FCM/APNs) | шов есть, сендеры по кредам | мобильные уведомления |
| JSON API v2 + bearer | есть (M4) | мобильный/нативный клиент |
| External transport adapters | позже | D/s-каналы (Telegram/e-mail), поверх ручного режима |

## 8. Мобильный API-контракт

- **Единый префикс** `api/v2/`, **JSON-first**, **bearer-auth** (`Authorization: Bearer <access>`).
- **Dual-mode** для action-эндпоинтов: bearer → JSON, HTML-форма → redirect (HTMX).
  Хелпер `app/api/responses.action_response`.
- **Auth**: `POST /api/v2/auth/token|refresh|revoke`, `GET /tokens`, `GET /me`.
  Refresh — rotation+revoke, SHA-256 в БД, sliding 30 дней.
- **Push**: `POST /api/v2/push/devices` (register upsert / list / deactivate / delete).
- **Media**: `GET /api/v2/media/{id}` + `/thumbnail` по bearer.
- Новые модули M3 обязаны: JSON-first + bearer + dual-mode + i18n + tests, без cookie-зависимостей.

## 9. Миграции, feature flags, rollout

- Одна Alembic-линейка, **single head обязателен** (проверяется в CI).
- Каждый новый модуль получает свой **feature flag** в composition (например `medication_enabled`),
  чтобы поставка была вертикальным срезом без блокировки остальных модулей.
- Rollout всегда: модель → миграция → сервис (commit только в сервисах) → API → UI →
  Telegram → тесты → функциональный inventory (`FUNCTIONAL.md`).
- **Не начинать новый крупный модуль при красном baseline** (ROADMAP §12).

## 10. Совместимость и не-регрессия

- Рефакторинг (разбиение файлов на пакеты) сохраняет публичный контракт через re-export.
- Legacy `db.commit()` в старых роутерах — осознанный долг; новые роутеры коммитят только в сервисах.
- `datetime.now(UTC)` + tz-хелперы (`app/timeutils.py`) для границ суток и сравнений; отображение —
  в tz устройства (`device-tz`).
- UI: PracticeLoop icon pack (`design/icons/`) — единственный источник иконок; токены `DESIGN_V2.md`.
