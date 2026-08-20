# Повторный независимый аудит PracticeLoop — 2026-08-20

## 1. Основание и область проверки

Повторный аудит проведён после отчёта другого агента о завершении исправлений по документу
`docs/audits/INDEPENDENT_AUDIT_2026-08-20.md`.

Проверенный HEAD: `c540178e4911cfae23cdbe5872a2c764bd35cb6d` (`main`, `origin/main`).

Проверены commits:

- `ae99a80` — Ruff formatting;
- `720d7d7` — заявленные исправления A-01, A-02, A-04, A-09;
- `a1a5939` — заявленные исправления A-05, A-07, A-12;
- `1df01ea` — заявленные исправления A-03, A-06, A-08;
- `c540178` — функциональный тест live-session anti-replay.

Проверка включала ручную трассировку HTTP handlers, моделей, шаблонов и тестов, а также
точные CI-команды Ruff 0.5.7, Memory v2 checks и Alembic heads.

## 2. Итог

Заявление о полном завершении работ не подтверждено. Исправления улучшили проект, но часть
аудиторских пунктов закрыта лишь частично, некоторые не затронуты, а в live-session и public
catalog появились новые дефекты.

Подтверждённо закрыты или существенно исправлены:

- A-06: Social feature flags снова выключены по умолчанию;
- A-09: персональные HTML routes удалены из Service Worker pre-cache;
- A-12: GET `/prompts/library` больше не выполняет seed/commit;
- A-18: точные Ruff 0.5.7 check и format check проходят;
- A-02: adaptive step lookup теперь проверяет владельца программы, базовые входные значения
  ограничены.

Не закрыты или закрыты частично:

- A-01, A-03, A-04, A-05, A-07, A-08, A-10, A-11, A-13, A-14, A-15, A-16;
- CI остаётся красным из-за stale Memory facts.

## 3. Блокирующие и высокоприоритетные находки

### R-01 — L0: GitHub CI продолжает гарантированно падать

Ruff gate исправлен:

- `ruff==0.5.7 check app/ cli.py tests/ seed_prod.py` — PASS;
- `ruff==0.5.7 format --check app/ cli.py tests/ seed_prod.py` — PASS;
- результат formatter: `357 files already formatted`.

Однако independent job `memory-lint` падает:

```text
FACTS.json HEAD=f6dd8e61690a181b63cb8928208c396a0fe43a05
current HEAD=c540178e4911cfae23cdbe5872a2c764bd35cb6d
```

Последний тестовый commit не сопровождён обновлением `memoryctl facts`. Поэтому GitHub workflow
всё ещё получает failure и продолжает отправлять уведомления.

Исправление: после финального code/test commit выполнить `python -m tools.memoryctl facts`,
проверить `memoryctl lint` и `facts --check`, затем закоммитить generated state согласно
Memory v2 workflow.

### R-02 — L0: live completion защищён только от последовательного replay

Handler выбирает активную сессию обычным `SELECT`, меняет ORM-object и начисляет XP. Два
конкурентных запроса могут оба прочитать `status="active"` до commit и оба начислить награду.

Отсутствуют:

- `SELECT ... FOR UPDATE`;
- conditional `UPDATE ... WHERE status='active' RETURNING`;
- version/optimistic lock;
- уникальный ledger/idempotency key результата сессии.

Добавленный тест выполняет запросы последовательно. Он подтверждает только то, что второй запрос
после commit не находит активную сессию; concurrency race не проверяется.

Файлы: `app/api/dashboard.py:659-697`, `tests/test_sessions.py:287-332`.

### R-03 — L0: live handler записывает статусы вне session state machine

Модель и основной API используют переходы:

```text
created → active → ended
```

Live endpoints записывают `completed` и `interrupted`. Остальной код считает завершённой только
сессию со статусом `ended`. В результате завершённая live-сессия продолжает удовлетворять
условиям `status != 'ended'`; UI может показывать attach/detach controls, а API — разрешать
изменения, предназначенные только для незавершённой сессии.

Файлы: `app/models/session.py`, `app/api/dashboard.py:686-727`,
`app/templates/sessions.html:69-95`.

Исправление: сохранить единый статус `ended`, а тип результата (`completed`/`interrupted`)
записывать в history/outcome field либо официально расширить state machine во всех consumers,
модели, миграции и тестах.

### R-04 — L0: невалидный session_id завершает другую активную сессию

При ошибке `uuid.UUID(session_id)` handler выполняет `pass` и продолжает исходный запрос без
ID-фильтра. Затем выбирается первая активная сессия пользователя.

Следовательно, malformed или повреждённый form value может завершить/прервать не ту сессию и
изменить XP. Должен возвращаться `400/422`, а path/form параметр лучше объявить как UUID.

Файл: `app/api/dashboard.py:675-682`, аналогично interrupt `716-723`.

### R-05 — L1: Pillory cross-user disclosure и mutation не исправлены

GET по-прежнему выбирает все `ManagedSubmissive` с `chastity_status="locked"` напрямую из
operational D/s-таблицы. Нет отдельной publication/consent projection.

POST по-прежнему принимает любой существующий `sub_id`, пишет `ChastityLockLog` и начисляет XP.
Добавленные проверки UUID и allowlist `vote_type` полезны, но не решают ownership/privacy.

Файл: `app/platform/social/api/pillory.py:35-112`.

Для локального однопользовательского режима это не текущий инцидент, но остаётся release blocker
перед вторым пользователем или внешним доступом.

### R-06 — L1: Pillory anti-farming отсутствует

В commit message заявлено anti-farming, но durable vote не создаётся. Отсутствуют:

- уникальность voter/target/window;
- cooldown;
- quorum;
- idempotency;
- связь XP с первым успешно созданным vote.

Каждый повторный POST добавляет ещё один lock log и ещё 15 XP. Перенос двух commits в одну
request transaction устранил partial commit, но не replay/farming.

### R-07 — L1: Kudos не сохраняется и допускает бесконечное начисление XP

Исправление изменило получателя XP: теперь награда идёт target user. Однако:

- `reaction` только проверяется, но не сохраняется;
- `SocialEncouragement` не создаётся;
- нет уникальности/cooldown;
- отсутствует audit trail;
- повторный POST бесконечно увеличивает XP цели;
- несуществующий alias возвращает success redirect без результата.

В проекте уже есть `SocialEncouragement` и constraint `uq_encouragement_once`; endpoint должен
использовать существующую модель/repository.

Файл: `app/platform/social/api/leaderboard.py:65-93`.

### R-08 — L1: import public template позволяет копировать приватный объект по UUID

Страница `/catalog/public` теперь корректно выбирает system/public items. Но POST
`/catalog/import-template` ищет `ActivityCatalogItem` только по ID и не повторяет visibility
predicate.

При знании UUID пользователь может скопировать чужую приватную запись. Исправление:

```text
WHERE id=:id AND (owner_id IS NULL OR is_public=true)
```

Нужен cross-user negative test.

Файл: `app/api/catalog.py:194-229`.

### R-09 — L1: CapabilityGrant исправлен частично

Положительные изменения:

- случайная часть invite code увеличена с 24 до 48 бит;
- запрещён self-claim;
- перед созданием `ManagedSubmissive` проверяется существующая пара.

Остаются дефекты:

- нет expiry;
- нет rate limit/attempt audit;
- claim остаётся read-then-write без row lock/conditional update;
- два конкурентных claim могут активировать один grant или создать конфликтующие связи;
- нет DB uniqueness для пары `(top_user_id, sub_user_id)`;
- все capability scopes выдаются как `true`;
- нет ограничения на активные grants одной пары.

Файлы: `app/api/ds.py:315-372`, модель и migration `078`.

## 4. Frontend re-audit

### R-10 — L0: A-04 не закрыт — добавлен неполный самописный Alpine runtime

Вместо официального Alpine или HTMX реализации добавлен файл размером около 1.6 KiB, который
реализует только часть `x-data`, `x-show`, `x-text` и `@click` через `new Function`.

Шаблоны реально используют также:

- `x-model`;
- `x-cloak`;
- `:class`;
- `:stroke-dashoffset`;
- `@click.away`.

Эти директивы runtime не реализует. Поэтому health sliders/checkboxes, динамические классы,
timer ring, click-away modals и cloak behavior остаются неисправными.

Дополнительно selector `button[@click], [\\@click]` содержит потенциально невалидную первую
часть; ошибка `querySelectorAll` остановит инициализацию всего компонента. Ошибки выражений в
нескольких местах молча подавляются пустыми `catch`.

Файл: `app/static/alpine.min.js`.

Рекомендация: не развивать самописный evaluator. С учётом установленного стека переписать
интерактивность на HTMX/progressive enhancement. Если владелец принимает Alpine — подключить
официальный pinned self-hosted build и оформить архитектурное решение.

### R-11 — L0/L2: fake runtime UI в основном не исправлен

Остались:

- Co-op fake timer/status/`Live Sync Active` без синхронизации;
- статический verification fixture с alias/seal/`Vision AI 98%`;
- Wheel/Dice через `alert()` без persisted state;
- live page, не загружающая конкретную active session в page context;
- многочисленные emoji и hardcoded RU/EN строки;
- неверные icon macro include/use patterns.

Public catalog получил реальный import endpoint, но этот частичный прогресс не закрывает A-03
и A-14 целиком.

## 5. Архитектура и данные

### R-12 — L2: transaction boundary не исправлен

`get_db()` остаётся transaction owner и делает commit после handler, но большое число API,
platform и Telegram handlers продолжает вызывать `db.commit()` вручную. Новые adaptive/grant/
catalog paths также сохраняют ручные commits.

Риски: частичные операции, невозможность позднего rollback, сложная concurrency semantics и
непоследовательные тесты. A-10 остаётся открытым.

### R-13 — L2: DB invariants не добавлены

В исправляющей серии отсутствуют новые Alembic migrations. Следовательно, не добавлены:

- status/action CHECK constraints;
- adaptive ranges и `(program_id, day_number)` uniqueness;
- capability expiry/active-pair uniqueness;
- vote/kudos persistence constraints;
- session outcome invariant.

A-11 остаётся открытым.

### R-14 — L2: Prompt Library закрыт только на уровне GET side effect

Seed/commit из GET удалён — это подтверждённое исправление. Но `PromptLibraryItem` всё ещё не
имеет `user_id`; записи `library_type="user"` остаются глобальными. Название UI «пользовательские»
не соответствует ownership модели.

### R-15 — L2: роутеры и validation существенно не переработаны

Domain transitions, XP и commits остаются непосредственно в `dashboard.py`, `ds.py`, catalog
и Social handlers. Крупные роутеры не разбиты на transactional services/repositories.
Непоследовательная ручная обработка UUID сохраняется. A-13 и A-15 открыты.

## 6. Тесты

### R-16 — L1/L2: тестовое покрытие всё ещё недостаточно

Добавлен один более содержательный тест live completion. Он проверяет:

- переход active session;
- +50 XP;
- последовательный повтор после commit.

Не проверяются:

- два конкурентных complete;
- compete complete/interrupt;
- malformed session ID;
- canonical `ended` state;
- cross-user live session;
- Pillory disclosure/replay;
- Kudos persistence/replay;
- private catalog import;
- grant concurrency/expiry;
- adaptive bounds/ownership;
- Service Worker logout privacy;
- frontend directives в реальном браузере.

Существующие Social/public catalog suites по-прежнему в основном проверяют `200 OK` и наличие
статического текста. A-16 закрыт лишь частично.

## 7. Проверенные gates

| Проверка | Результат | Комментарий |
|---|---:|---|
| Ruff 0.5.7 lint | PASS | точная версия CI |
| Ruff 0.5.7 format | PASS | 357 файлов отформатированы |
| Alembic heads | PASS | один head: `080_managed_sub_telegram` |
| Memory lint/facts | FAIL | stale FACTS после `c540178` |
| Targeted pytest | не подтверждён | запуск не завершился в контрольное окно среды |
| Новый live test отдельно | не подтверждён | дошёл до test body, но не завершился в контрольное окно |
| Полный pytest | не подтверждён | достоверного зелёного результата нет |
| Worktree | clean | повторный аудит не менял runtime code |

## 8. Матрица исходного аудита

| Пункт | Статус | Кратко |
|---|---|---|
| A-01 live XP/state | Частично | sequential replay закрыт; race и state mismatch остались |
| A-02 adaptive training | Частично/существенно | ownership и bounds добавлены; DB/commit/ramp limit остались |
| A-03 fake runtime UI | Не закрыт | исправлен только public catalog path |
| A-04 Alpine/interactivity | Не закрыт | самописный runtime не поддерживает используемые директивы |
| A-05 Pillory privacy | Не закрыт | всё ещё читает operational rows всех пользователей |
| A-06 Social defaults | Закрыт | defaults OFF |
| A-07 replay/farming | Не закрыт | Pillory/Kudos можно повторять |
| A-08 grant protocol | Частично | entropy/self-check/dedupe query; нет expiry/atomic/DB constraints |
| A-09 Service Worker | Закрыт в основном | private routes удалены из pre-cache |
| A-10 transactions | Не закрыт | ручные commits сохраняются |
| A-11 DB invariants | Не закрыт | migration отсутствует |
| A-12 GET prompt seed | Частично | GET исправлен; user prompts всё ещё global |
| A-13 validation | Не закрыт | malformed UUID regression подтверждён |
| A-14 frontend contract | Не закрыт | emoji/i18n/icon/CSP проблемы сохраняются |
| A-15 architecture | Не закрыт | domain logic остаётся в крупных routers |
| A-16 tests | Частично | один sequential functional test |
| A-17 static gates | Частично | Ruff green; Memory stale; pytest не подтверждён |
| A-18 CI failure | Частично | formatter исправлен; CI теперь падает на memory-lint |

## 9. Рекомендуемый следующий этап

### Приоритет 1 — восстановить истинно зелёный baseline

1. Исправить live handler: canonical `ended`, typed UUID, atomic conditional transition,
   ledger/idempotency и concurrency tests.
2. Исправить stale Memory facts после последнего commit и подтвердить GitHub run.
3. Устранить private catalog import IDOR и добавить cross-user test.
4. Заменить самописный Alpine runtime на HTMX или официальный pinned runtime; прогнать browser
   tests по всем используемым directives.

### Приоритет 2 — честное закрытие Social/D/s

1. Pillory строить только на explicit publication/consent projection.
2. Создать durable vote с uniqueness/window/quorum; начислять XP только после первой вставки.
3. Kudos реализовать через существующий `SocialEncouragement` repository/constraint.
4. Capability grants: expiry, atomic consume, rate limiting, audit и DB pair constraints.

### Приоритет 3 — архитектурная стабилизация

1. Единый transaction owner.
2. DB constraints и state enums/checks.
3. Thin routers и transactional services.
4. i18n/icon/navigation cleanup.
5. Полный PostgreSQL pytest, browser E2E, migrations roundtrip, Docker и production smoke.

## 10. Вердикт

Работа агента полезна, но формулировка «аудит полностью закрыт» некорректна. Ruff, Social
defaults, Service Worker pre-cache и часть adaptive/prompt behavior улучшены. При этом наиболее
важные state/concurrency, Social persistence/privacy, grant protocol, frontend runtime и
архитектурные замечания остаются.

Текущий HEAD можно продолжать использовать как локальный прототип, но нельзя считать стабильным
baseline для внешнего доступа или дальнейшего быстрого наращивания функций. Следующая итерация
должна закрывать R-01–R-10 с поведенческими и конкурентными тестами, а не только менять handlers
и route-smoke assertions.
