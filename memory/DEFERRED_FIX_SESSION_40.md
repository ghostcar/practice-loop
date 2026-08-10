# Session 40 — Deferred-фиксы (2026-08-09)

**Дата:** 2026-08-09.
**Контекст:** Владелец одобрил «делай всё, обновляя память на каждом этапе» — закрыл deferred пункты из Session 37 (backend P0) и Session 39 (frontend deferred).

**Результат:** **225/225 тестов ✅**, ruff 0 ✅, format ✅, P0/P1 из всех аудитов закрыты.

---

## 1. Сводка изменений

| # | Тип | Файл(ы) | Что |
|---|---|---|---|
| 1 | **Backend P0** | `app/config.py` + миграция-не-нужна | **Production gate секретов** через `app_env` model_validator: `change-me-...` + длина <32 отвергаются при APP_ENV=production |
| 2 | **Process** | `AGENTS.md` | **Bif-комментарий v0.8-actual ↔ v0.7-spec**: таблица 6 пунктов расхождения с ADR-029–034 |
| 3 | **Backend P1** | `alembic/versions/016_add_store_raw_response.py` + `app/models/llm_config.py` + `app/models/activity_log.py` + `app/llm/pipeline.py` + 3 схемы | **store_raw_response flag + TTL** (REM §7.5): opt-in/opt-out дебага raw-ответа + DateTime expires_at = now + 30d |
| 4 | **Backend P1** | `app/llm/validator.py` + `app/llm/pipeline.py` | **Расширение LLM validator** (REM §7.4): `validate_params_against_schema(params, schema)` — типы, min/max, length, enum, optional |
| 5 | **Frontend P1** | `app/templates/dashboard_v2.html` | **DESIGN §11**: 4 графика → 2 канваса + 2 summary-карточки (categories top-3 + completion big-number) |
| 6 | **Frontend P2** | `app/templates/calendar.html` | **JS async i18n**: `I18N` dict + `POLICY_LABEL` map для Mon–Sun, Allowed/Passive/Blocked, Templates/Overrides, check-result |
| 7 | **Frontend P2** | `app/templates/inventory.html` | **JS async i18n**: `I18N` dict + `STATUS_LABEL` map для All/Clothing/Equipment/Cosmetics/Shopping List |
| 8 | **Frontend P1** | `app/api/import_data.py` + `app/templates/import_data.html` | **localhost:8443 → `{{ app_url }}`** (из `request.url_root`); 17 i18n ключей; эмодзи → SVG; градиент → solid |
| 9 | **Tests** | `tests/test_config.py` | 11 тестов production gate |
| 10 | **Tests** | `tests/test_llm_raw_response_policy.py` | 5 тестов REM §7.5 policy |
| 11 | **Tests** | `tests/test_llm_validator.py` | 32 теста REM §7.4 schema |
| 12 | **Tests** | `tests/test_xss_fixtures.py` | 24 теста REM §A14 (autoescape + escapeHtml + e2e + OWASP regression) |
| 13 | **i18n** | `app/i18n/{en,ru}.py` | +105 ключей (nav_*, dashboard_*, calendar_*, inventory_*, inv_*, import_*, telegram_*) |
| 14 | **Infra** | `docker-compose.yml` + `docker-compose.override.yml` | APP_ENV: production (default) / development (override) |

---

## 2. Файлы изменены (по категориям)

### Backend (8 файлов)
- `app/config.py` — добавлен `app_env`, `_PLACEHOLDER_*` константы, `field_validator`, `model_validator` для gate
- `app/llm/validator.py` — `validate_params_against_schema(params, schema)` + `_validate_one_param`, `_TYPE_VALIDATORS`
- `app/llm/pipeline.py` — импорт нового валидатора, подключение к цепочке, helper `_resolve_raw_response`
- `app/models/llm_config.py` — поле `store_raw_response`
- `app/models/activity_log.py` — поле `raw_response_expires_at`
- `app/schemas/llm_config.py` — `store_raw_response: bool = True` во всех 3 DTO
- `app/api/llm_configs.py` — форма принимает `store_raw_response`
- `app/api/import_data.py` — контекст с `app_url=request.url_root`

### Migrations (1 файл)
- `alembic/versions/016_add_store_raw_response.py` — новые поля + индекс expires_at

### Templates (5 файлов)
- `app/templates/dashboard_v2.html` — refactor: 2 канваса + 2 summary
- `app/templates/calendar.html` — все hardcoded EN → `t.calendar_*`, JS `I18N` dict
- `app/templates/inventory.html` — все hardcoded EN → `t.inventory_*`/`t.inv_*`, JS `STATUS_LABEL`
- `app/templates/import_data.html` — locale URL → `app_url`, эмодзи → SVG, градиент → solid
- `app/templates/llm_configs.html` — показывает store_raw_response + 🤖 → SVG

### i18n (2 файла)
- `app/i18n/en.py` — добавлено ~52 ключей, удалены 2 дубля
- `app/i18n/ru.py` — добавлено ~52 ключей, удалены 2 дубля

### Tests (4 файла новых + 0 старых правок)
- `tests/test_config.py` — новый, 11 тестов
- `tests/test_llm_raw_response_policy.py` — новый, 5 тестов
- `tests/test_llm_validator.py` — новый, 32 теста
- `tests/test_xss_fixtures.py` — новый, 24 теста

### Process (1 файл)
- `AGENTS.md` — новая секция 0 «Архитектурный bif»

### Infra (2 файла)
- `docker-compose.yml` — APP_ENV default production
- `docker-compose.override.yml` — APP_ENV=development для dev

---

## 3. Acceptance criteria (REM §15)

| Критерий | До S40 | После S40 |
|---|---|---|
| Документация и код в одном имени (v0.8.0) | ✅ | ✅ |
| Чистая установка, Docker build, CI jobs зелёные | ✅ | ✅ |
| Alembic — единственный способ создания схемы | ✅ | ✅ (migration 016 добавлена) |
| **Production gate для placeholder секретов** | ❌ | ✅ (Этап 3) |
| **innerHTML-аудит + XSS-fixture** | ⚠️ partial | ✅ (Этап 10) |
| **Расширение LLM validator** (REM §7.4) | ❌ только top-level | ✅ schema-validation |
| **store_raw_response flag** (REM §7.5) | ❌ хардкод «всегда хранить» | ✅ opt-in TTL 30d |
| **AGENTS.md bif comment** (REM ↔ ADR) | ❌ не отражено | ✅ секция 0 |
| **Навигация «Сегодня/Каталог/История/Ещё»** (DESIGN §12.1) | ⚠️ ADR-033 | ⚠️ остаётся как ADR (bif владельца) |
| **Dashboard ≤2 графика на viewport** (DESIGN §11) | ❌ 4 графика | ✅ 2 канваса + 2 summary |

---

## 4. Compliance метрики

| Метрика | До S40 | После S40 |
|---|---|---|
| ruff check | ✅ | ✅ |
| ruff format | ✅ | ✅ |
| Тестов | 153 | **225 (+72)** |
| Новых i18n ключей en.py | — | +~52 (net +50) |
| Новых i18n ключей ru.py | — | +~52 (net +50) |
| Хardcoded URL в шаблонах | 2 (localhost:8443) | **0** (всё → `app_url`) |
| P0/P1 блокеров из аудитов | 6 | **0 (всё закрыто в S39+S40)** |
| P2 deferred | many | 3 (Inter font, mobile bottom nav, JS modules) |

---

## 5. Code-review highlights

1. **Production gate (`config.py`)** — минимально invasive: 1 поле (`app_env`), 1 validator, env vars. Не трогает существующую логику.
2. **`store_raw_response`** — backwards-compat: default TRUE, существующие записи продолжают работать. TTL только для новых.
3. **Schema-validator** — НЕ non-exhaustive (не отвергает лишние ключи) — schemas расширяемы без слома версий.
4. **dashboard_v2 refactor** — сохранены все данные points/XP/streak/done + 2 графика вместо 4; categories/completion показаны как текст-карточки (тот же объём данных, меньше canvas).
5. **JS i18n в calendar/inventory** — все hardcoded literal-ы заменены Jinja-инжекцией в JS-пространстве. Server-controlled (безопасно: не user input).
6. **`app_url = str(request.url_root).rstrip("/")`** — единственная точка, никаких hardcoded URL в шаблонах.

---

## 6. Acceptance test fixtures (REM §A14)

| Слой | Тесты |
|---|---|
| Jinja autoescape | 2 (content, attribute) |
| escapeHtml (mirror base.html) | 8 (script/quote/mouseover/javasсript/unicode/None/int/double-escape) |
| End-to-end calendar/inventory | 4 |
| OWASP regression | 10 (svg/onload, iframe/src, body/onload, input/autofocus, ERB/Jinja/JS injections) |
| **Итого** | **24 теста XSS-защитных** |

---

## 7. Что не реализовано (deferred в следующие сессии)

1. **Inter font self-hosted** (DESIGN §7.1) — грузится с googleapis сейчас (через все равно статически в `tailwindcss.js`).
2. **Mobile bottom nav** (DESIGN §4.4) — текущий top-nav на маленьких экранах.
3. **JS-hoist в ES modules** (DESIGN §15.4) — сейчас inline `<script>` блоки.

Все три — **non-blocker**, не влияют на функциональность.

---

## 8. Соответствие ADR (биф v0.8-actual ↔ v0.7-spec)

В AGENTS.md секции 0 явно зафиксировано:

1. **ADR-031**: Entity остаётся единой (полная версия: 8 таблиц) — **actual**.
2. **ADR-029**: Прерывание со штрафом — **actual** (отрицательные баллы вкл).
3. **ADR-034**: `store_raw_response` flag — теперь **реализован** (флаг + TTL) — частичное соответствие REM §7.5.
4. **ADR-032**: Training отдельная страница — **actual** (ADR остаётся).
5. **ADR-033**: Навигация 6 пунктов — **actual** (ADR остаётся).
6. **ADR-033 (навигация)**: 6 пунктов вместо 4 «Сегодня/Каталог/История/Ещё» — **actual**.

Никаких изменений в архитектуре не произошло; только реализованы ранее декларированные флаги (ADR-034).

---

## 9. Сохранённые данные о сессии

- `memory/SESSIONS.md` — Сессия 40 с поэтапным changelog (12 этапов)
- `memory/STATUS.md` — секция «Сессия 40» с метриками
- `memory/CHANGELOG.md` — Сессия 40 с подробным списком правок
- `memory/OPEN_QUESTIONS.md` — Q9 (frontend) и Q10 (backend) обновлены
- Этот файл `DEFERRED_FIX_SESSION_40.md` — финальный отчёт

---

## 10. Следующая сессия (опциональные выходы)

1. Mobile bottom nav (DESIGN §4.4) — порт UX
2. Self-hosted Inter font (DESIGN §7.1) — порт Performance/CSP
3. JS modules extraction (DESIGN §15.4) — порт Maintainability
4. Risk_level enum на Entity (REM §5.2) — порт Safety gate
5. Typed gamification_config DSL — порт Type safety
