# Practice Loop — карта документации

> Актуально на: 12 августа 2026 года.
> Назначение: не допускать смешения целевого продукта, фактического кода, планов и исторических
> спецификаций.

## 1. Источник истины зависит от вопроса

| Вопрос | Основной источник | Проверка/детализация |
|---|---|---|
| Что представляет собой продукт | `PRODUCT_VISION.md` | `PRODUCT_DECISIONS.md` |
| Что уже принято, отложено или исключено | `PRODUCT_DECISIONS.md` | `memory/DECISIONS.md` |
| Что реально реализовано сейчас | код, migrations и тесты текущего HEAD | `CURRENT_STATE.md`, `FUNCTIONAL.md` |
| Что делать следующим | `CURRENT_STATE.md` | `ROADMAP.md` |
| Каков долгосрочный порядок | `ROADMAP.md` | gates в соответствующих спецификациях |
| Как выглядит UI | `DESIGN_V2.md` | `DESIGN.md` как baseline v0.7, prototype и visual QA |
| Как агент должен работать | `AGENTS.md` | локальные инструкции и CI |
| Почему принято техническое решение | `memory/DECISIONS.md` | commit и session record |
| Что происходило по сессиям | `memory/SESSIONS.md`, `memory/CHANGELOG.md` | Git history |
| Какие вопросы открыты | `memory/OPEN_QUESTIONS.md` | `PRODUCT_DECISIONS.md` §5 |
| Как развернуть текущую версию | `README.md`, `DEPLOY_VPS.md`, `RUNBOOK.md` | Docker/CI evidence |

## 2. Роли документов

### Нормативные продуктовые

- `PRODUCT_DECISIONS.md` — принятые границы и статусы гипотез;
- `PRODUCT_VISION.md` — цельная пользовательская модель;
- `ROADMAP.md` — порядок развития и gates.

### Фактические

- `CURRENT_STATE.md` — датированный снимок HEAD, CI, реализации и ближайших блокеров;
- `FUNCTIONAL.md` — подробный inventory реализованного функционала;
- `PRODUCT.md` — короткий функциональный обзор для владельца;
- код, migrations, CI и тесты — окончательное доказательство факта.

### Инженерные

- `AGENTS.md` — правила работы с репозиторием и архитектурные ограничения;
- `DESIGN_V2.md` — актуальное визуальное направление «Тёмный архив» и frontend contract;
- `DESIGN.md` — baseline v0.7: safety, accessibility и progressive enhancement;
- `TARGET_ARCHITECTURE.md` — целевые bounded contexts, события, транспорты, rollout (создан, сессия 135);
- `DATA_LIFECYCLE.md` — классификация/retention/export/delete/derivatives (создан, закрывает PQ-006);
- `DEPLOY_VPS.md`, `RUNBOOK.md` — эксплуатация.

### Память

- `memory/DECISIONS.md` — legacy v1 **ACTIVE** (компилируется в `docs/adr/`);
- `memory/CONTEXT.md`, `memory/STATUS.md`, `memory/OPEN_QUESTIONS.md`, `memory/SESSIONS.md`,
  `memory/CHANGELOG.md` — legacy v1 **FROZEN** (M5, Сессия 120) — архив, не дописываются;
- `docs/memory-rfc/` — RFC Memory v2 (архитектура, schema, план M0–M6);
- `docs/adr/` — компилированные ADR (70, bidirectional с DECISIONS.md);
- `docs/wiki/`, `docs/questions/` — canonical знания и открытые вопросы (v2, L1);
- `docs/state/FACTS.json` + `docs/state/NOW.md` — generated facts текущего HEAD (v2, L2);
- `tools/memoryctl` — schema/lint/facts/adr/bootstrap/benchmark/sentinel/impact (v2).

### Исторические и входные материалы

- `tracker-spec.md` — исходная спецификация прототипа;
- `REMEDIATION_SPEC.md` — контракт стабилизации v0.7;
- `examples/LT/New_doc/` — исходный пак видения (перенесён в корень как нормативные документы);
- `examples/LT/` — LockTimer design input, не готовое задание без gap analysis.

## 3. Разрешение конфликтов

### Продуктовая цель

`PRODUCT_DECISIONS.md` → `PRODUCT_VISION.md` → `ROADMAP.md` → старые спецификации.

### Фактическое состояние

Код/миграция/реально выполненный тест → GitHub Actions evidence → `CURRENT_STATE.md` →
`FUNCTIONAL.md` → memory summary.

### Техническое решение

Новая ADR с явным `supersedes/refines` → более старая ADR → действующий engineering contract →
историческая спецификация.

### Safety и privacy

Более строгий запрет или более доступный safety stop имеет приоритет. Игровое последствие может
быть сохранено, но не блокирует emergency stop, удаление аккаунта, экспорт или отзыв доступа.

## 4. Известные superseded-положения

| Старое положение | Актуальное решение |
|---|---|
| Timer Core обязан быть семантически нейтральным | Честный Chastity Timer; нейтральность только для discretion (PD-017) |
| `tracker|timer|combined` — обязательная поставочная матрица | Один Personal-first продукт; `timer-only` требует отдельного решения |
| Timer — второй равноправный центр продукта | Chastity Timer — специализированный модуль Personal |
| Любая остановка трактуется одинаково | Обычный stopped и safety/emergency stop различаются; stop всегда технически доступен |
| Гостевой портал — естественное развитие Dynamics | В обозримом roadmap гостевого портала нет; внешний участник управляется вручную |
| Social включает управление отношениями | Social и D/s разведены: Social — проекции, D/s — grants |
| Мобильное приложение — отложенная гипотеза | Принято: кроссплатформенный клиент после портала (PD-018) |
| Масштабирование не упомянуто | Принято: обязательство по трём осям (PD-019) |

## 5. Когда обновлять

| Событие | Обновить обязательно |
|---|---|
| Принято или отменено продуктовое решение | `PRODUCT_DECISIONS.md`, `memory/DECISIONS.md` |
| Изменён пользовательский функционал | `FUNCTIONAL.md`, `CURRENT_STATE.md`, memory |
| Изменился приоритет или gate | `ROADMAP.md`, `CURRENT_STATE.md`, memory |
| Изменена архитектура | ADR, `TARGET_ARCHITECTURE.md`/`AGENTS.md`, memory |
| Изменён UI contract | `DESIGN.md`, visual acceptance evidence, memory |
| Новый release/deploy | README/runbook, `CURRENT_STATE.md`, memory |
| Только технический refactor | memory и ADR при необходимости; Vision не переписывается |

## 6. Правила для агента

1. Определить, задаёт запрос продукт, факт, план, UI или архитектуру.
2. Прочитать основной источник из таблицы §1 и обязательные memory-файлы.
3. Проверить HEAD и CI до утверждений о готовности.
4. Не переносить статус из плана в фактический inventory.
5. Не превращать предложение из переписки в принятое решение.
6. При конфликте сформулировать его явно и записать ADR.
7. После изменения обновить минимальный набор документов из §5.

## 7. Следующие документы

| Документ | Когда создавать |
|---|---|
| ~~`TARGET_ARCHITECTURE.md`~~ | ✅ создан (сессия 135, шаг 11a) |
| ~~`DATA_LIFECYCLE.md`~~ | ✅ создан (сессия 135, закрывает PQ-006) |
| `DOMAIN_GLOSSARY.md` | перед стабилизацией честного UI Timer |
