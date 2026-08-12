# Practice Loop — текущее состояние и план ближайших доработок

> Снимок на: 12 августа 2026 года.
> Репозиторий: `ghostcar/practice-loop`.
> Это фактический документ: целевая модель описана в `PRODUCT_VISION.md`.

## 1. Резюме

Practice Loop — крупный работающий прототип Personal-first продукта: Tracker (каталог, задачи,
сессии, тренировки, питание, геймификация, календарь, замеры, инвентарь, импорт/экспорт, медиа,
LLM, личный Telegram-бот), **LockTimer Core C0–C9** (предметное ядро Chastity Timer) и **Social
Platform S0–S7** (профили, отношения, публикации, верификация, модерация — не открыта публично).

**Основной факт:** `main` — зелёная поставочная точка: **592/592 тестов ✅, ruff ✅, Docker ✅,
миграции 001→035 ✅, деплой на VPS живой.**

Не реализованы: предметная обвязка Timer (device inventory, честный фронт), специализированные
Personal-журналы (Sexual Journal, Care, Medication, Cycle, Media Vault, Insights), открытие Social,
D/s, Community, мобильный клиент.

## 2. Git и проверенная исходная точка

| Параметр | Состояние |
|---|---|
| Ветка | `main` |
| HEAD | `f3079be` (2026-08-12) |
| Версия приложения | `0.8.0` |
| Последняя миграция | `035_add_template_sort_order.py` |
| Тесты | **592/592 ✅** |
| CI | GitHub Actions: lint/test/migrations/docker — зелёный |

## 3. Функциональная матрица

| Область | Статус | Главный остаток |
|---|---|---|
| Auth, роли, CSRF | ✅ готово | — |
| Приватный Activity Tracker | ✅ готово | — |
| Категории | ✅ backend + UI (S61) | — |
| ActivityTask v2 (11 статусов) | ✅ backend + UI | accepted-session freeze, UI аудита |
| Типизированные параметры (DSL) | ✅ готово | — |
| Сессии accepted | ⚠️ модель есть | фактический freeze snapshot + enforcement |
| Training | ✅ готово | согласовать с ActivityTask v2 |
| Diet/Nutrition | ✅ готово | объединённые Personal Insights |
| Геймификация | ✅ готово | семантика всех 11 статусов (частично) |
| Calendar/Schedule | ✅ готово | интеграция с Today и Chastity Timer |
| Measurements / Inventory | ✅ готово | — |
| Media/Attachments | ⚠️ частично | Media Vault, derivatives, retention |
| Import/Export | ✅ готово | новые модели, restore roundtrip |
| LLM BYOK | ✅ готово | унификация use cases |
| Personal Telegram | ✅ готово | Today, Chastity Timer, discretion |
| **LockTimer Core (C0–C9)** | ✅ ядро | **предметная обвязка**: device inventory, честный фронт (PD-017), Health override, TG-команды Timer |
| Верификация кодов | ✅ HMAC one-time | **OCR/LLM по фото — отложено** (Q13) |
| Sexual Journal | ❌ нет | продуктовый и технический design |
| Personal Care | ❌ концепт | специализированные процедуры |
| Medication/Health | ❌ нет | Medication Organizer, границы |
| Cycle | ❌ нет | модель факта/расчёта |
| Personal Insights | ❌ нет | общий opt-in анализ |
| Social Platform (S0–S7) | ✅ функции | **открытие публично** + Chastity Social (PQ-003) |
| Chastity Social | ❌ нет | публичные check-in, продления с caps |
| Manual Dominant Workspace | ❌ нет | — |
| Registered D/s | ❌ нет | — |
| Community | ❌ нет | после Trust & Safety |
| Mobile Foundation / клиент | ❌ нет | JSON-first (PD-020), bearer-auth, push (PD-018) |

## 4. Ближайший план доработок

### Шаг 1. Завершить M1 (Activity Tracker v2 + Today)

- accepted-session freeze и enforcement;
- UI-экран истории аудита;
- Today-достройка (просроченное, CTA, напоминания).

### Шаг 2. Предметная обвязка Chastity Timer (Этап 3)

- честная терминология фронта и уведомлений (PD-017) — i18n + шаблоны, без миграций;
- device inventory;
- Health override (только облегчение);
- Personal Telegram Timer-команды.

### Шаг 3. Мобильный фундамент (Этап 5A)

- JSON-first пилот: перевести timer start/safety-stop и ключевые действия на JSON-ответы (PD-020);
- bearer-auth слой;
- storage-абстракция (PD-019).

### Шаг 4. Рефакторинг и нормализация

- разбить крупные файлы (execution.py 1409, import_data.py 988, social/repositories.py 1032,
  references.py 817, social/api.py 957, pipeline.py 953);
- lint-нормализация; устранение дублей (list_templates уже объединён S80).

### Дальше

Social-открытие (PQ-003), Personal Suite, Mobile клиент, D/s, Community — `ROADMAP.md`.

## 5. Правило обновления

После каждого значимого commit или фазы обновляются: `FUNCTIONAL.md`, этот файл,
`memory/STATUS.md`/`SESSIONS.md`/`CHANGELOG.md`, ADR — при изменении решения, `ROADMAP.md` — при
изменении порядка или gate.
