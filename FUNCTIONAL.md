# Practice Loop — текущий функционал (v0.8-actual)

> Живой документ. Описывает **фактическое состояние** кодовой базы (v0.8-actual),
> а не целевую спецификацию (v0.7-spec / REMEDIATION_SPEC.md).
> Расхождения «спека ↔ код» зафиксированы в ADR-029…034 (см. `memory/DECISIONS.md`)
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
| i18n | EN/RU (876 ключей), темы dark/light/system + 3 акцентных набора (ember/sage/slate) |
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
| `/llm-configs` | BYOK-конфиги провайдеров, активный конфиг, режимы full/abstract, хранение raw |
| `/measurements` | Замеры тела (утро/вечер), графики |
| `/medications` | Medication Organizer: лекарства/аптечки/остатки/расписание/факт приёма, экспорт для врача (§22) |
| `/health` | Health + Cycle foundation (4D): ежедневный check-in (настроение/энергия/сон/симптомы), анализы с оригинальным диапазоном, цикл с расчётной фазой (§23) |
| `/inventory` | Инвентарь: предметы, фото, сортировка drag&drop, shopping list |
| `/schedule` | Правила расписания дня (day_of_week + время + тип задачи + recurring) |
| `/import` | Импорт/экспорт данных: CSV/JSON шаблоны, upload, API-push, полный экспорт |
| `/calendar` | Шаблоны доступности (allowed/disallowed/passive_only) + отпуска-оверрайды |
| `/diets` | Диеты: планы, позиции (drag&drop), журнал потребления, LLM-генерация/оценка, синергия с тренировками, фото |
| `/sessions` | Сессии: создание, старт, завершение |
| `/notifications` | In-app уведомления, отметка прочитанным |
| `/achievements` | Доска достижений (обезличенная), скрытие |
| `/privacy` | Экспорт данных, удаление аккаунта, статус Telegram-привязки |
| `/settings` | Кастомизация: тема (dark/light/system), акцент, плотность, блоки дашборда, discretion (ADR-081) |
| `/locktimer` | Lock Timer: обзор, детали сессии, шаблоны (§16) |
| `/social/*` | Социальная подсистема: профиль, связи, лента, верификация, модерация (§17) |

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
- **Опт-ин** (`user_entity_opt_in`): пользователь осознанно отмечает допустимые задачи
  (да/нет + рейтинг + шкала желания).
- **Risk-gate (REM §5.2)**: `not_assessed` / `high` никогда не автоматизируются LLM;
  `elevated` — только с согласием. Seed-каталог предварительно оценён как `low`.

---

## 5. LLM-пайплайн

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
  для награды). Прерывание всегда со штрафом (ADR-029).

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
- **Приватность**: экспорт данных (JSON), полное удаление аккаунта или с сохранением
  обезличенных данных; обезличенная доска достижений.
- Cross-user изоляция: чужие private entities/thresholds не видны; импорт ищет Entity
  только owner/public.

---

## 15. Модель данных (таблицы)

Полный перечень таблиц `app/models/*` (80):

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
  плоские owner-scoped списки для мобильного клиента.
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
  `POST /state`, `POST /labs`, `POST /cycle/events`.
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
  `POST /entries`, `POST /partners`, `POST /entries/{id}/complete`. Object-level auth:
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
  `DELETE /products/{id}`, `POST /courses`. Object-level
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
  GET /runs/{id}.
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

Дополнение к Reminders (§29) и Telegram-боту. **Relief-only** (PD-013); без миграций.

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

Дополнение к Telegram-боту (§13, §30). **Relief-only** (PD-013); без миграций, бот EN-hardcoded.

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
