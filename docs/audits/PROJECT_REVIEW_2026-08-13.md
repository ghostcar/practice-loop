# Practice Loop — полный аудит проекта

Дата: 2026-08-13  
Аудируемый commit: `5ae8cc2bd3a791b9c5e013504264748647ee0329` (`main`)  
Режим: read-only review; исходный код, миграции и конфигурация не изменялись.

## 1. Итог

Practice Loop — функционально богатый и уже достаточно дисциплинированный прототип: есть единый
Alembic head, owner-scoped запросы в основных доменах, атомарные переходы состояний, CSRF,
production gate секретов, локальные frontend assets, типизированная проверка LLM-ответов и большой
набор тестов. Кодовая база заметно сильнее обычного раннего MVP.

Однако проект пока нельзя считать готовым к расширению доступа за пределы доверенного личного
контура. Главные причины — обход авторизации при раздаче загруженных файлов и небезопасный fallback
ключа verification challenge. Frontend функционален, но неоднороден: дизайн-система внедрена
частично, CSP практически заблокирован inline-кодом, а браузерных E2E/a11y-тестов нет.

Оценка текущего состояния:

| Область | Оценка | Вывод |
| --- | ---: | --- |
| Доменная архитектура | 7/10 | Сильные инварианты, но API и транзакционные границы местами перегружены |
| Качество backend-кода | 7/10 | Ruff clean, понятные модули; остаются крупные файлы и широкие обязанности |
| Безопасность и приватность | 5/10 | Хорошая база, но два блокера до публичного доступа |
| LLM-контур | 7/10 | Allowlist/schema validation есть; weekly planner валидируется неполно |
| Тестирование | 7/10 | 661 тест собран; сильные service/API tests, нет browser E2E и coverage gate |
| Frontend/UX | 5.5/10 | Рабочий responsive SSR UI, но визуальная и accessibility-консистентность средняя |
| Эксплуатационная готовность | 6.5/10 | Compose/Alembic/health checks есть; security headers и observability ограничены |

## 2. Методика и подтверждённый baseline

Проверены архитектура, роуты, модели, сервисы, LLM pipeline, media/verification, security middleware,
миграции, зависимости, Docker/Nginx, Jinja-шаблоны, JavaScript, i18n и тестовый корпус.

Факты:

- около 34 000 строк Python/Jinja/JS/CSS;
- 229 HTTP route declarations;
- 38 Jinja-шаблонов и 14 собственных JS-файлов;
- 661 pytest test collected;
- один Alembic head: `e5f6a7b8c9d`;
- `ruff check` — успешно;
- `ruff format --check` — 210 файлов уже отформатированы;
- `python3 -m compileall` — успешно;
- `docker compose config --quiet` — успешно;
- `memoryctl facts --check` — manifest актуален;
- `memoryctl lint` — 0 ошибок, 3 предупреждения;
- полноценный browser/E2E/axe/Playwright suite не найден.

Полный pytest был запущен дважды. В текущем execution environment прогон не вернул итоговый
summary за отведённое время; отдельный зависшим считавшийся memory-тест прошёл изолированно за
1.85 s. Поэтому отчёт подтверждает collection 661 tests и успешные точечные проверки, но не
повторяет прежнее утверждение `661/661 passed` без полученного в этой сессии summary.

## 3. Находки по приоритету

### P0-1. Приватные media-файлы доступны в обход авторизации

`app/main.py:145` монтирует весь `UPLOAD_DIR` как публичный `StaticFiles` на `/uploads`. При этом
`app/api/media.py:137` реализует отдельную owner-authorized выдачу media. Прямой URL вида
`/uploads/media/<uuid>.<ext>` проходит мимо проверки `MediaAsset.owner_id`.

Риск: раскрытие личных фотографий и отчётов любому, кто получил или угадал URL. UUID снижает
вероятность перебора, но не является контролем доступа; URL может попасть в историю, referer,
логи, бэкап или публикацию.

Рекомендация: не монтировать приватный upload root. Отдавать приватные originals/thumbnails только
через авторизованный endpoint либо через Nginx `X-Accel-Redirect` после owner/grant проверки.
Публичные redacted assets хранить в отдельном storage namespace с явной политикой публикации.

### P0-2. Verification HMAC использует известный fallback-ключ

`docker-compose.yml:38` передаёт `CHALLENGE_HMAC_KEY` как пустую строку по умолчанию.
`app/services/media.py:187` при пустом значении использует константу `default-challenge-key`.
Production validator в `app/config.py:106-137` проверяет JWT и credentials encryption key, но не
challenge key.

Риск: при доступе к хешу или связанному сценарию атакующий знает HMAC key; криптографическая
граница verification challenge перестаёт быть секретной.

Рекомендация: в production требовать отдельный случайный `CHALLENGE_HMAC_KEY` длиной не менее
32 bytes и завершать startup при пустом/placeholder значении. Не использовать fallback вне tests.
При уже созданных production challenges после исправления инвалидировать активные challenges.

### P1-1. `innerHTML` снова создаёт XSS-sensitive boundary

`app/templates/locktimer/session_detail.html:423-430` вставляет `data.warnings` и `data.errors`
через `innerHTML` без escaping. Даже если текущий service формирует только безопасные сообщения,
граница хрупкая: появление названия пользовательского правила или другого input в сообщении
превратит её в stored/reflected XSS.

Рекомендация: строить DOM через `textContent`/`createElement`; запретить прикладной `innerHTML`
lint-правилом. Добавить тест с HTML payload именно для LockTimer validation response.

### P1-2. Weekly LLM planner принимает произвольную дату модели

`app/llm/pipeline/generate.py:320-334` проверяет формат `YYYY-MM-DD`, но не принадлежность даты
запрошенному `target_dates`. Модель может создать валидную задачу на прошлую или далёкую дату.
Также неверные items молча пропускаются, поэтому контракт «ровно одна задача на день» фактически
не обеспечен.

Рекомендация: валидировать конечное множество дат, уникальность даты и полноту всех requested
days до записи; сохранять план одной транзакцией только после полной валидации. В случае ошибки —
retry или понятный отказ без частичного плана.

### P1-3. Media finalize не проверяет целевой domain object

`app/api/media.py:105-129` проверяет владельца media asset, но не существование и принадлежность
`owner_ref_id` выбранного `owner_type`. Можно связать свой asset с произвольным UUID или объектом
другого пользователя, нарушив целостность и будущие grant/publication правила.

Рекомендация: единый registry/adaptor owner types с `authorize_bind(user_id, ref_id)`, а не только
строковый allowlist. Финализация должна быть атомарна и отклонять отсутствующий/cross-user target.

### P1-4. Отсутствуют browser E2E и accessibility gates

Тесты хорошо покрывают HTTP и сервисы, но Playwright/Selenium/axe/pa11y/Lighthouse не найдены.
Это особенно рискованно для 38 шаблонов, HTMX swaps, 14 JS modules, drag-and-drop, charts,
mobile navigation и theme switching.

Рекомендация: минимальный Playwright smoke matrix RU/EN × light/dark × 360/768/1280 для login,
dashboard, task lifecycle, training, timer safety-stop и privacy export/delete. Добавить axe scan
ключевых страниц и keyboard-only сценарий.

### P1-5. Транзакционные границы неоднородны

`get_db()` автоматически делает commit после endpoint, но ряд endpoint/service paths также
вызывает `db.commit()` самостоятельно. В API-роутерах остаётся значительная бизнес-логика и
десятки явных flush/commit. Это усложняет понимание атомарности, rollback и переиспользование
use cases ботом/будущим mobile API.

Рекомендация: выбрать единый transaction-owner: application service/use-case. Роутер валидирует
HTTP input и вызывает сервис; сервис владеет одной транзакцией; repository не коммитит.

### P1-6. Security headers и строгая CSP отсутствуют

В приложении и Nginx не найдены CSP, HSTS, frame-ancestors/X-Frame-Options, Referrer-Policy и
Permissions-Policy. Одновременно шаблоны содержат inline `<script>`, inline handlers и runtime
Tailwind, поэтому безопасную CSP сейчас трудно включить без рефакторинга.

Рекомендация: сначала вынести inline JS/handlers в modules и собрать Tailwind CSS на build stage,
затем ввести report-only CSP и постепенно перейти к enforcing CSP. На HTTPS proxy добавить HSTS,
`X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy` и запрет framing.

### P1-7. Версия проекта расходится

`pyproject.toml` и README заявляют `0.8.0`, FastAPI metadata — `0.9.0`. Это повторяет ранее
зафиксированный класс документационных дефектов и мешает support/deploy diagnostics.

Рекомендация: один источник версии через package metadata, используемый приложением, CLI и docs.

### P2-1. Крупные файлы и концентрация обязанностей

Примеры: `app/i18n/{ru,en}.py` ~760 строк каждый, `social/models.py` 677,
`locktimer_commands.py` 642, `telegram/bot.py` 589, `dashboard.py` 568,
`diets.py` 535, `training.py` 494, `tasks.py` 488; `locktimer/session_detail.html` 546 строк.

Размер сам по себе не дефект, но здесь он коррелирует со смешением HTTP, query composition,
serialization, UI context и orchestration. Рекомендация — декомпозировать по use case, не по
произвольному числу строк, сохраняя публичные re-export контракты.

### P2-2. Async endpoints выполняют блокирующие media-операции

Upload читает файл целиком, синхронно пишет `Path.write_bytes`, а Pillow декодирует и создаёт
thumbnail внутри event loop. Лимиты размера ограничивают ущерб, но несколько одновременных upload
могут задержать все запросы worker.

Рекомендация: streaming upload с подсчётом лимита, файловые/Pillow операции через thread pool или
job queue; лимиты pixel count и decompression bomb handling проверять до тяжёлой обработки.

### P2-3. Readiness раскрывает текст исключения

`app/main.py:162-165` возвращает клиенту `str(exc)`. Там могут оказаться hostname, DB name или
детали подключения. Рекомендация: наружу только `not ready`, подробности — structured server log.

### P2-4. Memory v2 denylist конфликтует с репозиторием

`memoryctl lint` сообщает три tracked denylist paths: `.env.example` и два self-hosted Inter font.
Это не runtime-дефект, но CI warning перестаёт быть информативным. В частности, blanket `.env*`
конфликтует с безопасным шаблоном `.env.example`, а запрет font assets конфликтует с DESIGN.

Рекомендация: уточнить модель denylist/allowlist так, чтобы секретные `.env` блокировались, а
санитизированный `.env.example` и проверенные vendored assets имели явное исключение с provenance.

## 4. Backend и архитектура

### Сильные стороны

- FastAPI/SQLAlchemy async используются последовательно в основном data path.
- Один Alembic head, миграции отделены от startup `create_all`.
- Product composition централизует tracker/timer/social feature gates.
- Owner filters и cross-user tests присутствуют во многих доменах.
- Переходы Activity/LockTimer используют conditional UPDATE/rowcount и idempotency keys.
- LockTimer имеет отдельные domain/services/repositories и явные state machines.
- Raw LLM response управляется флагом и TTL purge; usage хранится отдельно.
- BYOK ключи шифруются отдельным credentials key.
- Параметры LLM проходят allowlist и typed DSL validation.

### Архитектурные рекомендации

1. Закрепить единый шаблон `router → application service → repository` и transaction ownership.
2. Ввести typed DTO для action endpoints и единый error envelope/error codes.
3. Выделить policy registry для media ownership, social projection и domain grants.
4. Добавить correlation/request ID, structured logs и latency/error metrics для DB/LLM/jobs.
5. Для multi-instance deployment отделить scheduler/polling от web process: сейчас каждый Uvicorn
   worker/replica потенциально запускает собственный background scheduler.
6. Добавить concurrency tests на weekly generation, active-session uniqueness и media finalize.

## 5. Качество кода

### Положительное

- Ruff с широким набором правил проходит без ошибок; формат единообразен.
- Типы и docstrings широко используются; доменные enums вынесены из строковой логики.
- Существуют явные adapters/facades для совместимости после декомпозиции.
- Тесты организованы по фичам и содержат cross-user/concurrency/privacy сценарии.
- Нет обнаруженного `eval` в прикладном Python-коде; DSL типизирован.

### Что улучшать

- Добавить mypy/pyright хотя бы для services/models/schemas; Ruff не проверяет типовые контракты.
- Ввести complexity/boundary checks: запрет `db.commit()` в routers, лимит цикломатической
  сложности, architecture tests на запрещённые cross-domain imports.
- Добавить coverage report и gate сначала на критические модули, а не механические 100% всего.
- Заменить широкие `except Exception`/молчаливые `pass` на ожидаемые исключения и observable logs.
- Устранить повторяющиеся serializers/query-context builders.
- Синхронизировать supported Python: проект требует 3.11+, локальный аудит шёл на 3.13.5,
  production image — 3.11. Нужна CI matrix хотя бы 3.11 + актуальная поддерживаемая версия.

## 6. Frontend, UX и accessibility

### Сильные стороны

- SSR + HTMX соответствует выбранному стеку и не тащит тяжёлый SPA runtime.
- Assets self-hosted; Inter включён локально.
- Есть skip link, focus-visible, reduced-motion, live region, touch target baseline.
- Реализованы RU/EN, light/dark и mobile bottom navigation.
- Основной JS вынесен в page modules; есть общий CSRF wrapper и timezone rendering.
- Jinja autoescape и `tojson` применяются в основных data bridges.

### Проблемы и рекомендации

1. **Theme token bug:** `<html>` получает `class="dark|light"`, но semantic variables объявлены
   через `html[data-theme="dark"]`. Тёмный набор variables не активируется. Использовать один
   механизм (`class` или `data-theme`) и покрыть browser test.
2. **Визуальная неоднородность:** продолжают сосуществовать `slate` и `gray`, semantic tokens и
   прямые Tailwind colors, emoji и SVG, solid и gradients, `animate-fade-in` и новые motion rules.
   Нужен один component/token layer.
3. **Runtime Tailwind:** `/static/tailwindcss.js` компилирует стили в браузере. Для production
   собирать минимальный CSS при build; это улучшит startup, CSP и предсказуемость классов.
4. **Inline behavior:** многочисленные `onclick`/`onsubmit` и три крупных inline script block.
   Перенести в modules с `data-*` hooks и `addEventListener`.
5. **Charts:** найдено 10 `<canvas>` и ни одного с `role`/`aria-label`. Добавить текстовый summary,
   accessible table/fallback и осмысленные labels.
6. **Forms:** статически найдено 218 controls и только 54 `<label>`; часть labels может быть
   wrapping/aria-based, но нужен автоматический axe audit и ручная проверка accessible names.
7. **i18n:** остаются десятки fallback/hardcoded строк (`Lock Timer`, confirm/alert, footer,
   validation banners). Все пользовательские строки вынести в translation catalog, включая JS.
8. **Navigation/information architecture:** шесть и более первичных разделов плюс secondary
   modules создают высокую когнитивную нагрузку. ADR-033 разрешает их присутствие, но не требует
   одинакового визуального веса. Сгруппировать по сценариям «Сегодня / Практики / Прогресс /
   Инструменты» без изменения продуктового scope.
9. **Task-first dashboard:** основной CTA и active work должны визуально доминировать над charts,
   Telegram link, points и служебными карточками.
10. **Danger/safety UX:** safety stop должен оставаться всегда видимым, keyboard reachable и не
    зависеть от JS confirm. Подтверждение должно объяснять последствия без coercive wording.

## 7. Тесты, CI и эксплуатация

### Уже хорошо

- Unit/API/service/concurrency/cross-user/privacy/migration tests представлены.
- CI разделяет lint, tests, migrations и Docker build.
- Compose запускает `alembic upgrade head` перед приложением.
- DB и app имеют health checks; DB порт привязан к localhost.
- Runtime container работает не от root.

### Рекомендации

1. Добавить browser smoke/a11y matrix и production-compose smoke с реальным PostgreSQL.
2. Сделать memory lint warnings осмысленными, затем required; сейчас facts-check в CI допускает
   stale state через `|| echo`.
3. Добавить dependency/security scanning: Dependabot/Renovate, pip-audit, image scan, secret scan.
4. Пиновать base images по digest для воспроизводимых релизов; генерировать SBOM.
5. Добавить backup restore drill, а не только создание `pg_dump`.
6. Ограничить uploads на proxy, настроить timeouts/body size и malware/content processing policy.
7. Добавить application-level rate limits для auth, LLM и upload: встроенный Nginx — optional,
   поэтому его auth limit не является универсальной гарантией.
8. Перед горизонтальным масштабированием вынести Telegram polling, auto-analysis и Timer jobs в
   singleton worker/lease-based runner.

## 8. Рекомендуемый порядок работ

### Gate A — до любого расширения доступа

1. Закрыть публичную раздачу `/uploads` и проверить все существующие media URLs.
2. Сделать `CHALLENGE_HMAC_KEY` обязательным production secret; инвалидировать старые challenges.
3. Убрать LockTimer `innerHTML` и добавить XSS regression test.
4. Добавить минимальные security headers и скрыть readiness exception details.

### Gate B — стабилизация поведения

1. Усилить weekly planner: exact dates, completeness, uniqueness, atomic save.
2. Проверять ownership target при media finalize и LLM preference links.
3. Ввести browser smoke tests основных жизненных циклов.
4. Синхронизировать версию и исправить theme token selector.

### Gate C — качество и frontend

1. Собрать Tailwind CSS, удалить inline handlers/scripts, подготовить enforcing CSP.
2. Унифицировать tokens/components/i18n; провести axe + keyboard audit.
3. Декомпозировать крупные routers/templates по use cases.
4. Ввести type checking, targeted coverage gate и architecture tests.

### Gate D — публичная и горизонтальная эксплуатация

1. Rate/cost limits, email verification/recovery и session revocation.
2. Отдельный worker для background jobs и multi-instance concurrency tests.
3. Observability, dependency/image scans, SBOM и проверенное восстановление backup.

## 9. Финальный вывод

Проект не нуждается в переписывании. Его фундамент — модели, миграции, state machines,
owner-scoping, LLM validation и тестовая культура — пригоден для дальнейшего развития.
Рациональная стратегия: сначала закрыть два privacy/security blocker, затем укрепить проверку
LLM/media boundaries и browser coverage, после чего последовательно унифицировать frontend и
транзакционную архитектуру. Добавлять новые крупные функции до Gate A–B не рекомендуется.
