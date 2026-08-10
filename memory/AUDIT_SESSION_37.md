# Аудит PracticeLoop — Сессия 37

**Дата:** 2026-08-09.
**Объект:** `main`, после Сессий 1–36.
**Документы приоритета:** `REMEDIATION_SPEC.md` → `AGENTS.md` → `tracker-spec.md` → `memory/*`.
**Контекст:** владелец выбрал bif — REMEDIATION_SPEC.md остаётся целевой, ADR-029–034 — зафиксированный компромисс v0.8-actual (см. OPEN_QUESTIONS Q7).

---

## TL;DR

Проект перешёл из прототипа в **v0.8.0 production-ready** по большинству технических мер:
153 теста ✅, ruff 0 ✅, CI 3 job'а зелёные ✅, Docker smoke OK ✅, реальный деплой на VPS ✅.

Однако REMEDIATION_SPEC.md (высший приоритетный документ) выполнен **частично**:
6 архитектурных решений (ADR-029–034) оформлены как **явные отклонения от этого документа**.
Это — сознательный архитектурный bif, а не регрессия. Требует формальной фиксации в AGENTS.md.

---

## 1. Состояние по фазам (REMEDIATION_SPEC.md раздел 13)

| Этап | MEM статус | Код | Комментарий |
|---|---|---|---|
| **R0 контракт** | ✅ | ✅ | REM/AGENTS/DESIGN существуют; ADR-029–034 добавлены; ветки `fix/v0.7-stabilization` нет (вся работа в main) |
| **R1 воспроизводимость** | ✅ | ✅ | pyproject.toml — единственный источник; lock 102 pkg; CI 3 job'а |
| **R2 безопасность** | ⚠️ | ⚠️ | CSRF ✅; idempotency ✅; ownership ✅; **НО** secret defaults не gate в production |
| **R3 каталог/scheduler** | ⚠️ | ⚠️ | Roles ✅; unacceptable→strong_aversion ✅; soft scheduler ✅; **НО** Entity осталась единой (ADR-031) — противоречит разделам 5.2/5.3 SPEC |
| **R4 LLM planner** | ⚠️ | ⚠️ | full+abstract ✅; validator ✅; fallback ✅; **НО** raw_llm_response сохраняется безусловно; expires_at нет |
| **R5 frontend shell** | ⚠️ | ⚠️ | active_nav ✅; CSRF поля ✅; **НО** навигация не «Сегодня/Каталог/История/Ещё»; Training в главном меню |
| **R6 secondary** | ✅ | ✅ | Object-level auth применён, всё работает |

---

## 2. Зафиксированные ADR вразрез со спецификацией

Это **не баги** — это сознательный bif, оформленный в Сессии 19.

| # | Тема | SPEC требует | ADR принял | Состояние в коде |
|---|---|---|---|---|
| 1 | Модель данных | 8 таблиц: PracticeTemplate/Variant/UserPractice/Plan/PlanItem/ActivityEvent/ModerationEvent/LLMInvocation (**5.2**) | ADR-031: Entity остаётся единой | 1 таблица `entities` + `user_entity_opt_in`, `training_days`, `activity_logs` — без версионирования, без snapshot, без draft/published |
| 2 | Штрафы | Остановка атомарна; награда опциональна; отрицательные баллы **выключены по умолчанию** (**4.3**) | ADR-029: прерывание всегда со штрафом | `/tasks/{id}/interrupt` → `on_task_interrupted` → PenaltyRedemption + deduction |
| 3 | LLM debug payload | Постоянное хранение **выключено**; debug.payload шифруется; **expires_at**; очистка (**7.5**) | ADR-034: опционально (по умолчанию **включено**) | `ActivityLog.raw_llm_response: Text nullable` — пишется всегда в `pipeline.py:134,231`. Флаг `store_raw_response` в `LLMProviderConfig` отсутствует |
| 4 | Training | Заменяется «План дня»; верхняя вкладка **удаляется** (**12.3**) | ADR-032: Training — отдельная страница | `/training` в навигации; `TrainingDay`, `TrainingLogEntry`; фоновый авто-анализ |
| 5 | Onboarding secondary | Points/Inventory/Schedule/Telegram — только через «Ещё» + feature flags (**12.3**) | ADR-033: всё в главном меню | Telegram-карточка на дашборде; 6 пунктов навигации |
| 6 | Навигация | «Сегодня / Каталог / История / Ещё» (**12.1**) | ADR-033: фактический набор шире | Dashboard, tasks, training, catalog, points, admin |

**Действие:** добавить в AGENTS.md явное «актуальная сборка v0.8-actual отличается от целевой спецификации v0.7 по 6 пунктам (ADR-029–034). Принято владельцем в Сессии 19» — перенос в Сессию 38.

---

## 3. Регрессии и оставшиеся дефекты

### 3.1. Безопасность (P0)
- **secret defaults в `app/config.py`:** `jwt_secret_key = "change-me-to-a-random-secret-at-least-32-chars"`. Docker-compose жёстко валидирует через `${JWT_SECRET_KEY:?err}`, но `uvicorn app.main:app` без `.env` стартует с предсказуемым ключом. SPEC 9.1 требует «production завершается с понятной ошибкой при placeholder».
- **CSRF `secure=False`** в `security.py:38` — допустимо для dev, но нет автоматического переключения по `ENV=production` / `DEBUG=false`. Деплой на HTTPS → protection снижен.
- **innerHTML остался** в 6 файлах (ниже) — STATUS.md говорит «всё экранировано», но grep находит.

### 3.2. XSS / innerHTML (P0 для публичного использования)
Найдены `el.innerHTML = ...`:

```
app/templates/inventory.html:62       ← проверить user-controlled
app/templates/schedule.html:55,57    ← проверить
app/templates/dashboard_v2.html:277  ← category-legend (Chart.js labels — возможно серверные)
app/templates/dashboard_v2.html:331  ← gauge-stats (серверный JSON)
app/templates/calendar.html:112      ← templates list
app/templates/calendar.html:117      ← ✅ escapeHtml() применён
app/templates/calendar.html:121      ← overrides list
app/templates/calendar.html:176      ← available list
app/templates/measurements.html:59   ← проверить
app/templates/points.html:101        ← thresholds (статичные числа — безопасно)
app/templates/points.html:115        ← txn-table
app/templates/points.html:135,136    ← redemption list
app/templates/points.html:162,166    ← profile list ✅ escapeHtml()
```

Рекомендация: добавить автотест по сценарию A14 из SPEC (XSS-fixture).

### 3.3. Целостность LLM (P1)
- **validator.py: 37 строк** — проверяет только entity_id и тип params. **Не проверяет:** variant_id, compatibility, calendars/availability/rest, диапазон difficulty, `automation_allowed`, `risk_level`, отсутствие дубликатов.
- **`generate_daily_plan`** (pipeline.py:180+) принимает от LLM **произвольные `subtasks`** — LLM может «придумывать новые подзадачи», нарушение 7.1 SPEC. ADR-029–034 не покрывают этот риск.
- **Поле `risk_level`** не реализовано в `Entity`. SPEC раздел 5.2 вводит enum (`not_assessed`, `low`, `elevated`, `high`) — в коде отсутствует, gate невозможен.

### 3.4. Производительность (P2)
- **Telegram `setup_webhook`** в lifespan — если URL localhost без TLS, бот молча не работает; нет валидации handshake против `TG_WEBHOOK_SECRET`.
- **Auto-analysis scheduler** (`app/training/scheduler.py`) — tick каждые 60 сек; нет advisory lock; если один запуск задержался — может стартовать второй. test_scheduler покрывает только unit.

### 3.5. Quality (P2)
- **`app/llm/pipeline.py:332`** — одна функция делает 3 разные вещи (generate_task, generate_daily_plan, analyze_training_day). `generate_daily_plan` имеет **отдельную ветку repair без retry-loop** — отличие от `generate_task` (3 попытки). Рассогласование может привести к разному поведению.
- **`gamification_config`** в `ent` — JSON-блоб, схемы нет; чтение через `.get(...)` без типизации. SPEC явно запрещает `eval` и требует типизированный DSL.

---

## 4. Документация и процесс

| Что | Состояние |
|---|---|
| Версия в `pyproject.toml` | 0.8.0 ✅ |
| Версия в `app/main.py` | 0.8.0 ✅ |
| README.md | полный, 304 строки ✅ |
| DESIGN.md | 694 строки, актуальный ✅ |
| AGENTS.md | актуальный, **НО** не отражает bif SPEC↔ADR |
| REMEDIATION_SPEC.md | верхний приоритет заявлен, **НО** сознательно обходится в 6 пунктах |
| memory/* | Все 7 файлов ведутся дисциплинированно ✅ (STATUS, SESSIONS, DECISIONS, CHANGELOG, CONTEXT, OPEN_QUESTIONS, README) |
| Тесты | 153 ✅ |
| CI | 3 job'а зелёные ✅ |
| Docker smoke | OK (Сессия 34) |
| Деплой | На VPS OK (Сессии 35–36) |

**Сильная сторона:** процесс памяти работает.  
**Слабая сторона:** Definition of Done (REM 15) требует одновременного соответствия спеке — этого нет.

---

## 5. Что в коде хорошо

- 153 теста ✅
- CI 3 job'а ✅
- Docker smoke OK ✅
- Idempotency ✅
- Cross-user auth: 22 теста ✅
- CDN → локальные статики ✅ (htmx 2.0.10, Chart.js 4.5.1, TailwindCSS 4.3.3)
- Repair type guard ✅ (Session 32 fix)
- Alembic clean: 15 миграций, downgrade→upgrade OK
- DESIGN.md compliance: палитра, spacing, semantic tokens

---

## 6. Рекомендации (по убыванию приоритета)

### 🔴 P0 — до публичного использования
1. **Зафиксировать bif SPEC↔ADR в AGENTS.md** (явный комментарий: «актуальная сборка v0.8-actual отличается от целевой спецификации v0.7»). Владелец подтвердил подход bif в Сессии 37.
2. **Production gate для секретов:** pydantic validator или class-level validator в `config.py` — запрет `change-me-...` при `ENV=production`.
3. **Перепроверить `innerHTML`** в 6 файлах; добавить XSS-fixture тест (SPEC A14).

### 🟡 P1 — стабилизация
4. **Feature flags** для Training/Calendar/Telegram, чтобы можно было скрыть per-user.
5. **`store_raw_response`** флаг в `LLMProviderConfig`; debug.payload с отдельным шифрованием и TTL (REM 7.5).
6. **LLM validator** — добавить проверки variant_id, compatibility, risk/difficulty gate (REM 7.4).
7. **generate_daily_plan** — убрать свободное добавление subtasks (REM 7.1).
8. **`risk_level` enum** на `Entity` + gate в scheduler.

### 🟢 P2 — поддерживаемость
9. Pydantic DTO для LLM (Request/Response opaque-id).
10. `gamification_config` → typed DSL.
11. E2E тесты на 360/768/1280 px (SPEC 14: A01-A20).
12. Scheduler advisory lock.

---

## 7. Методология аудита

- Прочитаны REMEDIATION_SPEC.md (676 строк), AGENTS.md (219), tracker-spec.md (409), DESIGN.md (694), README.md (304).
- Прочитаны все 7 memory/* файлов.
- Проверен `git status` — clean, working tree совпадает с памятью.
- Прочитаны исходники: `app/main.py`, `app/security.py`, `app/models/entity.py`, `app/api/tasks.py`, `app/llm/pipeline.py`, `app/llm/validator.py`, `app/services/scheduler.py`, `app/config.py`.
- `rg 'create_all|metadata.create'` — пусто в коде (только комментарий в миграции 14).
- `rg 'innerHTML'` — 18 совпадений в 8 файлах.
- `rg 'eval('` — только исходник htmx.min.js (не ваш код).
- `python3 -m pytest --collect-only` → 153 теста собрано.
- CI конфиг прочитан: 3 job'а (lint, test, migrations roundtrip).
- docker-compose.yml прочитан: pg_isready wait, profiles nginx, env vars.
