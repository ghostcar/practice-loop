---
schema_version: memory/v2alpha1
id: K-FUNCTIONAL-READINESS-2026-09-03
kind: knowledge
title: Функциональная готовность PracticeLoop на 2026-09-03
status: active
authority: derived
owners:
  - project-owner
scope:
  - platform
  - tracker/core
  - ui
source_refs:
  - path: tests/browser/portal.spec.ts
    relation: verifies
  - path: scripts/prod_smoke.sh
    relation: verifies
  - path: scripts/pre_deploy_check.sh
    relation: verifies
  - path: app/api/auth.py
    relation: implements
  - path: app/auth.py
    relation: implements
last_verified_at: 2026-09-03T00:00:00Z
last_verified_commit: bf3647ab442aef97dc0e4493a23741af3ca35372
review_on: source-change
---

# Функциональная готовность PracticeLoop на 2026-09-03

## Вердикт

Текущая сборка не готова к нормальной production-эксплуатации. Основная серверная логика имеет
широкое автоматизированное покрытие и работающий happy path сессии, но обязательные release-gates,
web-сессия, браузерный контур и внешние интеграции не дают зелёного эксплуатационного сигнала.

## Подтверждённые результаты

- Backend: 1464 passed, 2 failed, 3 skipped. Два падения проверяют удалённые legacy page routes,
  тогда как отдельные тесты clean routes подтверждают новые адреса; полный pytest всё равно красный.
- Ruff: 5 нарушений (импорты, E713 и длина строк); pre-deploy gate красный.
- Runtime: app/db healthy, readiness `ready`, Alembic на единственной head `093_portal_selection`;
  за просмотренный интервал в логах не найдено 5xx/Traceback.
- Browser smoke (Firefox): два последовательных прогона дали 2 passed / 1 failed. Создание и
  принятие activity session и экран body parts проходят; dashboard воспроизводит необработанную
  JS-ошибку. Accessibility-прогон завис до завершения первого сценария.
- Browser test inventory содержит legacy `/api/v2/*/page` URL и местами не проверяет HTTP status,
  поэтому способен проверять страницу ошибки вместо целевой страницы.
- Production smoke не проходит актуальный обязательный consent (скрипт отправляет legacy набор `module:<tracker/timer/medication/health/journal/care/catalog/insights/aftercare>`, тогда как в коде 2026-09-03 новый обязательный `module:social` отсутствует; скрипт также не удаляет создаваемого пользователя и не делает page HTTP codes фатальными, а второй ответ после consent setup разбирает JSON body как inventory вместо `id` из JSON).
- Web refresh cookie ограничена `Path=/auth`, поэтому не отправляется на обычные защищённые страницы.
  После удаления access cookie dashboard переводит на login вместо восстановления сессии. Logout
  не отзывает refresh token: сохранённый до logout token успешно получает новую пару токенов.
- Telegram не настроен, push provider выключен. Omniroute доступен на уровне TCP/HTTP, но
  `/v1/models` с настроенной авторизацией завершился timeout; реальный LLM happy path не подтверждён.
- В текущей локальной БД 282 пользователя и 486 LLM configs — тестовые browser/smoke регистрации
  не изолированы и не очищаются.
- Автоматизация off-site backup и подтверждённый restore drill в репозитории не обнаружены;
  RUNBOOK описывает ручные действия.

## Что уже работает

- Большой набор unit/integration проверок подтверждает ключевые статус-машины, owner scope,
  геймификацию, timer safety stop, мобильную token rotation и миграции.
- Основные контейнеры, схема БД, readiness и серверные логи выглядят стабильно.
- Браузерный happy path создания/принятия activity session проходит.

## Минимальные условия допуска

1. ~~Исправить web refresh/logout и покрыть browser-тестом истечение access token и отзыв refresh.~~
   **Готово 2026-09-03:** `POST /auth/logout` отзывает web refresh-токен (`api_tokens.revoked_at`),
   регресс-тест `test_logout_revokes_web_refresh_token` (23/23 в test_auth.py).
2. ~~Устранить dashboard JS error и получить стабильные smoke/a11y прогоны на поддерживаемых браузерах.~~
   **Готово 2026-09-03:** «JS error» на Firefox — это прерывание загрузки self-hosted шрифтов
   (NS_ERROR_NET_INTERRUPT 0x804b0002) при быстрой навигации смоука; файлы отдаются целыми
   (curl-проверка), классифицированы как benign в `tests/browser/helpers.ts`. Chromium+Firefox smoke — зелёные.
3. ~~Привести prod-smoke и browser smoke в соответствие с фактическим состоянием consent на 2026-09-03...~~
   **Готово 2026-09-03:** `module:social` в consent-наборе, fatal HTTP-коды, clean routes,
   cleanup через `POST /privacy/delete` с CSRF (303, юзер удалён из БД).
4. ~~Сделать pytest, ruff и полный pre-deploy gate зелёными.~~ **Готово:** pytest 1468 passed / 3 skipped,
   ruff check + format по `app/` чистые.
5. Частично готово 2026-09-03: реальный LLM request через `https://llm.gorbunovr.ru` подтверждён
   (chat completions 200 на `auto/*`); backup-скрипт `scripts/backup_prod.sh` + еженедельный restore drill
   `scripts/restore_drill.sh` установлены в cron, ручной прогон `DRILL_OK` (tables=145, users=156,
   alembic=093_portal_selection). Осталось: off-site назначение (`OFFSITE_DIR`), каналы уведомлений.
