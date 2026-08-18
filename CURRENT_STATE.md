# Practice Loop — текущее состояние и ближайшие gates

> Снимок на: 18 августа 2026 года.
> Репозиторий: `ghostcar/practice-loop`.
> Это фактический документ; продуктовая цель описана в `PRODUCT_VISION.md`, порядок — в
> `ROADMAP.md`, текущая рабочая очередь — в `PLAN.md`.

## 1. Резюме

Practice Loop — работающий Personal-first веб-продукт: Activity Tracker, Today projection,
Lock Timer, Personal Suite, Mobile Foundation, Telegram, LLM/BYOK и закрытая Social Platform.
Social S0–S7 присутствует в коде, но не открыт внешним пользователям. Полноценного
кроссплатформенного мобильного клиента, D/s delegation и Community пока нет.

Исходное дерево находится на единственной Alembic head **058 (`a9b0c1d2e3f4`)**. Последний
полный воспроизводимый baseline на Python 3.11: **1132 passed, 1 skipped, 4 warnings**, Ruff check
и format-check зелёные. Проверка PostgreSQL 15 отдельно подтвердила миграции
`base → 057 → 058 → 057 → 058`, конкурентную идемпотентность consent и CRUD/cascade новых
Personal-таблиц.

Запущенный здесь production-like compose обновлён и здоров: образ содержит актуальный код, БД на
head **058**. Перед S5 создан backup, миграции 054–058 применены, общий prod-smoke, password E2E и
Chromium smoke/a11y/usability прошли успешно.

## 2. Проверенная исходная точка

| Параметр | Состояние |
|---|---|
| Ветка | `main` |
| Проверенный HEAD документации S3 | `1432ae4` (2026-08-18) |
| Версия приложения | `0.8.0` |
| Исходная Alembic head | `058_consent_policy_enforcement` (`a9b0c1d2e3f4`) |
| Полный pytest baseline | **1132 passed, 1 skipped, 4 warnings** (S2, Python 3.11) |
| Статические проверки | Ruff check + format-check ✅ |
| PostgreSQL integration | migration roundtrip + consent concurrency + Personal CRUD/cascade ✅ |
| Запущенный compose | health ✅; БД на 058; S5 smoke ✅ |

Счётчик тестов относится к проверенному S2-дереву; его нельзя автоматически переносить на
будущий HEAD без нового полного прогона.

## 3. Функциональная матрица

| Область | Фактический статус | Главный остаток |
|---|---|---|
| Auth, CSRF, privacy/export | ✅ работает | email verification/public hardening |
| Профиль/пароль | ✅ настройки и self-service смена пароля | полноценное admin-управление пользователями отсутствует |
| Activity Tracker + 11 статусов | ✅ работает | accepted-session freeze и UI аудита |
| Today projection | ✅ foundation работает | UX просроченного и единый главный CTA |
| Training, Diet, Calendar, Points | ✅ работает | дальнейшая унификация контрактов |
| Media Vault / attachments | ✅ foundation работает | storage abstraction, derivatives/retention polish |
| LLM/BYOK | ✅ работает | расширять use cases только через consent/policy gates |
| Durable consent | ✅ S1 | одно согласие на purpose+terms version; новые модули запрашиваются при включении |
| BYOK disclosure | ✅ S1 | пользователь сам подключает провайдера и отвечает за его выбор, ключ и условия |
| Lock Timer Core | ✅ C0–C9 | export/restore coverage и дальнейший subject polish |
| Device inventory / care | ✅ работает | расширение аналитики и UX обслуживания |
| Wear check-ins | ✅ реализовано, head 055 | production deploy S5 |
| Aftercare | ✅ реализовано, head 056 | production deploy S5 |
| Personal Telegram | ✅ работает | локализация части bot-текстов |
| Medication Organizer | ✅ работает | — |
| Health + Cycle | ✅ работает, relief-only | — |
| Sexual Journal | ✅ работает, Private Record | — |
| Personal Care + products/courses | ✅ работает, relief-only | — |
| Activity Catalog | ✅ работает | — |
| Personal Insights | ✅ работает | причинность не заявляется; opt-in разделов |
| Mobile Foundation | ✅ bearer/refresh, push registry, JSON/media contracts | расширить JSON-first покрытие |
| Mobile client | ❌ не реализован | выбор Flutter/React Native и отдельный этап |
| Social Platform S0–S7 | ✅ код, 🔒 закрыта | public rollout, rate limits, email verification |
| Chastity Social | ❌ не реализован | отдельное продуктовое решение |
| D/s delegation / Community | ❌ не реализованы | после Social/capability gates |

## 4. Consent и ответственность BYOK

- Согласие выдаётся один раз на конкретную цель и версию условий и действует всё время
  пользования порталом, пока пользователь явно его не отзовёт или не изменится версия условий.
- При первом входе запрашиваются согласия только для уже включённых профильных модулей. При
  последующем включении нового модуля в профиле портал отдельно запрашивает нужное ему согласие.
  Простое выключение функции не считается отзывом.
- История consent append-only; повторный grant идемпотентен, revoke немедленно закрывает
  чувствительное действие. Новая версия условий создаёт новую версию записи.
- Для BYOK интерфейс отдельно сообщает, что провайдера, endpoint, модель и ключ принёс сам
  пользователь. Пользователь отвечает за выбор провайдера, его ToS, тарифы и допустимость
  передаваемых данных; портал всё равно не обходит provider safety и применяет собственные gates.

## 5. Ближайшая последовательность

1. Закрыть остатки M1: accepted-session enforcement, UI истории переходов и Today polish.
2. Расширить export/restore и JSON-first покрытие новых Personal-модулей.
3. Решить объём account profile/admin user management (email, роли, reset/disable/audit).
4. Отдельно решить приоритет: mobile client или подготовка закрытого Social к limited rollout.

Future Research по автономным физическим устройствам описан в `ROADMAP.md` §12 и не является
разрешением на hardware-разработку или safety-critical управление.

## 6. Правило обновления

Факты меняются здесь и в `FUNCTIONAL.md`; порядок — в `ROADMAP.md`; рабочий gate — в `PLAN.md`.
Generated `docs/state/*` обновляются только через `python -m tools.memoryctl facts`. Замороженные
`memory/STATUS.md`, `memory/SESSIONS.md` и `memory/CHANGELOG.md` не дописываются.
