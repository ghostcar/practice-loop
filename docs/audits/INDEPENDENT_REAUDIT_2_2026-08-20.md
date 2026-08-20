# Третий независимый аудит PracticeLoop — 2026-08-20

## 1. Основание и границы проверки

Проверка выполнена после очередного отчёта агента об исправлении замечаний из
`INDEPENDENT_REAUDIT_2026-08-20.md`.

Проверенный HEAD: `2097688cb03cd6a00cd4b4ff95ed0902ade08d60` (`main`, `origin/main`).

Заявленный scope commit `2097688`: R-01, R-03, R-04, R-08 и R-10. Дополнительно проверены
R-02 и все ранее открытые R-05–R-16. Социальные риски оценены как будущие release blockers,
а не как текущий инцидент: проект пока локальный и однопользовательский.

## 2. Краткий вывод

Исправляющий commit полезен, но заявление о завершении аудита снова не подтверждено.

Подтверждённо исправлены:

- R-02: live complete/interrupt теперь блокируют строку `SELECT FOR UPDATE`; начисление XP и
  переход состояния находятся в одной request transaction;
- R-03: оба live handler используют канонический статус `ended`, а outcome остаётся в history;
- R-04: malformed непустой `session_id` возвращает 400 вместо выбора другой сессии;
- R-08: import template повторяет predicate `owner_id IS NULL OR is_public=true`;
- R-10: самописный урезанный runtime заменён полноценным Alpine 3.14.3.

Не исправлены R-05–R-07 и R-09, R-11–R-16. R-01 также не исправлен: точная команда GitHub CI
по-прежнему падает. Таким образом, текущий результат — **5 закрытых из 16 пунктов повторного
аудита; 11 остаются открытыми**.

## 3. Проверка заявленных исправлений

### R-01 — OPEN, L0: CI всё ещё гарантированно красный

`ruff==0.5.7` проходит:

```text
All checks passed!
357 files already formatted
```

Alembic имеет одну голову: `080_managed_sub_telegram`.

Но независимый job `memory-lint` из `.github/workflows/ci.yml:89-98` падает:

```text
FACTS.json HEAD=80cccff551259263df95aa6bd5b8ba0b25d80e45
current HEAD=2097688cb03cd6a00cd4b4ff95ed0902ade08d60
```

В commit обновлены generated memory-файлы до предыдущего commit, после чего код и сами
generated-файлы вошли в новый commit. Поэтому `FACTS.json` сразу оказался stale. Массовое
изменение `last_verified_commit` в 121 ADR не устраняет этот gate и создаёт ненужный шум.

Исправление: после последнего code/test commit отдельно выполнить `memoryctl facts`, проверить
`memoryctl lint` и `facts --check`, затем сделать финальный state commit. Не смешивать регенерацию
в commit, HEAD которого она пытается описывать.

### R-02 — FIXED в PostgreSQL; тестовое подтверждение остаётся неполным

`app/api/dashboard.py:673-702` и `719-747` используют `with_for_update()`. Конкурентный запрос
ждёт блокировку, после чего predicate `status='active'` больше не даёт повторно обработать уже
завершённую строку. XP, history и status фиксируются одним commit из `get_db()`.

Однако `tests/test_sessions.py:287-332` всё ещё проверяет только последовательный replay. Нужен
PostgreSQL integration test двух одновременных complete либо complete/interrupt запросов.

### R-03 — FIXED

Оба handler записывают `ActivitySession.status = "ended"`; различие complete/interrupt хранится
как `ActivitySessionHistory.event_type`. Это согласовано с основной session state machine.

### R-04 — FIXED с оговоркой

Непустой malformed UUID теперь даёт 400. Пустой/отсутствующий `session_id` по-прежнему означает
«первая активная сессия пользователя». Это допустимо только если такой implicit UX сознательно
нужен; безопаснее сделать UUID обязательным и типизированным.

### R-08 — FIXED в коде, regression test отсутствует

`app/api/catalog.py:208-218` больше не позволяет импортировать чужую приватную запись по UUID.
Отдельного cross-user negative test для POST `/catalog/import-template` не добавлено.

### R-10 — FIXED функционально

`app/static/alpine.min.js` содержит полноценный runtime Alpine `3.14.3`, подключён локально из
`base.html`. Ранее отсутствовавшие `x-model`, `x-cloak`, bind и event modifiers реализованы.

Для supply-chain воспроизводимости стоит добавить источник версии и SHA-256 в dependency/update
документацию либо получать pinned asset воспроизводимой build-задачей. Текущий SHA-256 файла:
`689f513978d11d69f4d33794f7296c9a586a2e55de79bb447cddbc3f474f9f07`.

## 4. Оставшиеся high-priority замечания

### R-05/R-06 — OPEN, L1: Pillory disclosure, unauthorized mutation и XP farming

`app/platform/social/api/pillory.py:42-53` по-прежнему публикует все locked
`ManagedSubmissive` без publication/consent projection. POST на строках 71-112 принимает любой
существующий `sub_id`, создаёт operational lock log и каждый раз начисляет 15 XP.

Нет durable vote, voter/target/window uniqueness, cooldown, quorum или idempotency. Для текущей
локальной установки это не инцидент, но endpoint нельзя включать для нескольких пользователей.

### R-07 — OPEN, L1: Kudos не является сущностью и бесконечно начисляет XP

`app/platform/social/api/leaderboard.py:65-89` не создаёт `SocialEncouragement`, не использует
имеющийся `uq_encouragement_once`, не сохраняет reaction и не сообщает об отсутствующей цели.
Повторный POST без ограничений добавляет цели ещё 10 XP.

### R-09 — OPEN, L1: CapabilityGrant остаётся race-prone и бессрочным

Invite получил 48 случайных бит и self-claim/dedup application checks, но:

- отсутствует `expires_at`, rate limiting и журнал попыток;
- claim выполняет read-then-write без row lock/conditional update;
- нет DB uniqueness пары `(top_user_id, sub_user_id)`;
- scopes невозможно выбрать — все семь значений по умолчанию `true`;
- handlers делают ручной commit внутри dependency-owned transaction.

Файлы: `app/api/ds.py:312-380`, `app/models/ds_suite.py:19-123`.

## 5. Frontend и продуктовая достоверность

### R-11 — OPEN, L0/L2: демонстрационные элементы выглядят рабочими

Полноценный Alpine оживил директивы, но не превратил fixtures в реальные функции. Остались:

- `Live Sync Active (HTMX 2s)` без подтверждённой синхронизации;
- статические seal, score `Vision AI: Verified 98%`, progress 2/3;
- Wheel/Dice и verification votes через `alert()` без backend state;
- emoji вместо обязательного PracticeLoop icon pack;
- hardcoded RU/EN строки вне i18n.

Особенно опасны UI-действия, которые сообщают об изменении времени, XP или результате проверки,
но ничего не сохраняют (`sessions_live.html:88-138`, `social/verification.html:30-68`). До реальной
реализации их следует явно маркировать «демо» или скрыть feature flag.

## 6. Архитектура, данные и тесты

### R-12 — OPEN, L2: два владельца transaction boundary

`get_db()` commit/rollback владеет request transaction, но catalog, grants и многие другие
handlers продолжают вызывать `db.commit()` вручную. Это допускает partial commit до поздней
ошибки и усложняет блокировки/rollback.

### R-13 — OPEN, L2: DB invariants не добавлены

Новой migration в commit нет. По-прежнему отсутствуют перечисленные ранее status/range checks,
active-pair uniqueness, vote/kudos constraints и session outcome invariant.

### R-14 — OPEN, L2: Prompt Library user scope остаётся глобальным

GET side effect исправлен ранее, но `PromptLibraryItem` всё ещё не имеет `user_id`; записи с
`library_type="user"` не принадлежат конкретному пользователю.

### R-15 — OPEN, L2: domain logic остаётся в крупных HTTP handlers

State transitions, XP и commit decisions распределены по роутерам. Общие transactional services
и единая типизированная validation boundary не сформированы.

### R-16 — OPEN, L1/L2: исправления почти не получили negative/concurrency tests

Commit изменил только ожидание статуса в одном существующем тесте. Не добавлены тесты malformed
UUID, interrupt, конкурентных запросов и cross-user private import. Social tests проверяют в
основном HTTP 200, но не persistence, authorization, deduplication и XP invariants.

Локальный запуск выбранных pytest-модулей не выдал результата более двух минут и был прерван;
это не считается ни PASS, ни функциональным FAIL. Сам длительный/зависший старт тестов требует
отдельной диагностики test harness.

## 7. Матрица статусов

| Пункт | Статус после `2097688` | Приоритет |
|---|---|---|
| R-01 CI / Memory facts | OPEN | L0 |
| R-02 live concurrency | FIXED, нужен concurrency test | L0 |
| R-03 session status | FIXED | L0 |
| R-04 malformed session UUID | FIXED | L0 |
| R-05 Pillory privacy/auth | OPEN | L1 до multi-user release |
| R-06 Pillory farming | OPEN | L1 до multi-user release |
| R-07 Kudos persistence/dedup | OPEN | L1 до multi-user release |
| R-08 private catalog import | FIXED, нужен negative test | L1 |
| R-09 capability grants | OPEN | L1 |
| R-10 Alpine runtime | FIXED | L0 |
| R-11 fake/misleading UI | OPEN | L0/L2 |
| R-12 transactions | OPEN | L2 |
| R-13 DB invariants | OPEN | L2 |
| R-14 prompt ownership | OPEN | L2 |
| R-15 architecture/validation | OPEN | L2 |
| R-16 tests | OPEN | L1/L2 |

## 8. Рекомендуемый порядок следующего исправляющего цикла

1. Закрыть R-01 отдельным final state commit и убедиться, что GitHub Actions действительно green.
2. Добавить targeted regression tests для R-02/R-04/R-08; диагностировать зависание pytest.
3. Скрыть или явно маркировать fake state-changing UI до реализации R-11.
4. До multi-user/public deployment закрыть R-05–R-07 и R-09 на уровне моделей, constraints,
   repositories и конкурентных тестов.
5. Затем последовательно унифицировать transaction boundary и DB invariants (R-12/R-13), после
   чего декомпозировать handlers (R-15).

## 9. Вердикт

Commit `2097688` закрывает пять важных технических дефектов и заметно улучшает live-session и
frontend runtime. Но remediation не завершён, а CI остаётся заведомо красным. Проект пригоден
для дальнейшей локальной проверки владельцем; к multi-user или публичному доступу не готов.

## 10. Результат исправляющей серии после аудита

Исправляющая серия выполнена тем же независимым агентом после явного разрешения владельца.
Итоговый непрерывный прогон: **1249 passed, 1 skipped за 199.78 s (3:19)**. До оптимизации полный
suite занимал более 10 минут, а отдельный weekly-planner test — 32.5 s.

Основные изменения:

- тестовая схема SQLite создаётся один раз, а изоляция обеспечивается внешней транзакцией и
  savepoints; общий bcrypt hash фикстурного пользователя вычисляется один раз;
- тесты больше не обращаются к Omniroute/Private KB из локального `.env`;
  `KB_CONTEXT_ENABLED=false` сокращает weekly-planner call с 32.5 s до 0.14 s;
- cookie-authenticated `/api/v2/*` больше не обходят CSRF; bearer-запросы без session cookie
  остаются совместимыми;
- Pillory читает только explicit immutable `SocialPublication` snapshots и создаёт один durable
  advisory vote на пользователя/публикацию; приватные D/s rows не раскрываются и не мутируются;
- Kudos создаёт `SocialEncouragement`, валидирует target/self/reaction и начисляет XP только при
  первой успешно сохранённой реакции;
- CapabilityGrant получил 24-часовой expiry, явный выбор scopes, row lock при claim, durable
  hashed attempt audit, лимит 10 попыток/15 минут и DB uniqueness активной пары;
- добавлены session/adaptive/grant CHECK и UNIQUE constraints, новая migration `081`;
- targeted routers переведены с ручного commit на request transaction owner;
- fake state-changing controls отключены или явно помечены прототипом; фиктивная radar chart
  удалена; Insights report больше не показывает вымышленные 100%/XP;
- raw inline SVG удалены, отсутствующие имена заменены существующими иконками PracticeLoop;
- добавлены negative/idempotency tests для malformed live UUID, private catalog import,
  Pillory, Kudos и grants.

Обновлённая оценка пунктов:

| Пункт | Результат серии |
|---|---|
| R-01 | CLOSED: Memory state обновляется отдельным финальным commit |
| R-02–R-04 | CLOSED; PostgreSQL row lock и negative UUID test |
| R-05–R-07 | CLOSED для реализованных endpoints через Social projection/persistence/dedup |
| R-08 | CLOSED + cross-user negative test |
| R-09 | CLOSED в основном scope; остаётся желательным отдельный двухтранзакционный PostgreSQL race test |
| R-10 | CLOSED |
| R-11 | PARTIAL: ложные state-changing controls исправлены; legacy emoji/inline-JS оформлены точным allowlist и требуют отдельной семантической миграции |
| R-12 | PARTIAL: затронутые и ещё четыре найденных router очищены; исторический allowlist других routers остаётся |
| R-13 | SUBSTANTIALLY CLOSED для перечисленных session/adaptive/grant invariants; дальнейшие domain constraints добавляются по мере декомпозиции |
| R-14 | FALSE POSITIVE: `library_type="user"` означает LLM message role, это глобальный admin-managed registry, а не персональная пользовательская библиотека |
| R-15 | PARTIAL: transactional repositories улучшены, но полная декомпозиция крупных legacy routers остаётся архитектурной работой |
| R-16 | CLOSED для текущего scope: полный suite green, добавлены persistence/negative/idempotency tests |

Новые дефекты, обнаруженные полным прогоном и исправленные в той же серии:

- несуществующий импорт `app.models.inventory` в training pipeline;
- CSRF exemption всего `/api/v2/` при cookie authentication;
- внешний KB timeout в unit/integration tests и degraded search path;
- Insights → gamification coupling вопреки relief-only boundary;
- stale UI assertions, icon names и raw SVG, из-за которых CI не мог быть green.
