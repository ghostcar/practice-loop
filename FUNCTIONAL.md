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
| i18n | EN/RU (687 ключей), темы dark/light с сохранением |
| LLM | OpenAI-совместимые endpoints, BYOK: Omniroute (по умолчанию), Groq, OpenRouter |
| Telegram | aiogram 3.x (вебхук + исходящие уведомления) |
| Инфра | Docker Compose (app, PostgreSQL, Nginx+SSL), загрузки в volume `uploads` |
| Время | Всё хранится в UTC; отображение и границы суток — в часовом поясе устройства (cookie `client_tz`); фоновые job — `TG_AUTO_ANALYSIS_TZ` |
| API | Все JSON-эндпоинты консолидированы под `/api/v2`; SSR-страницы по своим путям (`/locktimer`, `/social`, …) |

---

## 3. Страницы и навигация

Главная навигация (6 пунктов): **Дашборд · Задачи · Тренировка · Каталог · Баллы · Админ**.
Дополнительно: Измерения, Инвентарь, Расписание, Импорт, Календарь, Диеты,
Уведомления, Приватность, LLM-конфиги. Мобильная версия — нижняя навигация (4 пункта).

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
| `/inventory` | Инвентарь: предметы, фото, сортировка drag&drop, shopping list |
| `/schedule` | Правила расписания дня (day_of_week + время + тип задачи + recurring) |
| `/import` | Импорт/экспорт данных: CSV/JSON шаблоны, upload, API-push, полный экспорт |
| `/calendar` | Шаблоны доступности (allowed/disallowed/passive_only) + отпуска-оверрайды |
| `/diets` | Диеты: планы, позиции (drag&drop), журнал потребления, LLM-генерация/оценка, синергия с тренировками, фото |
| `/sessions` | Сессии: создание, старт, завершение |
| `/notifications` | In-app уведомления, отметка прочитанным |
| `/achievements` | Доска достижений (обезличенная), скрытие |
| `/privacy` | Экспорт данных, удаление аккаунта, статус Telegram-привязки |

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
`/session`, `/settings` (EN/RU). Inline-кнопки ✅ Done / ⏹ Interrupt. Бот вызывает
внутренние сервисы напрямую (не HTTP); уведомления — хук после каждого db.flush().

---

## 14. Аутентификация, безопасность, приватность

- Регистрация email+пароль (без подтверждения), JWT-cookie, CSRF double-submit
  (все native-формы с hidden token, JS-fetch с X-CSRF-Token; /uploads — CSRF-bypass).
- Cookies Secure в production; logout только POST; пароли в .env, шифрование API-ключей.
- **Приватность**: экспорт данных (JSON), полное удаление аккаунта или с сохранением
  обезличенных данных; обезличенная доска достижений.
- Cross-user изоляция: чужие private entities/thresholds не видны; импорт ищет Entity
  только owner/public.

---

## 15. Модель данных (таблицы)

users, entities, user_entity_opt_in, activity_categories, activity_sessions, activity_logs,
activity_task_history, training_days, training_log_entries, diet*, points_transactions,
points_profiles, penalty_redemptions, achievements, user_achievements, notifications,
llm_provider_configs, calendar_templates, availability_windows, calendar_overrides,
schedule_rules, body_measurements, inventory_items, attachments, user_progress
(справочные таблицы update2.md: body_parts, task_locations, inventory_categories, …).

---

## 16. Lock Timer — персональный таймер закрытия (chastity, ADR-062)

Отдельный bounded context (`app/locktimer/`) с таблицами `lock_*`. Включается флагом
`LOCKTIMER_CORE_ENABLED=true`. Доступен на странице `/locktimer`.

### Модель
- **LockSession**: draft → active → completed / safety_stopped. duration_type, timezone,
  effective_end_at, merge_gap, random_seed (детерминированная генерация).
- **LockSlotRule**: 5 типов расписания (every_n_days, exact_datetime, recurring_from_date,
  flexible_window_once, after_previous_close). duration, grace, extend_on_late_open,
  require_tag.
- **LockTaskRule**: 6 типов расписания (daily, every_n_days, recurring_from_date,
  exact_datetime, anytime_before_end, deterministic_random). source_entity FK,
  media/verification/penalty/availability policies.
- **LockSlotOccurrence**: состояние pending→eligible→open→closed, planned_open/close,
  extension, close_tag_number.
- **LockTaskOccurrence**: состояние scheduled→visible→submitted→completed/review/failed/skipped.
- **LockTagViolation**: запись расхождения номерной бирки при verify.
- **LockLlmProposal**: AI-предложения правил (kind, items JSON, apply/reject).

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

### Social таблицы (все с префиксом `social_`)
social_profiles, social_consents, social_subjects, social_relationships, social_blocks,
social_grants, social_notifications, social_publications, social_verification_policies,
social_verification_requests, social_verification_votes, social_comments,
social_encouragements, moderation_reports, moderation_actions.

---

## 18. Универсальная медиа-система

Platform-level (`app/api/media.py`, `app/api/verification.py`), общая для Tracker и Timer.

- **media_assets**: owner-scoped (owner_type/owner_id), staged→ready→archived pipeline,
  MIME+magic-bytes validation, SHA-256, thumbnail (Pillow LANCZOS 400x400).
- **verification_challenges**: одноразовые коды, HMAC-SHA256 (plaintext не хранится),
  constant-time сравнение, TTL, max_attempts, алфавит без O0I1l.
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

## 20. Реализованные решения и направление развития

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
- **JSON-first контракт** (ADR-065): action-эндпоинты возвращают JSON — фундамент для мобильного клиента.
- **OCR/LLM верификация кодов** (Q13 в OPEN_QUESTIONS.md): отложено.
