# Practice Loop — текущий функционал (v0.8.1-actual)

> Живой документ. Описывает **фактическое состояние** кодовой базы (v0.8-actual),
> а не целевую спецификацию (v0.7-spec / REMEDIATION_SPEC.md).
> Исторические расхождения «спека ↔ код» зафиксированы в ADR-029…034; текущие ограничения отмечены явно в разделах модулей
> и сводной таблице в `AGENTS.md` §0. Обновлять при значимых изменениях функционала.

---

## 1. Что это

Приватное веб-приложение для отслеживания и управления активностями в личных/парных
отношениях (только для взрослых, по обоюдному согласию): каталог задач, сессии, история,
геймификация (XP, баллы, штрафы), LLM-подбор задач, тренировочные программы, диеты с
LLM-контролем, календарь доступности, замеры, инвентарь, Telegram-бот, персональный
Lock Timer (chastity) и социальная платформа (обезличенный обмен результатами).

**Один пользователь, приватное использование.** Модель данных поддерживает
межпользовательское взаимодействие (публичный каталог с авторством, опт-ин), но
основной сценарий — single-user.

---

## 2. Технологический стек

| Слой | Технология |
|---|---|
| Backend | Python 3.11+, FastAPI (async), Pydantic v2 |
| DB | PostgreSQL 15 (prod), SQLite (dev/tests), SQLAlchemy 2.0 async, Alembic |
| Auth | JWT-cookie + CSRF double-submit (native-формы и JS-fetch покрыты) |
| Frontend | SSR Jinja2 + HTMX + TailwindCSS, Chart.js; JS вынесен в ES-модули |
| i18n | EN/RU, темы dark/light/system + 3 акцентных набора (ember/sage/slate) |
| LLM | OpenAI-совместимые endpoints, BYOK: Omniroute (по умолчанию), Groq, OpenRouter |
| Telegram | aiogram 3.x (вебхук + исходящие уведомления) |
| Инфра | Docker Compose (app, PostgreSQL, Nginx+SSL), загрузки в volume `uploads` |
| Время | Всё хранится в UTC; отображение и границы суток — в часовом поясе устройства (cookie `client_tz`); фоновые job — `TG_AUTO_ANALYSIS_TZ` |
| API | Все JSON-эндпоинты консолидированы под `/api/v2`; SSR-страницы по своим путям (`/locktimer`, `/social`, …) |

---

## 3. Страницы и навигация

Боковая панель (sidebar) с группировкой, сворачивается/разворачивается и отражает
feature flags (composition):
- **Сейчас**: Сегодня (дашборд) · Задачи · Сессии
- **Личное**: Каталог · Тренировка · Диеты
- **Данные**: Инвентарь · Замеры · Лекарства · Расписание · Зоны тела · Календарь · Баллы ·
  Достижения · Медиа · Импорт
- **Система**: Уведомления · LLM · Приватность · Админ · Настройки
- (при `timer_operational`) **Личное**: Таймер замка; (при `social_operational`)
  **Связи**: Социалка.

Мобильная версия — нижняя навигация; desktop — свёрнутый рейл (иконки) / развёрнутый
sidebar (иконки + подписи).

| Страница | Что делает |
|---|---|
| `/` (index) | Обзор, переход на дашборд/логин |
| `/dashboard` | Дашборд v2: статистика, XP, уровень, серии, графики активности/точек/XP/категорий, completion rate |
| `/tasks` | Задачи на сегодня: генерация (LLM/детерминированная), завершение, прерывание |
| `/training` | Тренировочные дни: планы с подзадачами, журнал по временным окнам, анализ дня LLM, параллельные планы, фото-отчёты |
| `/catalog` | Каталог активностей: системные + пользовательские, опт-ин, риск-уровни |
| `/my` (my_entities) | Личные активности: создание, публикация, удаление |
| `/points` | Баллы v2: баланс, транзакции, списание, профили, отработки штрафов |
| `/admin` | Админка: seed каталога и LLM-пресетов |
| `/llm-configs/` | BYOK-конфиги провайдеров, активный конфиг, режимы full/abstract, хранение raw; доступен во всех вариантах продукта |
| `/onboarding` | 4 шага первого запуска: режим AI (`none`/`portal`/`personal`), выбор модулей, опциональная настройка LLM и завершение через consent; portal quick-pick возвращает в мастер |
| `/measurements` | Замеры тела (утро/вечер), графики |
| `/medications` | Medication Organizer: лекарства/аптечки/остатки/расписание/факт приёма, экспорт для врача (§22) |
| `/health` | Health + Cycle foundation (4D): ежедневный check-in (настроение/энергия/сон/симптомы), анализы с оригинальным диапазоном, цикл с расчётной фазой (§23) |
| `/inventory` | Инвентарь: предметы, фото, сортировка drag&drop, shopping list |
| `/schedule` | Правила расписания дня (day_of_week + время + тип задачи + recurring) |
| `/import` | Импорт/экспорт данных: CSV/JSON шаблоны, upload, API-push, полный экспорт |
| `/calendar` | Шаблоны доступности (allowed/disallowed/passive_only) + отпуска-оверрайды |
| `/diets` | Диеты: планы, позиции (drag&drop), журнал потребления, LLM-генерация/оценка, синергия с тренировками, фото |
| `/sessions` | Сессии: создание, задачи, одноразовое принятие, старт/завершение, freeze и append-only аудит; изменения после принятия штрафуются |
| `/notifications` | In-app уведомления, отметка прочитанным |
| `/achievements` | Доска достижений (обезличенная), скрытие |
| `/privacy` | Versioned полный owner-scoped manifest Personal-данных без секретов, удаление аккаунта, статус Telegram-привязки |
| `/settings` | Кастомизация: тема (dark/light/system), акцент, плотность, блоки дашборда, discretion (ADR-081) |
| `/account` | Профиль аккаунта: email, роль, дата создания, часовой пояс и переходы к паролю/приватности |
| `/admin/users` | Admin-only роли, блокировка/разблокировка и явный reset пароля пользователей (§36) |
| `/consent` | Неизменяемая история согласий; grant/revoke по purpose и версии условий (§35) |
| `/aftercare` | Структурированный relief-only журнал восстановления и дебрифа (§34) |
| `/locktimer` | Lock Timer: обзор, детали сессии, шаблоны (§16) |
| `/social/*` | Социальная подсистема: профиль, связи, лента, верификация, модерация (§17) |
| `/health/dashboard` | Health & Cycle Dashboard: визуализация BodyCycleLog и процедур ухода (§43) |
| `/achievements/quests` | Quests Hub: интерактивный квест-хаб, прогресс, claim наград (§44) |
| `/billing` | Billing Showcase: тиры подписки, акции, мульти-гейтвей чекаут, инвойсы (§45) |
| `/communities/{id}/agent` | Community Top Agent: персона, турниры, делегирование блоков профиля (§46) |
| `/communities/{id}/cockpit` | Community Cockpit: управление агентом и делегированиями (§46) |
| `/llm/exchange` | LLM Exchange Hub: экспорт кросс-доменного промпта, парсинг ответа внешней ИИ (§47) |
| `/insights/analytics` | Analytics Cockpit: 10-модульный корреляционный движок (§48) |
| `/analytics/graph` | Интерактивный граф корреляций: матрица + кластеры (§48) |
| `/insights/trajectory` | Траектория развития: динамика метрик по времени (§48) |
| `/insights/report`, `/insights/export-medical` | Отчёт по инсайтам, медицинский экспорт (§48) |
| `/ds/keyholder` | Keyholder Dashboard: управление сабмиссивами (§49) |
| `/ds/portal` | D/s Command Center: мульти-сабмиссивный портал, чек-ины, когортная аналитика (§49) |
| `/ds/my-top` | Портал Нижнего: гранты делегирования, safe-word revoke (§49) |
| `/ds/checkins` | Wear Check-Ins: инспекция номерных пломб (§49) |
| `/agent/persona-builder` | Конструктор ИИ-Персоны (§40.1) |

---

## 4. Каталог активностей (Entity)

Единая модель «базовая активность + шаблон параметров + экземпляр» (ADR-031):
**не создаются** справочные записи под каждую комбинацию параметров.

- **Поля**: `real_name`, `slug` / `short_title`, `type` (one_time / series / infinite),
  `category` (строка, legacy) + `category_id` (FK → `activity_categories`, 16 категорий
  с подкатегориями), `tags` / `role_tags`, `level`, `intensity` (active/passive/neutral),
  `params_schema` (JSON: диапазоны и фиксированные значения), `risk_level`
  (not_assessed / low / elevated / high), `penalty_enabled` (ADR-038),
  `gamification_config` (JSON: баллы, бонусы, штрафы, пороги), `is_public`,
  `owner_id`, `author_id`, `parent_id` (иерархия).
- **Наполнение**: админ-сид (30+ задач) + пользовательские; публикация с авторством.
- **Текущее production-состояние (S8a)**: legacy admin seed из 30 бытовых/романтических действий
  удалён после backup; `entities=0`. Новый starter set проектируется как отдельный вручную
  модерируемый каталог строго для взрослых; до его принятия legacy seed повторно не запускать.
- **Опт-ин** (`user_entity_opt_in`): пользователь осознанно отмечает допустимые задачи
  (да/нет + рейтинг + шкала желания).
- **Одобрение (ADR-106)**: опт-ин пользователя — граница автоматизации по умолчанию;
  `risk_level` / `automation_allowed` — информационные метаданные (показываются пользователю,
  не блокируют автоматический выбор из опт-ин набора).

---

## 5. LLM-пайплайн

### Первый запуск и выбор LLM

Онбординг начинается с выбора уровня участия AI: `none` полностью скрывает настройку LLM и оставляет ручной режим, `portal` предлагает deployment-managed провайдеров, а `personal` открывает пользовательские BYOK-настройки. После выбора модулей LLM-шаг показывается только для двух включённых режимов. Portal quick-pick использует CSP-safe форму с CSRF и возвращает пользователя на шаг 3; подписи и описания режима/модулей локализуются через EN/RU.


```
Каталог Entity → опт-ин → Context Builder (история, статистика, штрафы, расписание дня, календарь)
  → LLM (полный/abstract контекст) → JSON → json_repair → Pydantic-валидация → ActivityLog
```

- **Гибридная генерация**: LLM НЕ генерирует контент — только выбирает из допустимого
  набора (опт-ин) и задаёт параметры в диапазонах `params_schema`.
- **Режимы (ADR-030)**: `full` (LLM видит названия) и `abstract` (opaque ID, только
  позиции — для провайдеров со строгими фильтрами). Промпт и training-пайплайн
  уважают режим.
- **Обработка ошибок**: `json.loads` → `json_repair` → regex-извлечение → после 3
  неудач — ошибка + кнопка «Повторить» (без шаблонной подстановки).
- **Безопасность**: `entity_name` из LLM заменяется каноническим серверным; entity_id
  обязан быть в allowed-наборе (чужой private отклоняется); params — против схемы;
  subtasks санитизируются (только строки, ≤20 шт., ≤500 симв.).
- **Tool calling** (опция): `save_activity_log`, `get_user_stats`, `apply_penalty`.
- **Биллинг**: usage-метрики (токены, стоимость) хранятся всегда; `raw_llm_response` —
  опционально (ADR-034), с TTL-очисткой (scheduler каждые 6 ч).
- **JSON repair**: `json_repair` + regex-фолбэк.

**LLM-функции**: `generate_task`, `generate_daily_plan` (план дня), `analyze_training_day`
(анализ тренировки), `generate_diet` / `evaluate_diet` (диеты), `analyze_diet_training_synergy`
(синергия диеты ↔ тренировки).

**Промпт-шаблоны** (ADR-070, Шаг 6): пользовательские приватные `prompt_templates`
(typical prompts / parameterized templates) — библиотека переиспользуемых промптов
по функциональным блокам, доступна через `/llm/templates`.

---

## 6. Задачи (ActivityLog)

Экземпляр активности. Строгая статус-машина из 11 состояний (ADR-040):
`draft` / `planned` / `in_progress` / `completed` / `partially_completed` / `skipped` /
`cancelled` / `stopped` / `substituted` / `not_applicable` / `review_needed`
(legacy `pending`→`planned`, `interrupted`→`stopped`); переходы контролируются
`STATUS_TRANSITIONS`, аудит — `activity_task_history`.

- `entity_id`, `session_id`, `training_day_id`, `user_prompt`, `selected_params`
  (параметры задачи), `planned_value` / `actual_value`, `subtasks` (чек-лист),
  `completed_at`, `penalty_applied` / `penalty_details`, `points_awarded`,
  usage-метрики LLM.
- **Генерация**: `/tasks/generate` (LLM) или `/tasks/generate-deterministic`
  (детерминированный выбор по расписанию).
- **Завершение/прерывание**: атомарные гарды `complete_once` / `interrupt_once`
  (UPDATE WHERE status=…, повторные вызовы идемпотентны; прерванную нельзя завершить
  для награды). Остановка доступна всегда; последствия определяются настройками активности и профилем геймификации (ADR-029).

---

## 7. Сессии (ActivitySession)

Объединение задач под общими правилами:

- Статусы: `created` / `active` / `ended`; `session_rules` (JSON: штрафы, лимиты,
  получатели уведомлений, эскалация, параллельные задачи).
- `POST /sessions`, `/sessions/{id}/start`, `/sessions/{id}/end`.
- Завершение сессии не требует выполнения всех задач.

---

## 8. Тренировки (Training)

Отдельная система «программ» (ADR-032, ADR-039):

- **TrainingDay**: план на дату, статусы planned/active/completed/analyzed,
  `plan_summary`, `analysis_summary`, `next_day_suggestion` (предложение LLM на завтра),
  имя плана (параллельные планы в день), `completed_at`, `analyzed_at`.
- **TrainingLogEntry**: журнал по временным окнам (time_label, entry_type:
  fluid_intake/micro_leak/pressure_check/general_note), planned vs actual, inline-редактирование,
  drag&drop сортировка, ad-hoc записи (is_extra).
- **Подзадачи**: чек-лист с toggle в ActivityLog.subtasks.
- **Анализ дня**: LLM-анализ с корректировкой плана на завтра; повтор не блокируется
  (leftover-пустые планы удаляются); пустые планы не коммитятся при ошибке LLM.
- **Фото-отчёты**: attachments на карточках задач.
- **Timeline**: общая шкала дня (журнал всех планов + правила расписания).

---

## 9. Диеты (Diet)

- **Diet**: направление (`direction`: weight_loss / muscle_gain / health / …),
  активность (несколько активных комбинируются), LLM-оценка (`last_evaluation`,
  `evaluated_at`), фото.
- **DietItem**: позиции плана (что + сколько + когда + приём пищи + заметки),
  drag&drop reorder, inline-редактирование.
- **DietConsumption**: фактическое потребление (журнал питания, лимит 200 записей).
- **LLM**: `generate_diet` (санитизация: ≤20 позиций, длины, qty>0), `evaluate_diet`
  (score 0-100, findings, adjustments add/modify/remove по точному имени).
- **DietEvaluation**: история оценок (все оценки сохраняются, сортировка по времени).
- **DietTrainingReview**: синергия диеты ↔ тренировки (направления влияния,
  корректировки ≤8, summary ≤5000), история обзоров.
- **Загрузки**: /attachments owner_type=diet (миниатюры, удаление).

---

## 10. Геймификация

### XP и уровни (формула задокументирована в tracker-spec §9.5)
- `base = BASE_XP[тип]` (one_time: 25 · series: 50 · infinite: 15)
- `+ streak_days × 5` (серия), `+ base × min(combo × 0.10, 0.50)` (комбо), `+ base × (intensity−1) × 0.10`
- Пороги уровней: 0 → 100 → 250 → 500 → 1000 → 1750 → 2750 → 4000 → 5500 → 7500 →
  10000 → 13000 → 16500 → 20500 → 25000, далее +2500/уровень.
- Штраф: `base_penalty = 25 XP` × эскалация `1.0 + (n−1)×0.5` (потолок ×5), XP не ниже 0,
  комбо сбрасывается. Серии: +1 раз в календарный день, сброс при пропуске >1 дня.
- Points v2 независим от XP (начисляется по gamification_config отдельно).

### Points v2 (документация: tracker-spec §9.9)
- `gamification_config` на сущности: `points` (base, max_per_day, profile_id),
  `bonuses` (условные, typed DSL — whitelist операторов, без eval), `penalties`
  (уровни с эскалацией и redemption), `thresholds` (negative/warning/good + уведомления).
- **PointsTransaction**: earn/redeem/penalty/bonus, уникальная привязка к
  `activity_log_id` (защита от двойного начисления).
- **PointsProfile**: переиспользуемые шаблоны баллов/штрафов/бонусов, назначаются на сущность.
- **PenaltyRedemption**: отработка штрафа pending → completed (возврат баллов) / skip.
- **Threshold effects**: уведомления при пересечении порогов.

### Достижения
- Achievement + UserAchievement (код, условия, контекст получения); обезличенная
  доска с ником; скрытие достижений; достижения за серии (3/7/14/30/100 дней).

---

## 11. Календарь и расписание

- **CalendarTemplate + AvailabilityWindow**: недельные окна с политиками
  allowed / disallowed / passive_only.
- **CalendarOverride**: отпуск/особые дни (шаблон «Vacation»).
- **Entity.intensity**: active/passive/neutral — может обходить ограничения календаря.
- **`is_available()`** утилита; интеграция в LLM-контекст (окна + политики + intensity).
- **ScheduleRule**: day_of_week + time + task_type + recurring → детерминированная
  генерация задач (`/schedule/today`, `/tasks/generate-deterministic`), due-даты,
  retry-блоки (`set_next_due`, `set_retry_block`).

---

## 12. Замеры, инвентарь, импорт/экспорт

- **BodyMeasurement**: замеры тела (утро/вечер), графики Chart.js.
- **InventoryItem**: предметы, категории, фото (загрузка/удаление), drag&drop,
  shopping list.
- **Импорт**: CSV/JSON шаблоны (скачивание), upload с drag&drop-зоной, API-push,
  upsert; экспорт по типам + полный экспорт; CLI `import`/`export`/`template`.
- **Загрузки**: app/services/uploads.py — валидация content-type + magic-bytes,
  лимит 8 МБ, защита от path traversal, volume `uploads`.

---

## 13. Telegram-бот (aiogram 3.x)

Вебхук + исходящие уведомления. Команды: `/start`, `/link` (привязка по 6-значному коду,
сессия 30 мин), `/next`, `/tasks`, `/done`, `/interrupt` (с подтверждением), `/stats`,
`/session`, `/settings` (EN/RU), таймер `/lock*` (§30) и личный контур `/med`,
`/health`, `/cycle`, `/care` (§31). Inline-кнопки ✅ Done / ⏹ Interrupt. Бот вызывает
внутренние сервисы напрямую (не HTTP); уведомления — хук после каждого db.flush().

---

## 14. Аутентификация, безопасность, приватность

- Регистрация email+пароль (без подтверждения), JWT-cookie, CSRF double-submit
  (все native-формы с hidden token, JS-fetch с X-CSRF-Token; /uploads — CSRF-bypass).
- Cookies Secure в production; logout только POST; пароли в .env, шифрование API-ключей.
- **Bearer-auth для API-клиентов (Mobile Foundation, M4)**: JSON-эндпоинты
  `POST /api/v2/auth/token` (email+пароль → access+refresh), `/refresh` (ротация),
  `/revoke`, `GET /tokens` + `POST /tokens/{id}/revoke` (список/отзыв по устройству),
  `GET /me`. Access — короткоживущий JWT с claim `type=access` (header
  `Authorization: Bearer`); refresh — непрозрачный, хранится только SHA-256-хэш,
  ротируется при каждом использовании, revocable (`api_tokens`). CSRF для
  bearer-запросов не требуется (нет cookie-сессии).
- **Self-service смена пароля**: `/settings` требует текущий пароль, новый пароль 6–128 символов
  и подтверждение; после успешной смены все mobile refresh-токены пользователя удаляются, а
  текущая browser access-сессия остаётся активной.
- **Приватность**: экспорт данных (JSON), полное удаление аккаунта или с сохранением
  обезличенных данных; обезличенная доска достижений.
- **Durable consent (ADR-102/104)**: согласие выдаётся один раз на конкретные purpose и
  `terms_version`, действует до явного отзыва и не запрашивается повторно при простом выключении/
  включении уже согласованного модуля. Первый вход запрашивает активные модули, новый модуль — при
  его включении в профиле. История append-only; revoke — новая версия и немедленный gate.
- **BYOK disclosure**: перед сохранением пользовательского LLM-провайдера отдельно раскрывается,
  что endpoint, модель и ключ принёс пользователь и он отвечает за выбор провайдера, его ToS,
  тарифы и допустимость отправляемых данных. Портал не снимает собственные policy/safety gates.
- Cross-user изоляция: чужие private entities/thresholds не видны; импорт ищет Entity
  только owner/public.

---

## 15. Модель данных (таблицы)

Перечень основных таблиц `app/models/*` (фактическая схема развивается миграциями):

- **Пользователи и каталог**: `users`, `user_progress`, `entities`, `user_entity_opt_ins`,
  `activity_categories`, `llm_provider_configs`, `prompt_templates`.
- **Мобильный фундамент (M4)**: `api_tokens` (refresh-токены), `push_devices`.
- **Medication Organizer (M3, §22)**: `medications`, `med_kits`, `med_stocks`,
  `med_schedules`, `med_intakes` (relief-only, без игровой интеграции — PD-013).
- **Health + Cycle foundation (M3, §23)**: `health_states` (check-in: настроение/энергия/сон/
  симптомы/восстановление), `lab_records` (анализы с оригинальным диапазоном лаборатории),
  `cycle_settings` (одна строка на пользователя), `cycle_events` (факты цикла) — relief-only, PD-013.
- **Sexual Journal (M3, §24)**: `sj_partners` (локальные псевдонимы партнёров),
  `sj_entries` (записи журнала: факт/ощущения/реакции/aftercare, снимок фазы Cycle,
  мягкие связи с Timer/Health по ID) — relief-only, PD-013, Private Record.
- **Personal Care (M3, §25)**: `care_routines` (каталог процедур/рутин: зона, тип,
  частота, заметки), `care_entries` (факты выполнения: дата, длительность, реакция
  кожи, снимок фазы Cycle), `care_products` (каталог средств/косметики: остаток,
  срок, привязка к инвентарю и универсальному каталогу), `care_entry_products`
  (средства, использованные в записи ухода), `care_routine_products` (рекомендуемые
  средства для процедуры), `care_courses` (курс из N сеансов), `care_course_sessions`
  (сеансы курса) — relief-only, PD-013, Private Record.
- **Reminders (§29)**: `reminder_log` (дедупликация напоминаний: медикаменты/средства/
  уход/курсы/таймер) — relief-only, PD-013.
- **Consent (§35)**: `consent_records` — append-only журнал granted/revoked с монотонной
  версией и `terms_version`.
- **Timer care/check-ins (§33)**: `chastity_device_events`, `chastity_check_ins`.
- **Aftercare (§34)**: `aftercare_entries` — Private Record, relief-only.
- **Универсальный каталог активностей (§26)**: `activity_catalog` — сквозной
  справочник видов активностей (как Entity: категория/теги/описание/domains),
  на который ссылаются журнал, уход, окна таймера и трекер-задачи — нейтрален,
  relief-only, PD-013.
- **Personal Insights (M3, §27)**: `insight_runs` (запуск кросс-модульного
  анализа: период, выбранные разделы, статус, usage), `insight_findings`
  (находки по разделу с used_data) — relief-only, PD-013, Private Record.
- **Задачи и сессии**: `activity_logs`, `activity_task_history`, `activity_sessions`.
- **Тренировки и диеты**: `training_days`, `training_log_entries`, `diets`, `diet_items`,
  `diet_consumptions`, `diet_evaluations`, `diet_training_reviews`.
- **Геймификация и баллы**: `points_transactions`, `points_profiles`, `penalty_redemptions`,
  `achievements`, `user_achievements`.
- **Календарь и расписание**: `calendar_templates`, `availability_windows`, `calendar_overrides`,
  `schedule_rules`.
- **Замеры, инвентарь, медиа**: `body_measurements`, `inventory_items`, `inventory_categories`,
  `attachments`, `media_assets`, `media_verification_results`, `verification_challenges`.
- **Справочники (update2.md)**: `body_parts`, `task_body_targets`, `task_locations`,
  `task_location_usages`, `activity_location_requirements`, `task_inventory_usages`,
  `activity_inventory_requirements`, `activity_body_part_requirements`.
- **Уведомления**: `notifications`.
- **Lock Timer** (bounded context, см. §16): `lock_sessions`, `lock_timer_templates`,
  `lock_session_snapshots`, `lock_inner_periods`, `lock_slot_rules`, `lock_slot_occurrences`,
  `lock_task_rules`, `lock_task_occurrences`, `lock_penalty_events`, `lock_tag_violations`,
  `lock_llm_proposals`, `lock_audit_events`, `lock_job_receipts`, `lock_outbox_events`.

Таблицы Social (`app/platform/social/models.py`) перечислены в §17.

Таблицы новых модулей v0.8.1:
- **Quests (§44)**: `quests`, `user_quests` (миграция 072).
- **Billing (§45)**: `subscription_tiers`, `tier_feature_grants`, `temporary_feature_promotions`,
  `payment_invoices`, `promo_codes` (миграции 082 и последующие изменения).
- **Community (§46)**: `communities`, `community_posts`, `community_top_agents`,
  `community_member_delegations`, `community_tournaments`, `community_tournament_entries`,
  `community_member_roles` (миграции 082–083 и последующие изменения).
- **Automation (§46)**: `automation_triggers` (миграция 082).
- **Media Vault v2 (§51)**: `one_time_media_tokens` (миграция 082).
- **Адаптивные программы (§38.1)**: `adaptive_programs`, `adaptive_program_steps` (миграция 074).
- **Обслуживание инвентаря (§38.4)**: `equipment_maintenance_logs` (миграция 076).
- **D/s-делегирование (§49)**: `managed_submissives`, `assigned_duties`, `chastity_lock_logs`,
  `capability_grants`, `capability_grant_claim_attempts`, `wear_check_in_logs`
  (миграции 077–081).
- **AI-персоны (§40)**: `user_agent_personas` (миграция 082); **Лиги/Дуэли (§39)**:
  `user_league_tiers`, `user_duels` (миграция 082).

---

## 16. Lock Timer — персональный таймер закрытия (chastity, ADR-062)

Отдельный bounded context (`app/locktimer/` — domain/services; таблицы `lock_*`
в `app/models/locktimer.py`). Включается флагом
`LOCKTIMER_CORE_ENABLED=true`. Доступен на странице `/locktimer`.

### Модель (14 таблиц `lock_*`)
- **LockTimerTemplate**: сохранённый шаблон сессии (name, description, config JSON,
  sort_order, archived_at).
- **LockSession**: draft → active → completed / safety_stopped (реализованный
  жизненный цикл; константы validating / cancelled_by_system зарезервированы, пока не
  задействованы). duration_type (fixed_dates / duration_from_start / infinite),
  timezone, requested_start_at / started_at / original_end_at / effective_end_at /
  max_end_at, can_extend_duration, merge_gap_seconds, random_seed (encrypted +
  commitment, детерминированная генерация), privacy_mode, row_version.
- **LockSessionSnapshot**: canonical_config JSON на момент старта.
- **LockInnerPeriod**: именованный под-период (rule_type + rule_data).
- **LockSlotRule**: 5 типов расписания (every_n_days, exact_datetime, recurring_from_date,
  flexible_window_once, after_previous_close). duration_seconds, allow_late_open,
  max_late_seconds, extend_on_late_open, require_close_media, close_grace_seconds,
  late_close_policy, require_tag.
- **LockSlotOccurrence**: pending → eligible → open → closed (+ overdue_open расчётный,
  missed, blocked, cancelled). planned_open/close_at, eligible_from/until, close_due_at,
  actual_opened/closed_at, extension_applied_seconds, close_tag_number.
- **LockTaskRule**: 6 типов расписания (daily, every_n_days, recurring_from_date,
  exact_datetime, anytime_before_end, deterministic_random). source_entity FK,
  due_window_seconds, hide_until_due, requires_report, media/verification/penalty/
  availability policies.
- **LockTaskOccurrence**: scheduled → visible → submitted → verifying → completed /
  review_required / failed / skipped / expired / safety_cancelled. appears_at, due_at,
  content_visible, occurrence_snapshot, revealed_at, finalized_at.
- **LockPenaltyEvent**: penalty_type (add_time / block_next_slot / mark_task_failed /
  points), state (applied / capped_noop / rejected / superseded), idempotency_key.
- **LockAuditEvent**: append-only аудит (actor, event_type, object, from/to_version, payload).
- **LockJobReceipt**: durable фоновые job (state pending/running/done/failed/dead, lease).
- **LockOutboxEvent**: транзакционные domain-события (state pending/published/failed).
- **LockLlmProposal**: AI-предложения правил (kind: pre_start_plan / hidden_reveal /
  anchor_fill; status pending/partial/applied/rejected; items JSON; usage-метрики).
- **LockTagViolation**: запись расхождения номерной бирки при verify (reason mismatch /
  missing_required).

### Действия
- **Создание**: POST /locktimer/new → draft с правилами слотов/задач (JSON-расписания)
- **Старт**: атомарный переход draft→active + снапшот + материализация слотов/задач на 90 дней
- **Выполнение**: открытие/закрытие слотов, reveal/complete/skip задач
- **Safety stop**: экстренная остановка с отменой будущих occurrences
- **Бирки**: опциональная нумерация при закрытии слотов, verify-tag + violation audit
- **Валидация**: pre-start conflict check (пересечение слотов, распределение задач)
- **Расширение**: extend horizon — материализация на следующие 90 дней
- **Шаблоны**: сохранение draft как шаблона, инстанциирование
- **Countdown**: JS-таймер реального времени (HH:MM:SS) до effective_end_at

### Страницы
- `/locktimer` — обзор (активная сессия, слоты, задачи, черновики, история)
- `/locktimer/sessions/{id}` — детали (info grid, правила, occurrences, proposals)
- `/locktimer/templates` — сохранённые шаблоны

### Интеграция
- Dashboard: карточка активного таймера (amber-тема, duration/TZ/slots/tasks/end)
- LLM: timer-aware context builder → proposals API
- Media: универсальная медиа-система (platform-level, shared с Tracker)

---

## 17. Platform Social — социальная подсистема

Общая capability-based подсистема (`app/platform/social/`). Включается флагом
`SOCIAL_ENABLED=true`. Не импортирует Tracker/Timer — взаимодействует через адаптеры.

### S0 — Identity
- **SocialProfile**: публичная личность (alias 3-80 chars, case-insensitive unique),
  bio, настройки приватности (discoverable, show_in_feed).
- **SocialConsent**: версионированное согласие (adult attestation + privacy terms).
- Страницы: `/social/profile` (создание/редактирование), `/social/privacy` (публичная).

### S1 — Subject Registry
- **SocialSubject**: opaque registry для domain объектов. subject_type (tracker.* / timer.*),
  domain_object_id, projection_snapshot + version, lifecycle (active/tombstoned).
- **SocialSubjectAdapter Protocol**: 14 методов (authorize, build_redacted_projection,
  list_shareable_capabilities, validate_grant_constraints, execute_authorized_action, …).
- **Adapter registry**: register_adapter / get_adapter_registry.
- Страницы: `/social/subjects`, `/social/api/capabilities`.

### S2 — Relationships & Grants
- **SocialRelationship**: invitation lifecycle (pending→accepted/declined/expired/revoked),
  display_role presets (viewer/coach/mentor/curator), cooldown 24h.
- **SocialBlock**: cross-product block (shuts down all interactions immediately).
- **SocialGrant**: scoped capability grants (subject/module/global scope, JSON caps,
  propose→accept/revoke). Требует accepted relationship + recipient accept.
- **SocialNotification**: outbox (9 типов: invitation_*, grant_*, block_*, relationship_*).
- Страница: `/social/relationships` (pending invites, send form, active connections + grants,
  blocks, notification feed).

### S3 — Publications & Feed
- **SocialPublication**: immutable redacted snapshots. SHA-256 hash подтверждает целостность.
  visibility: relationship_only / unlisted / public. subject_namespace для фильтрации
  (tracker / timer). Активная → withdrawn (никогда не редактируется).
- **Feed**: cursor-based. Читает ТОЛЬКО таблицу `social_publications` — никогда не
  присоединяет приватные Tracker/Timer таблицы. Block-aware (исключает публикации
  заблокированных). Accepted-relationship gating для relationship_only.
- API: `/social/feed` (namespace filter), `/social/publish`, `/social/publish/{id}/withdraw`.
- Страница: `/social/feed` (publish form, feed с namespace tabs, own publications).

### S4 — Verification & Comments
- **SocialVerificationPolicy**: frozen policy snapshots (min_approvals, max_rejections,
  deadline_hours, no_quorum_action, require_reject_comment).
- **SocialVerificationRequest**: open → verified / review_required / failed / cancelled.
  Счётчики approvals/rejections, deadline. Владелец не может голосовать.
- **SocialVerificationVote**: approve / reject / abstain. One vote per verifier per request.
- **SocialComment**: plain text comment на publication или verification request.
  Edit + delete, is_edited tracking.
- **SocialEncouragement**: thumbs_up / support / celebrate / motivate.
  One per sender per target (уникальный constraint).
- Quorum: min_approvals → verified, max_rejections → review_required, deadline → no_quorum_action.
- API: `/social/verification`, verify/create, vote, comment CRUD, encourage.
- Страница: `/social/verification`.

### S5 — Moderation
- **ModerationReport**: abuse reports (profile/publication/comment/vote).
  7 reason codes: harassment, privacy, non_consensual, impersonation,
  dangerous_content, spam, other. States: open → reviewing → resolved / dismissed.
  Reporter identity НЕ раскрывается цели.
- **ModerationAction**: immutable append-only audit trail. 6 action types:
  hide_publication, hide_comment, invalidate_vote, resolve_report, dismiss_report,
  request_evidence. Каждое действие: moderator_id + reason + timestamp.
- Репозитории: hide_publication (is_active=False), hide_comment (body→[removed]),
  invalidate_vote (удаление + корректировка счётчиков).
- API: `/social/report` (любой пользователь), `/social/moderation` (admin-only очередь),
  assign, action.
- Страница: `/social/moderation` (состояние-бейджи, форма действий, лог).

### S6 — Domain Adapters
- **TrackerSocialAdapter** (14 методов протокола): authorize_subject (ActivityLog.user_id
  / Entity.owner_id), build_redacted_projection (strips raw_llm_response, penalty_details,
  user_id), list_shareable_capabilities (view_summary/view_details/verify),
  validate_grant_constraints.
- **TimerSocialAdapter**: skeleton (все методы реализованы, возвращают empty/not_implemented).
- Adapters регистрируются при старте через composition flags.

### S7 — Hardening & Limited Rollout
- 11 social concurrency tests: double-accept, invite+block race, feed isolation after
  moderation hide, grant idempotency, block propagation, cross-user isolation.
- 11 privacy audit tests: все social роуты просканированы на forbidden patterns
  (email, password_hash, raw_llm_response, penalty_details, ip_address, user_prompt).
- pre_deploy_check.sh §8: social privacy scan (grep-проверка утечек в social коде).
- DEPLOY_VPS.md §15: Social Ops Runbook (включение, hardening checks, troubleshooting).

### Social таблицы (в `app/platform/social/models.py`, 15 шт.)
`social_profiles`, `social_consents`, `social_subjects`, `social_relationships`, `social_blocks`,
`social_grants`, `social_notifications`, `social_publications`, `social_verification_policies`,
`social_verification_requests`, `social_verification_votes`, `social_comments`,
`social_encouragements` (все с префиксом `social_`), плюс модерация без префикса:
`moderation_reports`, `moderation_actions`.

---

## 18. Универсальная медиа-система

Platform-level (`app/api/media.py`, `app/api/verification.py`), общая для Tracker и Timer.

- **media_assets**: owner-scoped (owner_type/owner_id), staged→ready→archived pipeline,
  MIME+magic-bytes validation, SHA-256, thumbnail (Pillow LANCZOS 400x400).
- **verification_challenges**: одноразовые коды, HMAC-SHA256 (plaintext не хранится),
  constant-time сравнение, TTL, max_attempts, алфавит без O0I1l.
- **media_verification_results**: результат LLM-оценки фото (ADR-075, Шаг 7) —
  вердикты code_match / chastity_closed; это вспомогательное доказательство,
  авторитетное завершение по-прежнему HMAC-челлендж (автозавершение — только при
  явном включении владельцем).
- API: upload (multipart 15MB), finalize, serve (nosniff+no-store), thumbnail, delete;
  create/verify/status challenge.

---

## 19. Дата и время (часовые пояса)

- **Хранение**: все даты/время в UTC (`DateTime(timezone=True)`); в тестах SQLite — naive
  datetime, нормализация через `as_utc()`.
- **Отображение**: в часовом поясе устройства — Jinja-глобал `localtime()` + JS
  `applyLocalTimezones()`; браузер определяет tz через `Intl` и передаёт cookie `client_tz`.
- **Границы суток**: «сегодня» (серии, графики, календарь, расписание, диеты) считается
  по часовому поясу устройства (`local_today()` / `local_date()` через ContextVar).
- **Графики**: дневные бары бакетируются по device-календарному дню (ADR-066), а не по
  UTC-дню БД.
- **Фоновые задачи** (автоанализ тренировок): часовой пояс — конфиг `TG_AUTO_ANALYSIS_TZ`
  (по умолчанию UTC), т.к. у фонового job нет request-контекста.

## 20. Кастомизация и discretion (DESIGN_V2 §12/§16, ADR-081/082)

- **Хранилище**: `users.prefs` JSONB (миграция 039) + `app/prefs.py` — типизированный
  `UserPrefs` (валидация, дефолты, ContextVar). Инъекция в шаблоны через auth-зависимости
  + контекст-процессор (хендлеры не тронуты).
- **Ключи** (все опциональны, fallback на дефолты): `accent` (ember/sage/slate),
  `density` (comfortable/compact), `dash_blocks` (order + hidden; блоки header/stats/
  charts/summaries/xp/quick/today/timer), `discretion` (mode off/always/schedule +
  start/end-окно), `blur` (0/1/2), `theme_choice` (dark/light/system).
- **Тема system**: JS-резолв через `matchMedia` (`data-theme-choice`), серверный
  SSR-fallback `detect_theme`; `users.theme` синхронизируется с резолвнутым dark/light.
- **Акценты**: `html[data-accent]` переопределяет токены accent/on-accent/accent-text;
  контраст верифицирован (accent↔on-accent ≥4.5, accent-text↔surface ≥4.5).
- **Дашборд**: рендер по `prefs.dash_visible` (порядок + скрытие), id `dash-block-*`.
- **Светлая тема = первый класс (ADR-082)**: `--text-muted` light #6b5e53; цветные
  тексты `-700 dark:-400`; белый текст на `bg-emerald/green-500/600` → фон -700;
  JS-инжект шаблонов тоже токенизирован. Axe dark+light на 8 маршрутах зелёный;
  browser-матрица 36 passed / 6 skip (prototype) / 0 fail.
- **Discretion v1 (§12)**: нейтральные nav-лейблы (`dscr_*` EN/RU, макрос `dscr_label`
  в `components/labels.html` с `with context`), маскировка имён (Item #N), нейтральный
  favicon (`favicon-neutral.svg`), blur изображений (media vault SSR + inventory JS
  `data-blur`), quick-toggle в utility bar (POST + мгновенно, сервер — источник истины
  для следующего SSR). Данные/правила/safety не трогаются. Долг: тексты уведомлений
  не нейтрализованы (v1).
- **Social tone (§13)**: токен-пасс social-шаблонов (bg-white→pl-surface, gray→токены,
  indigo→`--dom-social*`); токены `--dom-social-text` / `--dom-social-btn` с проверкой
  контраста.

---

## 21. Реализованные решения и направление развития

### Реализовано (ADR-035…042, сессии 58–62)
1. **ActivityCategory** — таблица категорий (16 категорий с подкатегориями), `entities.category_id` FK (legacy `category` строка сохранена).
2. **ActivityTask** — эволюция ActivityLog: статус-машина из 11 состояний, title_override, scheduled_at, planned/actual параметры раздельно, комментарии.
3. **Аудит переходов** — `activity_task_history`.
4. **Сессии-accepted** — принятие сессии, после чего изменения = штраф (ADR-037).
5. **Штрафы** — частичное выполнение без награды; cancelled/skipped до начала без штрафа; stopped — штраф; per-activity `penalty_enabled` (ADR-038).
6. **Типизированный DSL параметров** (ADR-041) + **title-генератор** (ADR-042).
7. Training — отдельная система программ (ADR-039).

### Направление развития
- **Мобильный клиент** (ADR-063): кроссплатформенное приложение после запуска портала.
- **Масштабирование** (ADR-064): по трём осям (пользователи / объём данных / инфраструктура), без преждевременного over-engineering.
- **JSON-first контракт** (ADR-065): action-эндпоинты возвращают JSON — фундамент для мобильного клиента. **Реализовано в M4**: locktimer-действия (start/safety-stop/open/reveal/complete/правила/шаблоны) отдают JSON при `Authorization: Bearer` и redirect для HTMX-форм (dual-mode).
- **Mobile Foundation (M4)** — bearer-auth (access+refresh, ротация+отзыв), push-устройства (`/api/v2/push/devices`) и абстракция отправки (`app/push`, `PUSH_PROVIDER=none|logging|fcm|apns`); медиа URL-контракт — `GET /api/v2/media/{id}` работает по bearer.

---

## 22. Medication Organizer (M3 Personal Suite, Шаг 11b, ADR-084)

Первый Health-модуль личного контура (ROADMAP §7 4C, PRODUCT_VISION §9.1).
**Relief-only** (PD-013): никакой игровой интеграции (XP/баллы/штрафы не применяются);
все записи — Private Record (DATA_LIFECYCLE.md); экспорт для врача — явный
Shared Artifact. Feature flag `medication_enabled` (default true).

- **Модель (5 таблиц, миграция 041)**: `medications` (каталог лекарств/БАД/расходников:
  name, kind, active_ingredient, form, strength, unit, instructions), `med_kits` (аптечки/
  места хранения), `med_stocks` (партия: quantity + expiry_date + lot + low_stock_threshold),
  `med_schedules` (доза + частота: daily/interval/weekly), `med_intakes` (факт приёма:
  taken/missed/skipped/rescheduled/unknown).
- **Страница `/medications`**: «на сегодня» (невыполненные приёмы, быстрые действия
  принято/пропущено/осознанный пропуск), истекающие/низкий остаток (30 дней порог),
  каталог с остатками и расписаниями, аптечки, инлайн-формы добавления.
- **JSON API** (`/api/v2/medications`, bearer): список, `/today` (due + expiring +
  low_stock по локальному дню устройства), `POST /{id}/intake`, `/export` (JSON),
  `GET /stocks` (партии/остатки), `GET /schedules` (расписания), `GET /kits` (аптечки) —
  плоские owner-scoped списки для мобильного клиента; создание — `POST /` (препарат),
  `POST /stocks`, `POST /schedules`, `POST /kits` (owner-scoped, 201); удаление —
  `DELETE /{id}`, `DELETE /stocks/{id}`, `DELETE /schedules/{id}`, `DELETE /kits/{id}` (204).
- **Экспорт**: `GET /medications/export` — CSV (список + история приёма) для врача;
  `Content-Disposition: attachment`.
- **Границы дня**: «сегодня» и подсчёт принятого — через `timeutils.local_date()`
  (client-tz), а не жёсткий UTC.
- **OCR/LLM верификация кодов** (Q13 в OPEN_QUESTIONS.md): отложено.

---

## 23. Health + Cycle foundation (M3 Personal Suite, Шаг 13, ADR-086)

Второй Health-модуль личного контура (ROADMAP §7 4D, PRODUCT_VISION §9.2–9.4).
**Relief-only** (PD-013): никакой игровой интеграции, никаких штрафов; все записи —
Private Record (DATA_LIFECYCLE.md). Расчётная фаза Cycle никогда не выдаётся за
достоверный факт (§9.4). Feature flag `health_enabled` (default true).

- **Модель (4 таблицы, миграция 044)**:
  - `health_states` — ежедневный check-in: event_date, mood/energy/sleep_quality/recovery (1–5),
    sleep_hours, symptoms (JSON-список), notes;
  - `lab_records` — анализы: name, measured_at, value, unit, ref_min/ref_max (оригинальный
    диапазон конкретной лаборатории), lab_name, flagged (пометка лаборатории), notes;
  - `cycle_settings` — одна строка на пользователя: cycle_length, period_length, contraception;
  - `cycle_events` — факты цикла: event_date, event_type
    (bleeding/symptom/state/sleep/energy/libido/skin/test/note), value, notes.
- **Страница `/health`**: check-in на сегодня (upsert по дате), история check-in'ов,
  анализы с подсветкой вне-диапазона, Cycle: настройки + события + расчётная фаза
  (menstrual/follicular/ovulation/luteal) по дню цикла от последнего начала кровотечения.
- **Расчёт фазы**: `_day_of_cycle` — день цикла от последнего начала кровотечения
  (новый цикл после перерыва ≥3 дней), `_cycle_phase` — фаза по дню. Всегда помечается
  `phase_estimated=True`.
- **JSON API** (`/api/v2/health`, bearer): сводка (`/`), `/states`, `/labs`, `/cycle`,
  `POST /state`, `POST /labs`, `POST /cycle/events`, `POST /cycle/settings` (upsert),
  `DELETE /labs/{id}`, `DELETE /cycle/events/{id}`.
- **Дашборд**: блок `dash-block-health` (check-in сегодня / число анализов / фаза цикла),
  управляется в /settings (DASH_BLOCKS), discretion-aware.
- **LLM-разбор анализов** (§9.3, ADR-087): `POST /health/analyze` (form) и
  `POST /api/v2/health/analyze` (JSON). Режим из `prefs.llm_mode` (safe/expanded,
  настройка в /settings → «LLM mode»): safe — нейтральный пересказ + вопросы врачу;
  expanded — дополнительно рекомендации/советы (в т.ч. по схеме приёма — активные
  med_schedules в контексте). Usage-трекинг на активном LLMProviderConfig. Результат
  stateless (не сохраняется в БД). Дисклеймер «не врач» — только в UI, в промпты
  не подаётся (решение владельца).
- **LLM-режим на всех блоках** (ADR-087): `app/llm/mode.py` — единый `llm_mode_hint()`
  аппендится к системным промптам задач/тренировок/диет/промпт-шаблонов (safe —
  только факты; expanded — рекомендации/советы). Параметр `llm_mode` у всех
  pipeline-функций (None → из prefs); Telegram `/next` и фоновый scheduler передают
  режим явно из `user.prefs`.

## 24. Sexual Journal (M3 Personal Suite, Шаг 14 + 14b, ADR-088/089)

Первый срез журналов личного контура (ROADMAP §7 4A, PRODUCT_VISION §7).
**Relief-only** (PD-013): никакой игровой интеграции, никаких штрафов; все записи —
Private Record (DATA_LIFECYCLE.md). Feature flag `journal_enabled` (default true).

- **Модель (2 таблицы, миграции 045 + 046)**:
  - `sj_partners` — локальные псевдонимы партнёров (user-scoped, name/notes; никогда
    не раскрываются наружу);
  - `sj_entries` — записи журнала: entry_date, partner_id (FK SET NULL), activity_type,
    duration_minutes, desire_before/arousal_before (1–5), protection
    (none/condom/birth_control/withdrawal/other), orgasms, intensity/satisfaction/pleasure
    (1–5), reactions (JSON), emotional_state (JSON), aftercare, recovery (1–5), notes,
    мягкие ссылки timer_session_id/health_state_id (UUID без FK), снимок cycle_phase/cycle_day,
    **status** (draft/completed), **source** (manual/activity/timer_slot),
    **activity_log_id** и **slot_occurrence_id** (мягкие ссылки на Tracker-задачу и окно таймера).
- **Страница `/journal`**: форма записи (дата, партнёр, вид активности, длительность,
  желание/возбуждение до начала, защита/контрацепция, оргазмы, интенсивность,
  удовлетворённость, удовольствие, реакции, эмоциональное состояние, aftercare,
  восстановление, заметки, селект недавних активностей Tracker), история записей
  (с фото-плитками и названием связанной задачи), псевдонимы партнёров (CRUD),
  секция **«Требуются детали»** (draft-записи от окон таймера — форма заполнения при закрытии).
- **Медиа**: `owner_type=journal_entry` в media registry; `POST /journal/entries/{id}/media`
  (загрузка фото → MediaAsset, owner-scoped, чужой entry → 404); фото отображаются в записях.
- **Связь с Cycle (§16)**: при создании записи сохраняется снимок расчётной фазы цикла
  (`cycle_phase`/`cycle_day`) — помечен как оценка, не факт (§9.4). Если Cycle недоступен —
  (None, None).
- **Связь с Tracker**: `activity_log_id` (мягкая ссылка по ID, валидация владельца —
  чужой task → 400); при привязке `source=activity`; название задачи показывается в записи.
- **Timer-автозапись (Шаг 14b)**: флаг `journal_auto` на слоте (`lock_slot_rules`, миграция 046) —
  открытие окна для плановой активности авто-создаёт **draft**-запись (`source=timer_slot`,
  idempotent); при закрытии окна API возвращает `journal_pending` (entry_id + url) и в
  session_detail появляется CTA «Заполнить детали журнала»; детали обязательны при закрытии
  (форма или `POST /api/v2/journal/entries/{id}/complete`).
- **Связи с Timer/Health — по ID без раскрытия** (DATA_LIFECYCLE.md): мягкие UUID-ссылки
  без FK; отдельное удаление; общая проекция не открывает журналы друг друга (§7).
- **JSON API** (`/api/v2/journal`, bearer): сводка (`/` — записи + партнёры),
  `POST /entries`, `POST /partners`, `POST /entries/{id}/complete`,
  `DELETE /entries/{id}`, `DELETE /partners/{id}`. Object-level auth:
  чужой partner_id отклоняется; удаление псевдонима обнуляет ссылки в записях
  (SET NULL на уровне приложения).
- **Дашборд**: блок `dash-block-journal` (записи за 30д / последняя запись /
  ср. удовлетворённость), управляется в /settings (DASH_BLOCKS), discretion-aware.
- **Навигация**: пункт «Журнал» (иконка aftercare.svg из пакета) в группе «Данные».

## 25. Personal Care (M3 Personal Suite, Шаг 15, ADR-090)

Третий срез ухода личного контура (ROADMAP §7 4B, PRODUCT_VISION §8): уход, косметика,
гигиена, процедуры и внешность. **Relief-only** (PD-013): никакой игровой интеграции,
никаких штрафов; все записи Private Record (DATA_LIFECYCLE.md).
Feature flag `care_enabled` (default true).

- **Модель (7 таблиц, миграции 047 + 049 + 051 + 053)**:
  - `care_routines` — каталог процедур/рутин: name, area (face/body/hair/hands/feet/other),
    kind (home/salon), frequency_days (частота в днях, необязательно), notes;
  - `care_entries` — факты выполнения процедуры: routine_id (FK SET NULL), entry_date,
    duration_minutes, skin_reaction (1–5), notes, снимок cycle_phase/cycle_day;
  - `care_products` — каталог средств/косметики (Шаг 16b, ADR-092): name, category
    (cleanser/toner/serum/moisturizer/mask/exfoliant/sun/body/hair/other), brand, notes,
    quantity (остаток), expiry_date (срок), inventory_item_id (FK inventory_items, SET NULL —
    остаток/список покупок в инвентаре), catalog_item_id (FK activity_catalog, SET NULL —
    связь с универсальным каталогом);
  - `care_entry_products` — какие средства использованы в записи ухода (many-to-many
    care_entries ↔ care_products, CASCADE);
  - `care_routine_products` — рекомендуемые средства для процедуры (many-to-many
    care_routines ↔ care_products, CASCADE);
  - `care_courses` — курс процедур (серия сеансов, Шаг 17c, ADR-095): name, area,
    total_sessions, interval_days, start_date, status, catalog_item_id;
  - `care_course_sessions` — сеансы курса: session_number, scheduled_date, status
    (pending/done/skipped), entry_id (мягкая ссылка на запись ухода).
- **Курсы процедур (Шаг 17c, ADR-095)**: секция на /care — создание курса (название,
  зона, число сеансов, интервал, дата старта) генерирует сеансы; прогресс-чипы,
  отметка сеанса «done» по клику; напоминание о следующем сеансе (reminder engine).
  JSON `/api/v2/care/courses` — `GET` (список курсов со сеансами, для мобильного
  клиента) + `POST` (201, создание).
- **Страница `/care`**: форма процедуры (название, зона, тип, частота, заметки) +
  журнал ухода (дата, процедура, длительность, реакция кожи, заметки) + каталог рутин
  (с числом выполнений) + история записей с фото-плитками.
- **Медиа**: `owner_type=care_entry` в media registry/allowlist;
  `POST /care/entries/{id}/media` (загрузка фото → MediaAsset, owner-scoped, чужой
  entry → 404) — фото динамики.
- **Связь с Cycle (§9.4)**: при создании записи сохраняется снимок расчётной фазы цикла
  (`cycle_phase`/`cycle_day`) — помечен как оценка, не факт. Если Cycle недоступен —
  (None, None).
- **Средства/косметика (Шаг 16b, ADR-092; Шаг 17b, ADR-094)**: секция на /care —
  форма (название, категория, бренд, остаток quantity, срок expiry_date, связанный
  предмет инвентаря, ссылка на универсальный каталог) + список с инвентарным бейджем,
  low-stock/expiring-бейджами и счётчиком использований; фото средства (owner_type=
  care_product, POST /care/products/{id}/media); форма записи ухода — мультиселект
  средств; форма рутины — мультиселект рекомендуемых средств (care_routine_products).
  Валидация владельца: чужой inventory_item_id/product_id → 400; удаление продукта
  чистит join-строки на уровне приложения + CASCADE в БД.
- **JSON API** (`/api/v2/care`, bearer): сводка (`/` — процедуры + записи + средства),
  `GET /products`, `GET /courses`, `POST /routines`, `POST /entries`, `POST /products`,
  `DELETE /products/{id}`, `DELETE /routines/{id}`, `DELETE /entries/{id}`,
  `POST /courses`, `DELETE /courses/{id}`.
  Object-level
  auth: чужой routine_id отклоняется; удаление процедуры обнуляет ссылки в записях
  (SET NULL на уровне приложения).
- **Дашборд**: блок `dash-block-care` (процедуры за 30д / последняя / число рутин),
  управляется в /settings (DASH_BLOCKS), discretion-aware.
- **Навигация**: пункт «Уход» (иконка routine.svg из пакета) в группе «Данные».

## 26. Универсальный каталог активностей (сквозной, Шаг 16, ADR-091)

Единый каталог «видов активностей» по образцу Entity (категории/теги/описание),
на который могут ссылаться любые модули личного контура. **Relief-only** (PD-013):
это справочник без игровой интеграции (XP/баллы/штрафы); игровые параметры остаются
в Entity-каталоге трекера. Feature flag `catalog_enabled` (default true).

- **Модель (1 таблица, миграция 048)**: `activity_catalog` — name, description,
  category_id (FK activity_categories, SET NULL), tags (JSON), domains (JSON-список
  контекстов: journal/care/timer/tracker; пусто/None = «сквозная», применима везде),
  owner_id (NULL = системная запись, видна всем; иначе — пользовательская, только
  владельцу), is_public, created_at/updated_at.
- **Замена свободных полей на FK-ссылку (все SET NULL)**: `sj_entries.catalog_item_id`
  (вид активности в журнале), `care_routines.catalog_item_id` (вид процедуры ухода),
  `lock_slot_rules.catalog_item_id` (причина/цель окна таймера), `entities.catalog_item_id`
  (трекер-задача). Свободный ввод остаётся только через создание своей записи каталога.
- **Страница `/catalog`**: просмотр/создание/удаление записей, фильтр по domain,
  системные + личные записи.
- **JSON API** (`/api/v2/catalog`, bearer): список/создание/удаление. Object-level auth:
  чужая запись недоступна.
- **Хелпер `catalog_options(domain)`**: для пикеров в формах журнала, ухода, слота
  таймера и my_entities (системные + свои, фильтр по domain).
- **Навигация**: пункт «Каталог» (иконка library.svg из пакета) в группе «Данные».

## 27. Personal Insights (M3 Personal Suite, Шаг 17, ADR-093)

Явно запрошенный кросс-модульный LLM-анализ личных данных (PRODUCT_OVERVIEW §12,
TARGET_ARCHITECTURE §3.10): тенденции и связи между активностями, таймером,
журналом, здоровьем, уходом, тренировками и диетами. **Relief-only** (PD-013):
без игровой интеграции; все записи Private Record (DATA_LIFECYCLE.md).
Feature flag `insights_enabled` (default true).

- **Модель (2 таблицы, миграция 050)**:
  - `insight_runs` — запуск анализа: period_start/period_end, sections (JSON),
    status (completed/failed), summary (общий вывод), usage_tokens/usage_cost, error;
  - `insight_findings` — находки (run_id FK CASCADE): section, title, summary,
    used_data (JSON — какие данные использованы, прозрачность).
- **LLM-пайплайн** (`app/llm/pipeline/insights.py` + `insights_prompts.py`):
  контекст собирается только из выбранных разделов за выбранный период
  (tracker/timer/journal/health/care/training/diet); промпт требует показывать
  использованные данные и **не объявляет корреляцию причиной**; режим
  `prefs.llm_mode` (safe/expanded, ADR-087); usage трекается на LLMProviderConfig.
- **Страница `/insights`**: пикер разделов (чекбоксы) + период + «Запустить
  анализ» + результат (summary + находки с used_data) + история запусков
  (с удалением). Object-level auth: чужой run → 404; удаление каскадит findings.
- **JSON API** (`/api/v2/insights`, bearer): GET список, POST запуск,
  GET /runs/{id}, DELETE /runs/{id}.
- **Дашборд**: блок `dash-block-insights` (последний запуск / число находок /
  период), управляется в /settings (DASH_BLOCKS), discretion-aware.
- **Навигация**: пункт «Инсайты» (иконка insights.svg из пакета) в группе «Данные».

## 28. Средства/косметика в других модулях (кросс-модуль, Шаг 17b, ADR-094)

Доработка каталога средств/косметики (§25) и его сквозное использование в
других модулях личного контура. **Relief-only** (PD-013): без игровой интеграции.
Все связи — мягкие ссылки JSON по ID (DATA_LIFECYCLE.md, без FK, отдельное удаление).

- **Остатки и сроки**: `care_products.quantity` (остаток, low-stock при ≤1) и
  `care_products.expiry_date` (срок, expiring при ≤30 дней) — бейджи на /care.
- **Средства ↔ рутины**: `care_routine_products` — рекомендуемые средства для
  процедуры (мультиселект в форме рутины).
- **Средства в окнах таймера**: `lock_slot_rules.care_product_ids` (JSON) — какие
  средства использовать в окне; пикер в форме слота + отображение в открытом окне.
- **Средства в задачах трекера**: `entities.care_product_ids` (JSON) — какие средства
  нужны для задачи; пикер в форме my_entities.
- **Средства → журнал**: `sj_entries.care_product_ids` (JSON) — использованные
  средства в записи; мультиселект в форме/complete + JSON API.
- **Средства в Insights**: контекст раздела care дополнен расходом средств (сколько
  раз использовалось) и low-stock (низкий остаток/истёкший срок).
- **Валидация владельца** во всех местах (чужое средство → 400); JSON-колонки хранят
  строки UUID (UUID не сериализуется в JSON).

## 29. Reminders & авто-инсайты (Шаг 17c, ADR-095)

Фоновые напоминания личного контура + автозапуск Personal Insights + Cycle-инсайты.
**Relief-only** (PD-013): напоминания и курсы не применяют очки/штрафы.

- **Reminder engine** (`app/reminders/` + `reminder_log`, миграция 052):
  - коллекторы (daily): медикаменты (due today по расписанию / низкий остаток /
    истекающие), средства ухода (low-stock quantity≤1 / expiring ≤30д), процедуры
    ухода (по frequency_days), курсы (следующий сеанс); таймер и точное время дозы
    переехали в event-режим (§30);
  - дедупликация через `reminder_log` (unique user+kind+dedupe_key): daily — ежедневно,
    state — разово, occurrence — разово на occurrence;
  - доставка: in-app `Notification` (type=reminder) + Telegram + push; тексты
    нейтрализуются при discretion (ADR-081);
  - asyncio-планировщик (`reminder_time`/`reminder_tz`, `REMINDER_ENABLED`,
    default 09:00 UTC) в lifespan.
- **Авто-инсайты** (`app/insights/scheduler.py`): `prefs.insights_auto` +
  `insights_auto_days`; `run_auto_insights` для opted-in пользователей с активным
  LLM-конфигом (lookback window, все секции).
- **Cycle-инсайты**: раздел `cycle` в `INSIGHT_SECTIONS` + `_ctx_cycle` — фаза по
  дням периода, агрегаты настроения/удовлетворённости/реакции кожи по фазам
  (расчётная фаза, без причинности — §9.4).

## 30. Event-напоминания + настройки и таймер в боте (Шаг 17d, ADR-096)

Дополнение к Reminders (§29) и Telegram-боту. **Relief-only** (PD-013); изменений схемы БД не требуется.

- **Event-напоминания («незадолго до события»):**
  - режим `event` в reminder engine: `med_dose` (доза в конкретное `times_of_day`-время)
    и `timer_slot_upcoming`/`timer_task_due` (lead-окно вместо 24ч lookahead);
  - scheduler с двумя каденсами: daily-батч (`reminder_time`) + event-цикл каждые
    `reminder_event_interval_minutes` (default 15); lead `reminder_event_lead_minutes`
    (default 30) — т.е. уведомление приходит ~за 30 минут до события;
  - дедуп: `med_dose:{schedule}:{date}:{HH:MM}` (пересрабатывает ежедневно на дозу),
    таймер — occurrence-ключи (разово на окно/задачу).
- **Настройки в боте:** `/settings` — язык (EN/RU), discretion (off/always/schedule),
  llm_mode (safe/expanded) инлайн-меню; пишутся в `users.prefs`.
- **Таймер в боте (полное управление):** `/lock_slots` (открыть/закрыть окно),
  `/lock_tasks` (reveal/complete/skip), `/lock_close <номер бирки>` (закрытие с биркой,
  `require_tag`), `/lock_tag <номер>` (проверка номерной бирки); все inline-действия
  вызывают сервисы `app/locktimer/services/execution.py` с проверкой владельца сессии.

---

## 31. Команды бота для личного контура (Шаг 17e, ADR-097)

Дополнение к Telegram-боту (§13, §30). **Relief-only** (PD-013); изменений схемы БД не требуется, локализация бота ограничена текущим EN-контуром.

- **`/med`** — приёмы на сегодня (`_schedule_summary`: due + expiring + low stock);
  инлайн «Taken» записывает `MedIntake(status=taken)` + `on_medication_taken`
  (adherence XP + достижения, positive-only, ADR-085).
- **`/health`** — чек-ин: настроение/энергия/сон на сегодня, инлайн-кнопки mood/energy 1–5
  (upsert `HealthState` на сегодня).
- **`/cycle`** — расчётная фаза, день цикла, длина и оценка даты следующих месячных
  (`_get_cycle_context`; фаза всегда «estimated», §9.4).
- **`/care`** — due-рутины по `frequency_days` + ближайшие сеансы курсов; инлайн «Done»
  создаёт `CareEntry` на сегодня (со снимком фазы Cycle) или помечает сеанс `done`.
- `/start` help дополнен этими командами.

---

## 32. Напоминания: время/пояс на пользователя (Шаг 17f, ADR-098)

Глобальные `REMINDER_TIME`/`REMINDER_TZ` стали **дефолтами** (default 09:00 UTC), а не единственным значением.

- **Prefs**: `users.prefs.reminder_time` (HH:MM) + `reminder_tz` (IANA); пустое/невалидное = наследовать глобальный дефолт.
- **Engine**: daily-цикл считает «сегодня»/«сейчас» в tz пользователя (границы суток и время доз корректны); `run_reminder_cycle_for_user` — per-user.
- **Scheduler**: daily-триггер per-user (локальное время ≥ reminder_time, раз в локальный день); event-цикл (ADR-096) — глобальный каденс с per-user «сейчас»; auto-insights — раз в день.
- **UI**: `/settings` → секция «Напоминания» (время + часовой пояс IANA с подсказкой).

---

## 33. Уход за устройством и wear check-ins (B2/C2, миграции 054–055)

- `chastity_device_events` хранит owner-scoped события comfort/problem/maintenance/cleaning/
  inspection с мягкими связями на Inventory device и Timer session. Контур relief-only:
  проблемы и обслуживание не начисляют очки и не применяют штрафы.
- `chastity_check_ins` хранит настроение, физический комфорт, заметку и опциональный фото-отчёт
  во время ношения. Фото может ссылаться на существующий результат media verification.
- Web и bearer JSON API поддерживают создание/просмотр; все ссылки проверяются по владельцу.

## 34. Aftercare (C1, миграция 056)

Отдельный Private Record для физической и эмоциональной заботы, дебрифа, гидратации и отдыха.
Запись содержит дату, вид, уровень восстановления, заметку и мягкие связи с Sexual Journal и
Timer. Модуль доступен через `/aftercare` и `/api/v2/aftercare`, owner-scoped, relief-only и без
игровой интеграции.

## 35. Durable consent и BYOK disclosure (C3/S1, ADR-102/104, миграции 057–058)

- Реестр purpose включает профильные модули Tracker/Timer/Medication/Health/Journal/Care/
  Catalog/Insights/Aftercare и отдельные цели `byok_provider`, `llm_expanded`,
  `media_verification`, `data_processing`.
- Grant действует **один раз на весь срок пользования порталом** для конкретной цели и версии
  условий. Повторный grant идемпотентен; выключение модуля не отзывает согласие. Явный revoke или
  новая версия условий требуют новой append-only записи.
- При первом входе запрашиваются согласия включённых модулей; при включении нового модуля в
  профиле запрашивается только его недостающее согласие. Sensitive endpoints возвращают 428 с
  машинным кодом `consent_required` до grant.
- История доступна в `/consent` и `/api/v2/consent`; DELETE отсутствует. PostgreSQL сериализует
  выдачу версии блокировкой пользователя, а unique/check constraints защищают инварианты.
- BYOK имеет отдельное раскрытие: пользователь сам принёс провайдера, endpoint, модель и ключ и
  несёт ответственность за их выбор, условия, стоимость и передаваемые данные. Это не разрешает
  обход safety-фильтров и не отменяет серверную валидацию и consent gates портала.

## 36. Account profile и admin user management (S6, миграция 059)

- `/account` — личный профиль с email, ролью, датой создания и часовым поясом; пароль меняется в
  `/settings`, privacy/export остаются в `/privacy`.
- `/admin/users` доступен только роли admin: список аккаунтов, роли user/moderator/admin,
  disable/enable и явная установка временного пароля другому пользователю. Хеши, токены и другие
  секреты не выводятся.
- Администратор не может понизить или заблокировать собственный аккаунт через admin UI; свой
  пароль меняет только с подтверждением текущего пароля.
- `users.disabled_at` немедленно запрещает cookie/bearer login, текущие authenticated requests и
  refresh-token rotation; при блокировке и reset все сохранённые refresh-токены удаляются.
- Не реализованы: восстановление через email, verified смена email, приглашения и отдельный audit
  trail административных операций.

---

## 37. Зашифрованное Медиа-Хранилище (Media Vault)

> Добавлено в v0.8.1-actual (2026-08-20).

- **AES-256-GCM шифрование** (`app/media/crypto.py`): все загружаемые медиа-файлы шифруются на
  диске. 12-байтный случайный nonce генерируется для каждого файла; ключ шифрования берётся из
  `CREDENTIALS_ENCRYPTION_KEY`. Дешифровка только через авторизованный API.

- **Анти-утечка водяные знаки** (`app/media/watermark.py`): при отдаче файла накладывается
  полупрозрачный overlay с `user_id` и временно́й меткой. Препятствует несанкционированному
  распространению через скриншоты или повторную публикацию.

- **Извлечение ключевых кадров из видео** (`app/media/video_frames.py`): видео-доказательства
  проходят через frame-extraction — сохраняются N ключевых кадров для аудита и AI-анализа.

- **EXIF-аудит и pHash антиспуфинг** (`app/media/anti_spoofing.py`): вычисляет dHash/pHash для
  дедупликации и обнаружения повторно используемых изображений; анализирует EXIF-метаданные
  (время съёмки, GPS, устройство) и выдаёт оценку подлинности `authenticity_score` (0..100).

- **Мультиподписное HMAC-доказательство** (`app/media/multi_sig.py`): криптографическая
  верификация целостности медиа-файла через HMAC-SHA256. Позволяет удостоверить, что файл не
  изменялся после подписания.

- **AI визуальное сравнение «До/После»** (`app/agent/media_comparison.py`): мультимодальный
  AI-анализ пары фото «до» и «после» для оценки прогресса (используется multimodal LLM).

- **Авто AI-теггинг и умные альбомы** (`app/agent/media_tagging.py`): семантические теги
  (`[chastity, checkin, aftercare]`) + автоматическая категоризация в смарт-альбомы на основе
  визуального содержимого.

- **Временна́я шкала медиа-доказательств** (`/media/timeline`): хронологический интерактивный
  просмотр медиа-доказательств в формате «Dark Archive» UI.

---

## 38. ИИ-Агенты: расширенные движки

> Добавлено в v0.8.1-actual (2026-08-20).

### 38.1. Адаптивный генератор тренировочных программ

`app/agent/training_generator.py` — генерирует 7-дневные адаптивные тренировочные программы на
основе recovery-логов пользователя. Использует LLM для подбора нагрузки, упражнений и
последовательности дней с учётом текущего уровня восстановления.

Модели: `AdaptiveProgram` (`focus_domain`, `total_days`, `current_day`, `difficulty_level`,
`status`) + `AdaptiveProgramStep` (`program_id`, `day_number`, `title`, `target_parameters`, `status`).

### 38.2. AI визуальное сравнение медиа

`app/agent/media_comparison.py` — мультимодальный AI-анализ фотопар «До / После» для прогресс-
отчётов. Результат — структурированное сравнение изменений по ключевым параметрам.

### 38.3. AI авто-теггинг и умные альбомы

`app/agent/media_tagging.py` — автоматическое назначение семантических тегов медиа-файлам и их
категоризация в умные альбомы. Примеры тегов: `chastity`, `checkin`, `aftercare`, `training`,
`progress`.

### 38.4. Контроль обслуживания инвентаря

`app/agent/equipment_maintenance.py` — автоматическое отслеживание интервалов дезинфекции и
ухода за предметами инвентаря. Функция `schedule_equipment_maintenance_reminders` опрашивает
`EquipmentMaintenanceLog` и формирует чек-ин-напоминания для предметов, превысивших установленный
интервал обслуживания.

### 38.5. Ежемесячные визуальные отчёты прогресса

`app/agent/pdf_reports.py` — `generate_monthly_user_report(db, user)` компилирует ежемесячную
статистику активностей (всего/завершено/success_rate) в HTML-отчёт для личного архива.

### 38.6. Тест готовности к сессии (Pre-Session Readiness)

`app/agent/stress_test.py` — `evaluate_pre_session_readiness(answers: list[int])`:
- 5 диагностических вопросов по шкале 1..5
- Итоговый `readiness_score` (0..100%)
- При `readiness_score < 30%` → `is_load_restricted = True` + рекомендация снизить интенсивность
  на 50% или заменить сессию на Aftercare-отдых

---

## 39. Геймификация: Лиги и Дуэли

> Добавлено в v0.8.1-actual (2026-08-20).

### 39.1. Лиги сообщества

`app/agent/community_leagues.py` + `app/models/community_leagues.py`:
- Тиры: **Бронза → Серебро → Золото → Мастер**
- Модель `UserLeagueTier`: `user_id`, `tier` (bronze/silver/gold/master), `points_this_period`,
  `promoted_at`
- Автоматическое повышение при достижении порога очков за период
- Понижение при падении ниже нижнего порога

### 39.2. Еженедельные 1-на-1 Дуэли

`app/agent/weekly_duels.py` + `app/models/duels.py`:
- Модель `UserDuel`: `challenger_id`, `opponent_id`, `challenger_score`, `opponent_score`,
  `status` (pending/active/completed), `winner_id`, `week_start`
- Функция `evaluate_duel_result(db, duel_id)`: определяет победителя по счёту, завершает дуэль,
  начисляет бонусные очки победителю

---

## 40. ИИ-Персона и Аудитор Безопасности

> Добавлено в v0.8.1-actual (2026-08-20).

### 40.1. Конструктор ИИ-Персоны (`/agent/persona-builder`)

`app/agent/persona_builder.py` + `app/models/persona.py` + `app/api/persona_builder.py`:
- **4 архетипа**: Строгий Ключник (Strict Keyholder), Заботливый Куратор (Caring Curator),
  Тренер Выносливости (Endurance Trainer), Анонимный Наблюдатель (Anonymous Observer)
- **Строгость штрафов**: шкала 1..5
- **Tone of Voice**: пользовательский свободный текст
- **Регулятор проактивности**: насколько часто агент инициирует задачи и напоминания
- Модель `UserAgentPersona`: `user_id`, `archetype`, `strictness_level`, `tone_of_voice`,
  `proactivity_level`, `custom_instructions`
- Страница `/agent/persona-builder` — Dark Archive UI с настройкой и сохранением персоны

### 40.2. Аудитор безопасности и выгорания

`app/agent/safety_auditor.py`:
- Вычисляет индекс выгорания **0..100%** на основе истории нагрузки и recovery-логов
- При `burnout_index > 70%` → активируется защитная заморозка нагрузки:
  рекомендуется приостановить нагрузочные активности и перейти в режим восстановления
- Информационные уведомления (не жёсткие блокировки — согласно ADR-129)

---

## 41. Монетизация, Сертификаты и Безопасность

> Добавлено в v0.8.1-actual (2026-08-20).

### 41.1. Промокоды и Gift-подписки

`app/models/promocodes.py` + `app/api/promocodes.py`:
- Модель `PromoCode`: `code` (unique, индексируемый), `tier_grant`, `duration_days`,
  `max_claims`, `claims_count`, `is_active`
- `POST /billing/promocodes/claim` — активация промокода, мгновенный грант тира доступа
- Валидации: лимит активаций, статус активности, верхний регистр кода

### 41.2. Публичные цифровые сертификаты достижений

`app/api/certificates.py` + `app/templates/certificate.html`:
- `GET /certificates/{cert_id}/verify` — публичная страница верификации сертификата
- Отображает: ID подлинности, название программы, подтверждение верификации в реестре
- Dark Archive UI с иконкой трофея и криптографическим ID-подписью

### 41.3. 2FA PIN Shield

`app/api/security_2fa.py`:
- `POST /security/verify-pin` — верификация PIN-кода для разблокировки чувствительных зон
  (Media Vault, D/s-контроли)
- Валидации: минимум 4 цифры, только цифровой ввод
- Возвращает `vault_token` при успешной верификации
- Статус: опциональная TOTP 2FA через authenticator-приложение; recovery-коды и обязательная TOTP при входе остаются отдельными задачами hardening

---

## 42. Telegram: Broadcast Engine

> Добавлено в v0.8.1-actual (2026-08-20).

`app/telegram/broadcast.py`:
- `send_telegram_direct_notification(db, user_id, message_text)` — отправляет прямое
  персональное уведомление в Telegram-чат пользователя через aiogram-бот
- Используется для AI-агентных алертов (выгорание, дуэли, повышение в лиге, обслуживание
  инвентаря)
- Статус: webhook/уведомления реализованы через aiogram-контур; внешние провайдеры и фоновые каналы проверяются отдельно по конфигурации окружения

---

## 43. Health & Cycle Dashboard

> Добавлено в v0.8.1-actual (2026-08-20).

`app/api/health_dashboard.py` + шаблон `health_body_cycle.html`:
- Страница `/health/dashboard` — сводная визуализация ежедневного check-in (`BodyCycleLog`:
  настроение/энергия/сон/симптомы) и процедур ухода (`CareEntry`)
- Сгруппированные карточки по датам, фаза цикла, динамика самочувствия
- Объединяет модули Health + Cycle (§23) и Personal Care (§25) в единый обзор

---

## 44. Quests & Weekly Challenges (ADR-120)

> Добавлено в v0.8.1-actual (2026-08-20).

`app/api/quests.py` + `app/models/quest.py` + `app/seed_quests.py` + шаблон `quests.html`
(миграция `072_add_quests_and_user_quests.py`):
- Модель `Quest`: `title`, `description`, `quest_type` (daily / weekly / streak), `category`,
  `target_count`, `reward_xp`, `badge_icon`
- Модель `UserQuest`: `current_progress`, `status` (active / completed / claimed), `obtained_at`
- Хаб `/achievements/quests` (алиас `/quests/challenges`): авто-сидирование каталога квестов,
  назначение активных квестов пользователю
- `POST /achievements/quests/{user_quest_id}/claim` — claim награды: статус `claimed` +
  начисление `reward_xp` в `UserProgress`

---

## 45. Billing: тиры, акции, мульти-гейтвей оплаты

> Добавлено в v0.8.1-actual (2026-08-20).

`app/api/billing.py` + `app/billing/gateways.py` + `app/models/monetization.py` +
`app/models/payment.py` + шаблон `billing.html`:

### 45.1. Конструктор тиров подписки
- `SubscriptionTier`: `code`, `name`, `rank` (иерархия 1..5), `price_monthly`, `is_default`
- `TierFeatureGrant`: `feature_code` + `limit_value` (NULL = безлимит) — какие функции доступны
  на тире
- `TemporaryFeaturePromotion`: временная акция, открывающая feature-код на более низкие тиры
  (`starts_at` / `ends_at` / `is_active`)

### 45.2. Multi-Gateway Checkout
- `POST /billing/checkout` — создание чекаута по `tier_code` + `gateway`
- Провайдеры (`PRICES_MAP`): **Stripe**, **Telegram Stars**, **Crypto (NowPayments)**,
  **ЮKassa (yoomoney)**; цены: standard 9.99$ / pro 19.99$ / ds_master 29.99$ / guild_master 49.99$
- `PaymentInvoice`: `user_id`, `tier_code`, `gateway`, `external_invoice_id`, `amount`, `currency`,
  `status` (pending → paid), `paid_at`
- `POST /billing/webhook/{gateway}` — обработка вебхука: подтверждает платёж по
  `external_invoice_id`, апгрейдит `user.subscription_tier`

### 45.3. Взаимодействие с Промокодами (§41.1)
- `POST /billing/promocodes/claim` — активация промокода, мгновенный грант тира

---

## 46. Community Top Agent, Турниры и Автоматизация

> Добавлено в v0.8.1-actual (2026-08-20).

### 46.1. Автономный Top Agent сообщества

`app/agent/community_agent.py` + `app/api/community_agent.py` +
`app/models/community_agent.py`:
- `CommunityTopAgent`: `persona_name` (по умолчанию «Domina Veritas»), `strictness_level` (1..5),
  `auto_quests_enabled`, `lock_challenges_enabled`, `rules_manifest`, `last_audit_at`
- `CommunityPost`: лента анонсов (тип, заголовок, контент)
- `CommunityMemberDelegation`: делегирование блоков профиля агенту (`delegate_tasks`,
  `delegate_training`, `delegate_care`, `delegate_timer`) + `compliance_score`
- Страницы: `/communities/{id}/agent` (кокпит члена), `/communities/{id}/cockpit` (кокпит владельца)
- Эндпоинты: `POST .../agent/configure`, `.../agent/quest/generate`, `.../agent/delegate`,
  `.../cockpit/update-persona`

### 46.2. Публичные турниры сообщества

`app/agent/tournament_rewards.py`:
- `CommunityTournament`: `title`, `metric_type` (compliance / xp / care / lock), `status`
  (active / completed), `starts_at` / `ends_at`
- `CommunityTournamentEntry`: `points`, `rank` — живой лидерборд
- `POST .../tournaments/create`, `POST .../tournaments/{id}/join`
- `award_tournament_prizes`: пересчёт итогов и награждение топ-3 эксклюзивными бейджами
  (`tournament_gold_champion`, `tournament_silver_runner_up`, `tournament_bronze_podium`)
- **iCal-экспорт турниров**: `GET /calendar/feed.ics` (RFC 5545, §52)

### 46.3. Co-Governance роли

`app/agent/community_roles.py` + `app/models/community_roles.py`:
- `CommunityMemberRole`: гранулярные роли со-управления — `co_top`, `keyholder`, `trainer`,
  `care_curator`, `tournament_organizer`
- `assign_community_role(db, community_id, user_id, role_type)` — выдача роли с проверкой
  валидности типа; `get_community_user_roles` — получение ролей пользователя

### 46.4. Automation Triggers (AI-автогенерация триггеров)

`app/agent/automation_triggers.py` + `app/models/automation.py`:
- `AutomationTrigger`: `condition_type`, `threshold_value`, `action_type`, `action_params`,
  `is_active`, `is_agent_generated`, `reasoning_notes`
- `generate_agent_automation_triggers`: анализ истории за 14 дней →
  - пропущенные задачи → триггер `missed_tasks_count → apply_penalty` (штраф XP);
  - записи ухода → триггер `high_stress_score → generate_emergency_quest` (экстренный сеанс
    восстановления);
- `evaluate_user_triggers`: проверка активных триггеров по текущей метрике и выполнение действий

---

## 47. LLM Exchange Hub (Внешняя ИИ-модель)

> Добавлено в v0.8.1-actual (2026-08-20).

`app/api/llm_exchange.py` + `app/llm/pipeline/exchange.py` + шаблон `llm_exchange.html`:
- Страница `/llm/exchange` (feature `llm_exchange`): справочники пользователя для матчинга
- `POST /llm/exchange/export` — сборка и экспорт **кросс-доменного промпта** по выбранным
  доменам для копирования во внешнюю ИИ-модель
- `POST /llm/exchange/parse` — парсинг вставленного ответа внешней ИИ через `json_repair`
  → структурированные items
- `POST /llm/exchange/confirm` — гидрирование подтверждённых items: создание
  `ActivitySession` + `ActivityLog` на каждый item, начисление +30 XP
- Принцип комплаенса: внешней модели передаётся промпт-описание и справочники, а не
  откровенный контент; финальные действия подтверждает пользователь

---

## 48. Analytics Engine v2 (корреляции, кластеры, траектория)

> Добавлено в v0.8.1-actual (2026-08-20).

`app/analytics/engine.py` + `app/api/insights_analytics.py` + `app/api/insights.py`:

### 48.1. Всеохватывающий корреляционный движок
- `run_full_analytics_suite(db, user, days, locale)` — попарный корреляционный анализ
  (Pearson r) по всем модулям (задачи, тренировки, уход, здоровье, цикл, замеры, диеты и др.)
- `compute_multivariable_clusters` — тройные кластеры сильных корреляций (A+B+C, топ-5)
- Динамическая запись находок в `insight_findings` (section=`correlation`)
- Страницы: `/insights/analytics` (Analytics Cockpit), `/analytics/graph` (интерактивный граф
  корреляций)
- REST: `GET /api/v2/analytics/matrix` — полная матрица для мобильного/PWA
- `POST /insights/analytics/run` — запуск анализа с периодом 7..365 дней

### 48.2. Траектория развития
- `/insights/trajectory` + `POST /insights/trajectory/generate-map` — динамика метрик по
  времени, карта изменений

### 48.3. Отчёт и медицинский экспорт
- `/insights/report` — сводный отчёт по инсайтам
- `/insights/export-medical` + `POST /insights/export-medical/generate` — экспорт медицинских
  данных (проверенные показатели для врача)

---

## 49. D/s Command Center и Keyholder Management (ADR-128/129/130)

> Добавлено в v0.8.1-actual (2026-08-20).

`app/api/ds.py` + `app/models/ds_suite.py` + шаблоны `ds_keyholder.html`, `ds_portal.html`,
`ds_my_top.html`, `ds_checkins.html`:

### 49.1. Keyholder Dashboard
- `/ds/keyholder` — управление сабмиссивами (registered / offline)
- `POST /ds/submissive/create` — создание профиля сабмиссива
- `POST /ds/submissive/{id}/lock-action` — lock / unlock / key_check / emergency_unlock
  с журналом `ChastityLockLog`
- `POST /ds/duties/assign` — выдача задания; `POST /ds/duties/{id}/verify` — approve/reject
  с проверкой исполнения

### 49.2. D/s Command Center (портал)
- `/ds/portal` — мульти-сабмиссивный командный центр: выбор сабмиссива, чек-ины,
  когортная аналитика (`aggregate_keyholder_cohort_analytics`)
- `POST /ds/submissive/{id}/ai-keyholder-spin` — «Колесо Фортуны» ИИ-ключника (ADR-113):
  +24ч продления / выдача ключа / запрос инспекции пломбы
- `POST /ds/submissive/{id}/telegram-code` — генерация 6-символьного кода привязки offline-
  сабмиссива к Telegram-боту (ADR-130)

### 49.3. Портал Нижнего (делегирование, ADR-129)
- `/ds/my-top` — настройки делегирования: `CapabilityGrant` (scope_chastity, scope_tasks,
  scope_training, scope_medication, scope_aftercare, scope_inventory, scope_health_view)
- `POST /ds/grant/create` — генерация invite-кода `DS-XXXX...` (24ч)
- `POST /ds/grant/claim` — активация кода Верхним; rate-limit 10 попыток / 15 мин; запрет
  self-delegation; `with_for_update` против гонок
- `POST /ds/grant/{id}/revoke` — **Safe Word**: мгновенный отзыв всех прав

### 49.4. Wear Check-Ins (ADR-100)
- `/ds/checkins` + `POST /ds/checkins/log` — фиксация чек-ина: номер пломбы, comfort_score,
  заметки, фото (`is_verified_closed` при наличии фото)

---

## 50. Voice STT и TTS

> Добавлено в v0.8.1-actual (2026-08-20).

- **STT-интрейк** (`app/agent/voice_hydration.py`): `process_voice_transcript_intake` —
  обработка транскрипта голосовой заметки: извлечение выполненных/прерванных задач
  (`[Voice Intake]`), метрик здоровья (вода/сон/настроение), создание ActivityLog, markdown-сводка
  для Telegram
- **TTS** (`app/telegram/voice_tts.py`): генерация голосовых ответов/уведомлений
- Статус: STT-парсинг эвристический; TTS зависит от настроенного внешнего провайдера и не считается доступным без успешной проверки подключения
  с логированием (реальная озвучка — в roadmap)

---

## 51. Media Vault v2: одноразовые ссылки

> Добавлено в v0.8.1-actual (2026-08-20).

`app/api/media_vault_v2.py` + `app/models/media_vault.py` (таблица `one_time_media_tokens`):
- `POST /media/one-time-token` — создание **burn-on-read** токена: `secrets.token_urlsafe(32)`,
  срок 24 часа, привязка к `media_path`
- `GET /media/view-once/{token}` — просмотр фото-доказательства с мгновенным уничтожением
  токена (`is_burned`); просроченный токен → 410 Gone
- Дополняет §37 (шифрование, водяные знаки, pHash, HMAC): одноразовый обмен — без
  сохранения копии у получателя

---

## 52. Weekly Digest и iCal-календарь

> Добавлено в v0.8.1-actual (2026-08-20).

- **Weekly AI Digest** (`app/agent/weekly_digest.py`): `generate_weekly_user_digest` —
  недельная сводка (всего/выполнено/прервано, completion rate) + предиктивный прогноз
  вероятности достижения целей на следующую неделю (75%..98.5%), markdown для Telegram
- **iCal Feed** (`app/api/calendar_v2.py`): `GET /calendar/feed.ics` — RFC 5545 iCalendar
  событий активных турниров сообщества (§46.2) для импорта в любой календарь

---

## 53. Media Showcase: Динамический таймер и Неснимаемые публикации

> Добавлено в v0.8.1-actual (2026-08-21).

`app/models/media_exposure.py` + `app/api/media_exposure.py` + шаблон `media_showcase_item.html`:
- `POST /media/exposure/create` — создание публичной или защищенной экспозиции:
  1) **One-Time Burn-on-Read** (`exposure_type="one_time"`): уничтожение после первого открытия;
  2) **Dynamic Countdown Timer** (`exposure_type="dynamic_timer"`): базовый таймер (1–168ч) с
     интерактивным обратным отсчетом на странице;
  3) **Immutable Permanent Showcase** (`exposure_type="permanent_immutable"`): неснимаемая
     публикация, **защищенная от удаления пользователем** на всё время жизни профиля (удаляется
     только при полном удалении аккаунта);
- `POST /media/exposure/{token}/adjust-timer` — управление временем экспозиции: кнопки быстрого
  продления (`+15m`, `+1h`, `+24h`) и сокращения (`-15m`, `-1h`) дедлайна;
- `POST /media/exposure/{token}/revoke` — Kill Switch: мгновенный отзыв временной ссылки
  (блокируется для неснимаемых публикаций);
- Опциональная PIN-защита (4–16 символов) и счетчик просмотров (`view_count`).

---

## 54. Deep EXIF/GPS Stripper и Privacy Masking Studio

> Добавлено в v0.8.1-actual (2026-08-21).

`app/media/sanitizer.py` + `app/media/privacy_mask.py` + `app/api/media_albums.py`:
- **EXIF/GPS Stripper**: автоматическое вырезание геолокации, серийных номеров камер и
  персональных метаданных при любой загрузке изображений (`strip_exif_metadata`); генерация
  серверного HMAC-SHA256 подтверждения подлинности;
- **Privacy Masking Engine**: нанесение зон размытия (Gaussian blur) и blackout-закрашивания
  на чувствительные области (лица, татуировки, фон, интимные зоны) перед экспортом или публикацией
  через `POST /api/v2/media/redact`.

---

## 55. Smart Albums и Зашифрованный Пакетный Экспорт

> Добавлено в v0.8.1-actual (2026-08-21).

`app/services/smart_albums.py` + `app/api/media_albums.py`:
- `GET /api/v2/media/smart-albums` — группировка медиа-архива по смарт-альбомам: *«Сессии»*,
  *«Пломбы и замки»*, *«Замеры и тело»*, *«Процедуры ухода»*, *«Неснимаемая витрина»*;
- `POST /api/v2/media/batch-export-zip` — выгрузка выбранных материалов в зашифрованный ZIP-архив
  с опциональным пользовательским паролем;
- `POST /api/v2/media/batch-delete` — пакетное удаление с **серверной защитой неснимаемых
  постоянных публикаций** (постоянные дропы игнорируются при удалении и сохраняются).

---

## 56. Cross-Activity Dead Man's Switch (Сквозной Контроль Активностей)

> Добавлено в v0.8.1-actual (2026-08-21).

`app/models/dead_mans_switch.py` + `app/services/dead_mans_switch.py` + `app/api/dead_mans_switch.py`
+ шаблон `dms_dashboard.html`:
- Сквозной монитор дедлайнов регулярности по ключевым модулям:
  1) **Wear Check-Ins**: контроль инспекций номерных пломб (автоматический OCR-скан номера
     пломбы через `app/media/ocr_seals.py` при чек-ине на `/ds/checkins`);
  2) **Daily Tasks**: контроль выполнения регулярных задач;
  3) **Medications**: контроль факта своевременного приёма медикаментов;
  4) **General Heartbeat**: общий чек-ин активности;
- Автоматический сдвиг дедлайна при активности (`record_activity_heartbeat`);
- Фоновый аудитор (`evaluate_all_dead_mans_switches`): автоматический переход статусов
  `active → warning → triggered_penalty` и эскалация штрафов при просрочке дедлайна;
- Дашборд мониторинга: `/dms`.



## 57. Протоколы (Protocol Engine, R5, ADR-140)

`app/models/protocol.py` + `app/services/protocol.py` + `app/api/protocols.py`
+ шаблоны `protocols.html` / `protocol_builder.html` / `protocol_run.html`:
- **Протокол** — упорядоченный набор шагов (`ProtocolStep`) с типами (`ProtocolStepType`:
  wait/checklist/timer/care/medication/note), таймингом (`TimingSpecType`:
  rel_before/rel_after + `offset_seconds`) и якорями (`ProtocolAnchorType`).
- UI: список протоколов + активные раны (`/protocols`), визуальный конструктор шагов
  с `duration_picker` и селектором типа (`/protocols/new`, `/{id}/edit`),
  интерактивный чеклист рана с прогресс-баром и эмуляцией отметки по ADR-129
  (`/{id}/run`).
- Раны: `ProtocolRun` (scheduled/active/completed/aborted) + журнал `ProtocolStepLog`
  с `planned_at`/`completed_at`; завершение шага — `POST /protocols/{run_id}/steps/{step_id}/complete`.
- Все мутации — через сервисы с `ActorContext(owner_manual)`, авторство фиксируется.

## 58. Community Governance: роли, модерация, передача владения (ADR-143)

`app/models/community_roles.py` (`CommunityMemberRole`) + эндпоинты в `app/api/communities.py`:
- **Передача владения** — `POST /communities/{id}/transfer-ownership` (только текущий
  владелец, активному участнику).
- **Со-модераторы** — `POST /communities/{id}/moderators/add` и `/remove`
  (владелец назначает/снимает роль модератора; `role_type` хранится в
  `CommunityMemberRole`, набор ролей участника агрегируется на странице сообщества).
- Список ролей и проверка прав — через сервис `list_member_roles`/`assign_member_role`.

## 59. Agency & Capability (D/s делегирование v2, ADR-145)

`app/models/agency.py` (`AgencyPolicy`, `AgencyLevel`) + `app/models/capability.py`
(`CapabilityGrantV2`, миграция 085) + `app/models/dynamic.py` (`DynamicDefinition`,
`DynamicRun`, миграция 086):
- **Agency** — политика «Полного Делегирования» (ADR-129): уровни
  (`AgencyLevel`), границы контроля Верхнего над блоками профиля Нижнего.
- **Capability** — точечные гранты возможностей (`CapabilityGrantV2`), проверяются
  на мутациях; фоновые условия в `services/`.
- **Dynamic Engine** — сквозные динамические условия/триггеры с персистентным
  журналом ранов.

## 60. Навигация «Тёмный архив»: 5 разделов и feature-гейтинг (R10.1, ADR-141/144)

`app/templates/base.html` (макрос `nav_groups()`, общий для десктоп-сайдбара и
мобильного drawer):
- Пункты сгруппированы в 5 разделов: **Сегодня / План / Тело & Рутина / Связи / Система**.
- Пункты выключенных модулей скрываются по `ProductComposition` (`composition.*_enabled`)
  теми же флагами, которыми регистрируются роуты (журнал, каталог, здоровье/уход/послеуход/
  медикаменты, инсайты, матрица согласий, LockTimer, соцсеть).
- Мёртвые шаблоны прототипа удалены (R9.1): `dashboard.html`, `components/live_camera_observer.html`.

## 61. Качество: локализация и доступность (2026-08-28)

### Session 42 — защищённые страницы и формы

- `portal.spec.ts`: a11y-маршруты расширены до 47 пользовательских + 7 admin-страниц.
- Проверены dark/light и axe tags `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`.
- Отдельно проверены `/social/leaderboard`, `/social/pillory`, `/certificates/{id}/verify`, `/admin/tiers`.
- Результат: 0 serious/critical violations.



- **i18n консистентность** — `tests/test_localization.py` (15 тестов): строгий parity EN/RU
  (ключи 1:1, без пустых значений), согласованность `{var}`-плейсхолдеров, проверка всех
  статических `t.<key>` в шаблонах и JS-ключей (`T.*`, `I18N.*`, `i18n.*`) на наличие в обоих
  словарях, валидность `page-i18n` JSON-блоков, покрытие динамических префиксов
  (`t['health_phase_' + x]` и т.п.), unit-тесты `detect_locale`.
- **Полный a11y-аудит** — `@a11y` e2e (axe wcag2a/2aa/wcag21a/wcag21aa, серьёзные/критические нарушений нет)
  покрывает 47 пользовательских + 7 admin-роутов × темы dark/light: нав-страницы, social,
  billing, DMS, communities, insights, analytics, `/admin/*`, `/admin/tiers` и публичный
  `/certificates/{id}/verify`.
  В аудите исправлены: `/dms` (500 из-за legacy TemplateResponse), `<html lang>` на 7 роутax,
  aria-лейблы для selects/inputs/textarea/checkbox/range, контрасты status/accent/archive
  токенов и цветных статусов в обеих темах; добавлен тест admin-контекста через DB promotion.
- **Защищённые роуты**: `/admin/tiers` проверяется реальным admin-контекстом через тестовый DB promotion;
  `/social/leaderboard` и `/social/pillory` — authenticated; `/certificates/{id}/verify` — public.
- **CI** — 6 джобов (lint, memory-lint, migrations, test, docker, e2e), все зелёные;
  `timeout-minutes` + кеш pip; миграции 083/084 идемпотентны, добавлена 090 (колонки users);
  e2e-флоу обновлён под onboarding/session-wizard; `/locktimer` за feature-гейтом.
