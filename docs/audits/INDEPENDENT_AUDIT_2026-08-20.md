# Независимый аудит PracticeLoop — 2026-08-20

## 1. Резюме

Проверен `main` на commit `1e52043e2168f0e1ab7e391c557a995cb4920af2` после большой
серии изменений Steps 49–90. Аудит охватывает backend, структуру проекта, модели и
миграции, транзакции, frontend, информационную безопасность, приватность, PWA,
тесты и эксплуатационную готовность.

Проект пока используется только локально одним владельцем и не предоставлен другим
пользователям. Поэтому cross-user и Social-находки ниже не являются немедленным
инцидентом. Они остаются обязательными release blockers перед сетевым доступом,
регистрацией второго пользователя или публикацией приложения.

Общий вывод: кодовая база содержит сильный ранее созданный фундамент, но последняя
серия функций добавлена значительно быстрее, чем были закреплены доменные инварианты,
тесты и frontend-контракт. Текущий HEAD пригоден для локального прототипирования,
но не для внешнего доступа. Часть новых экранов является runtime-подключёнными
демонстрационными макетами, хотя визуально сообщает пользователю о реальной работе.

## 2. Шкала приоритетов с учётом локального режима

- **L0 — исправить до продолжения активной разработки:** дефект портит локальные данные,
  создаёт ложное состояние или ломает ключевой сценарий даже при одном пользователе.
- **L1 — исправить до подключения второго пользователя или внешнего доступа:** ownership,
  privacy, replay, grant/link security и публичные контуры.
- **L2 — технический долг ближайшей стабилизации:** архитектура, ограничения БД,
  frontend-контракт, i18n, поддерживаемость.
- **L3 — улучшение:** polish, наблюдаемость и оптимизация.

## 3. Основные находки

### A-01 — L0: live completion не связан с реальной сессией и позволяет бесконечно начислять XP

`POST /sessions/live/complete` не принимает session/task ID, не проверяет наличие активной
сессии, не сохраняет completion и не использует idempotency guard. Любой повторный POST
начисляет ещё 50 XP. `interrupt` аналогично не относится к конкретной сессии.

Файл: `app/api/dashboard.py:598-688`.

Последствия в локальном режиме: случайный double-click, refresh/replay или ручной вызов
искажает прогресс. Необходимо связать действие с owned `ActivitySession`/`ActivityLog`,
выполнять атомарный state transition и начислять результат единожды.

### A-02 — L0: adaptive training допускает изменение чужого шага и не валидирует нагрузку

`log_step_feedback_and_adapt()` находит `AdaptiveProgramStep` только по `step_id` и не
проверяет `AdaptiveProgram.user_id == user_id`. Переданный `user_id` фактически не используется.
При наличии второго пользователя это IDOR. Даже локально отсутствуют диапазоны для
`comfort_score`, `actual_minutes`, `total_days` и `difficulty_level`.

`total_days` напрямую используется в `range(1, total_days + 1)`. Большое значение создаст
огромное число ORM-объектов и строк. Алгоритм автоматически повышает длительность каждого
следующего шага без верхней границы и выдаёт rule-based решение за «ИИ».

Файлы: `app/agent/training_adaptive.py:17-116`, `app/api/training.py:700-747`.

### A-03 — L0: новые runtime-экраны содержат фиктивное состояние

- `/sessions/coop` показывает статические задания, таймер `03:04`, статусы участников и
  `Live Sync Active (HTMX 2s)`, но не выполняет синхронизацию и не загружает сессию.
- `/social/verification` всегда показывает фиктивные alias, seal number, `Vision AI 98%`
  и `2/3` голосов вместо реальных verification requests.
- live extensions Wheel/Dice только вызывают `alert()`, хотя сообщают об изменении времени
  и XP multiplier.
- `/catalog/public` заявляет community exchange, rating, opt-in и report, но выбирает только
  системные строки (`owner_id IS NULL`), а кнопки не имеют действий.
- `/social/kudos` игнорирует `target_alias` и `reaction`; запись kudos не создаётся, XP
  начисляется отправителю.

Это опаснее обычного placeholder: пользователь не может отличить сохранённое действие от
декорации. Демонстрационные экраны следует держать вне runtime либо явно маркировать demo.

### A-04 — L0: Alpine-синтаксис используется без Alpine runtime

Шаблоны используют `x-data`, `x-show`, `x-text`, `:class` и `@click`, но Alpine.js в
`base.html`, package manifests и локальных JS не подключён. В результате модальные окна,
вкладки и live timer не работают как задумано.

Затронуты как минимум `ds_keyholder.html`, `ds_portal.html`, `ds_checkins.html`,
`training_adaptive.html`, `prompt_library_user.html`, `sessions_live.html`,
`sessions_wizard.html`, `health_body_cycle.html` и другие новые шаблоны.

Это также расходится с установленным стеком «HTMX без тяжёлого JS-фреймворка». Следует либо
переписать интерактивность на HTMX/progressive enhancement, либо отдельно принять и локально
подключить Alpine как архитектурное решение.

### A-05 — L1: Pillory раскрывает и изменяет cross-user чувствительные данные

GET выбирает все `ManagedSubmissive` со статусом `locked` без publish/consent/owner scope.
В шаблон передаются имя, rules notes и compliance score. POST принимает любой `sub_id`, также
без scope, и записывает `ChastityLockLog` в чужой профиль.

Файл: `app/platform/social/api/pillory.py:42-110`.

Пока приложение строго локальное и однопользовательское, эксплуатационный риск невысок.
Перед вторым аккаунтом необходимо ввести отдельную publication/consent projection; нельзя
публиковать персональную operational-модель напрямую.

### A-06 — L1: Social включён по умолчанию вопреки staged rollout

Комментарий `Feature flags — all default OFF for safe rollout` противоречит значениям
`social_enabled`, `social_tracker_adapter_enabled`, `social_timer_adapter_enabled` и
`social_public_enabled`, установленным в `True`.

Файл: `app/config.py:34-40`.

Для локальной разработки допустимо включить эти значения в `.env`; безопасный default в коде
должен оставаться `False` до прохождения Social release gate.

### A-07 — L1: replay/farming в Pillory и Kudos

Pillory не имеет модели голоса, уникальности `(voter, subject)`, cooldown, quorum или
идемпотентности. Каждый POST добавляет лог и 15 XP. Неизвестный `vote_type` молча становится
`lock_extension`. Kudos аналогично не сохраняет target/reaction и каждый раз начисляет 10 XP
самому отправителю.

Файлы: `app/platform/social/api/pillory.py:71-110`,
`app/platform/social/api/leaderboard.py:65-79`.

### A-08 — L1: capability grant/link протокол недостаточно защищён

- invite code содержит только 6 hex-символов случайной части (24 бита);
- у grant отсутствует expiry;
- нет rate limit и attempt audit;
- claim выполняется read-then-write без row lock/conditional update;
- нет защиты self-claim;
- все scopes выдаются по умолчанию;
- нет DB-ограничения на допустимые статусы и активные пары;
- создаются повторные `ManagedSubmissive` для одной пары.

Файлы: `app/api/ds.py:315-368`,
`alembic/versions/078_add_capability_grants_table.py:21-43`.

Telegram link code для managed profile также не уникален на уровне БД. До внешнего Telegram
доступа нужны длинные одноразовые токены, expiry, atomic consume и rate limiting.

### A-09 — L1: Service Worker кэширует персональные страницы

Pre-cache включает `/`, `/agent/chat` и `/insights/trajectory`. Это аутентифицированные страницы
с чувствительными данными. Они могут остаться в Cache Storage после logout и быть показаны на
общем устройстве. `cache.addAll()` также может сорвать установку SW, если protected route
ответит ошибкой до login.

Файл: `app/static/sw.js:3-37`.

Кэшировать следует только versioned public static assets. Для authenticated HTML нужны
`Cache-Control: no-store` и явная очистка user-scoped cache на logout.

### A-10 — L2: transaction boundary системно нарушен

`get_db()` уже делает commit после успешного handler и rollback при исключении, однако поиск
обнаруживает 115 ручных `await db.commit()` в `app/api`, `app/platform` и `app/telegram`.
Это создаёт частичные транзакции и делает поздний rollback бесполезным.

Особенно показателен Pillory: сначала commit log, затем отдельный commit XP. Между ними возможна
полуприменённая операция. Аналогичная проблема видна в importers и новых D/s endpoints.

Файл: `app/database.py:18-26`.

Нужен единый transaction owner: HTTP dependency или service/use-case, но не оба одновременно.

### A-11 — L2: модели и миграции не закрепляют доменные инварианты

В новых таблицах свободными строками хранятся `status`, `action`, `chastity_status`,
`library_type`, `focus_domain`. Отсутствуют `CHECK` constraints для score/duration/difficulty,
уникальность program step `(program_id, day_number)`, ограничения capability grants и
managed-sub relationships. Несколько FK не задают явный `ondelete` в adaptive training.

В результате invalid state легко записывается любым code path, а не только ошибочным API.

### A-12 — L2: GET-запрос prompt library изменяет БД

`GET /prompts/library` вызывает `seed_prompt_library()`, который при необходимости вставляет
строки и делает commit. GET перестаёт быть безопасным и предсказуемым, а первый параллельный
запрос может столкнуться с unique race.

Кроме того, `PromptLibraryItem` не имеет `user_id`: элементы с `library_type="user"` являются
глобальными, хотя UI называет их пользовательскими.

Файлы: `app/api/prompt_templates.py:165-190`, `app/models/prompt_library.py`,
`app/prompt_library.py:148-176`.

### A-13 — L2: API validation непоследовательна

Часть path/form UUID объявлена как `str` и вручную передаётся в `uuid.UUID()`. Некорректное
значение приводит к необработанному `ValueError`/500 вместо 422. Строковые actions, modes,
scores и counts часто не имеют allowlist или границ. Для новых контрактов предпочтительны
типизированные path параметры и Pydantic/Form schemas.

### A-14 — L2: frontend нарушает DESIGN_V2 и icon-pack contract

- широко используются emoji как UI-иконки;
- присутствуют произвольные inline SVG;
- `{% include "components/icon.html" %}` лишь загружает определение macro, но не вызывает его;
- после include выводится `<use>` вне `<svg>` и с неверным sprite ID без `icon-` prefix;
- новые строки жёстко записаны на русском/английском вместо RU/EN i18n;
- навигация разрослась до нескольких десятков элементов;
- фиктивные статусы и действия ухудшают accessibility и доверие пользователя.

Пример: `app/templates/sessions_live.html:4-140`.

### A-15 — L2: роутеры слишком крупные и смешивают уровни абстракции

`dashboard.py` объединяет dashboard, achievements, notifications, session UI, wizard,
геймификацию и новые live/coop endpoints. В API-файлах выполняются доменные переходы,
начисление XP, создание зависимых объектов и commits. Это расходится с целевой структурой
thin router → transactional service → scoped repository и уже привело к A-01/A-05/A-10.

### A-16 — L2: новые тесты создают ложное ощущение полноты

Commit `6b50435` добавил шесть файлов, названных comprehensive suites. Большинство тестов
проверяет только `status_code == 200` и наличие статического текста. Они не проверяют:

- cross-user access;
- реальную co-op синхронизацию;
- отсутствие повторного XP;
- ownership adaptive steps;
- capability claim concurrency/expiry;
- поведение кнопок в браузере;
- соответствие UI сохранённому состоянию;
- Service Worker privacy;
- invalid input и DB constraints.

Например, kudos test проходит даже несмотря на то, что target и reaction полностью игнорируются.
Такие тесты полезны как route smoke, но не должны называться функциональным покрытием.

### A-17 — L2: статические quality gates не зелёные

На исходном audited HEAD `fbd2ac9`:

- `ruff check .` завершился с 72 ошибками;
- `memoryctl lint` сообщил stale `FACTS.json`;
- один Alembic head был сохранён;
- `compileall` прошёл;
- очевидных реальных секретов в tracked files не найдено.

После добавления тестов HEAD изменился на `1e52043`; FACTS был обновлён, но исправлений runtime
дефектов в commits `6b50435`/`1e52043` нет. Точечный новый pytest-run не завершился в контрольное
окно среды, поэтому полный suite нельзя документировать как подтверждённо зелёный.

### A-18 — L0: постоянное падение GitHub CI вызвано format gate

GitHub Actions workflow запускается на каждый push в `main`. Job `lint` выполняет:

1. `ruff check app/ cli.py tests/ seed_prod.py`;
2. `ruff format --check app/ cli.py tests/ seed_prod.py`.

Локальное воспроизведение показало: lint rules проходят, но `ruff format --check` завершается
ошибкой. Точным CI formatter `ruff==0.5.7` признаны неформатированными 36 файлов, включая новые
`app/agent/*`, `app/api/ds.py`, `app/api/dashboard.py`, `app/api/prompt_templates.py`,
`app/agent/training_adaptive.py`, Social API и добавленные тесты.

Это объясняет постоянные письма GitHub:

- `lint` падает на каждом push;
- jobs `test`, `migrations` и `e2e` имеют `needs: [lint]`, поэтому после падения lint
  пропускаются и весь workflow получает failure;
- серия работ создавала отдельный feature commit и следующий `docs(state)` commit с интервалом
  в несколько секунд; каждый commit в `main` запускал новый полный workflow и новое уведомление;
- в workflow нет `concurrency.cancel-in-progress`, поэтому устаревшие runs не отменяются;
- нет job/path filtering, и чисто документационные state commits также запускают lint,
  PostgreSQL migrations, browser E2E и Docker build.

Конфигурация версии Ruff согласована (`ruff==0.5.7` в CI и lockfile), поэтому причина не в
случайном обновлении formatter, а в том, что изменения коммитились без обязательного
`ruff format --check`/pre-push gate. Диагностика отдельно установила и запустила именно
проектный `0.5.7`: `ruff check` прошёл, `ruff format --check` вернул 36 файлов и ненулевой код.

Прямые GitHub logs получить не удалось: локальный `gh` token недействителен, а подключённый
GitHub connector возвращает только PR-triggered workflow runs, тогда как рассматриваемые runs
созданы push-событиями. Однако failing command воспроизведён локально по точной CI-конфигурации,
и он детерминированно объясняет текущий failure до запуска зависимых jobs.

Исправление CI:

1. В окружении с `ruff==0.5.7` выполнить `ruff format app/ cli.py tests/ seed_prod.py`.
2. Проверить `ruff check` и `ruff format --check` теми же путями и версией, что в workflow.
3. Добавить эти команды в pre-commit/pre-push либо единый `scripts/ci_local.sh`.
4. Добавить workflow-level concurrency, например группу по workflow/ref с
   `cancel-in-progress: true`.
5. Разделить code CI и docs/memory CI через path filters: документационный commit должен
   выполнять memory lint, но не обязан каждый раз поднимать PostgreSQL, Playwright и Docker.
6. Не использовать прямую серию мелких push в `main`: сначала локальные gates, затем один
   проверенный push или PR.
7. После восстановления `gh auth login` проверить первый новый run и только затем разбирать
   возможные ошибки, которые сейчас скрыты зависимостью `needs: [lint]`.

## 4. Положительные стороны

- Сохраняется один линейный Alembic head.
- Базовые CSRF middleware, security headers, owner-scoped repositories старых модулей и
  production secret validation уже существуют.
- Проект имеет заметное unit/integration покрытие исторических контуров.
- Пароли/API secrets отделены, явной утечки реальных секретов аудит не обнаружил.
- Для старых task completion путей существует атомарный `complete_once`.
- В social foundation уже есть более подходящие модели publications, consent и verification;
  новые Pillory/Leaderboard endpoints следует строить на них, а не на operational D/s rows.
- Memory v2 и preflight дают хороший каркас для контролируемой стабилизации.

## 5. Рекомендуемый план исправлений

### Этап 1 — честность локального прототипа

1. Восстановить зелёный CI: применить Ruff 0.5.7 formatter и прогнать точные CI-команды.
2. Убрать XP mutation из fake live/kudos/pillory flows либо реализовать persisted state machine.
3. Пометить demo UI или отключить маршруты feature flags до реальной реализации.
4. Исправить adaptive training ownership и поставить пределы входных значений.
5. Выбрать HTMX или Alpine; восстановить работоспособность всех новых контролов.
6. Удалить authenticated routes из Service Worker cache.

### Этап 2 — code health

1. Выделить `sessions`, `ds`, `adaptive_training`, `social_gamification` services/repositories.
2. Устранить ручные commits из HTTP layer и определить единый transaction owner.
3. Добавить DB constraints и уникальности.
4. Перевести UUID/actions/scores на типизированные схемы.
5. Исправить icon pack, i18n, inline scripts/handlers и навигацию.

### Этап 3 — release gate перед внешним доступом

1. Вернуть Social defaults в OFF; включать через `.env` только после gate.
2. Создать explicit publish/consent projection для Pillory.
3. Реализовать durable votes/kudos с uniqueness, audit и replay protection.
4. Усилить capability/Telegram token protocol и проверить concurrency.
5. Добавить cross-user tests для каждого object ID.
6. Прогнать PostgreSQL migrations up/down, полный pytest, browser suite, ruff,
   memory lint и production smoke.

## 6. Минимальный набор недостающих тестов

- `test_live_complete_requires_owned_active_session`
- `test_live_complete_is_idempotent_under_concurrency`
- `test_adaptive_step_cross_user_returns_404`
- `test_adaptive_input_ranges_and_total_days_limit`
- `test_pillory_requires_explicit_publication_and_consent`
- `test_pillory_vote_unique_per_voter_and_window`
- `test_kudos_persists_target_reaction_and_no_sender_farming`
- `test_grant_claim_atomic_expiring_non_self`
- `test_telegram_link_code_atomic_unique_expiring`
- `test_logout_clears_private_service_worker_cache`
- browser tests для modal/tab/timer controls без фиктивных `alert()`.

## 7. Итоговый вердикт

Для строго локального однопользовательского прототипа продолжать исследование можно после
исправления L0-находок: ложного runtime-состояния, XP replay, adaptive ownership/limits и
неработающей интерактивности. Social privacy/grant проблемы можно не считать срочным инцидентом,
но они должны оставаться явными L1 blockers перед появлением второго пользователя или сетевого
доступа.

Приоритет следующей итерации должен быть не в добавлении новых экранов, а в превращении уже
подключённых экранов из демонстраций в проверяемые доменные сценарии с атомарным состоянием.
