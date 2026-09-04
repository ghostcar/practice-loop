# K-MEDICATION-SUBSTANCES-SPEC — «Активный элемент», состав и суточные пределы

> Статус: **дизайн зафиксирован (ADR-190)**, реализация фазами E–G.
> Модуль: Medication Organizer (§22 FUNCTIONAL.md, ADR-084/189/190). Relief-only (PD-013).

## 1. Проблема (факты)

1. Одно поле «МНН / Действующее вещество» смешивает МНН и действующее вещество; карточка
   подписывает это же поле «МНН».
2. Модель однокомпонентная. Нужны многосоставные препараты: **Фемостон 2/10** (активные
   компоненты эстрадиол + дидрогестерон; в пачке таблетки двух видов — с разными дозировками),
   витаминно-минеральные комплексы (десяток компонентов).
3. Группировки/поиска/замены по действующему веществу нет; остатки учитываются только по
   конкретному препарату.
4. Нет суточных пределов веществ (нормы) и явного разрешения превышения.
5. Автопоиск по наименованию (`autofill-info`) почти не работает: seed мал, «LLM» — мок.

## 2. Термины

| Термин | Значение | Пример |
|---|---|---|
| Торговое наименование | `medications.name` | «Фемостон 2/10» |
| **Активный элемент (действующее вещество)** | `med_substances` | «Эстрадиол», «Дидрогестерон» |
| **МНН / INN** | `med_substances.inn` (справочно) | «Estradiolum» |
| **Компонент** | `med_components` (med ↔ substance + amount/unit) | Эстрадиол 2 мг |
| **Вариант пачки** | `med_variants` (таблетки разного состава) | «белые 1–14», «серые 15–28» |
| **Суточный предел** | `med_substances.daily_max_*` | вит. D: 100 мкг/сут |
| Полный аналог | тот же набор компонентов + та же форма | Нурофен 500 ↔ Ибупрофен 500 |

## 3. Модель данных (миграция 097)

### 3.1. `med_substances` — справочник активных элементов

| Поле | Тип | Смысл |
|---|---|---|
| `id` | UUID PK | |
| `name` | VARCHAR(200) | каноническое отображаемое имя («Ибупрофен», «Эстрадиол») |
| `norm_key` | VARCHAR(200) UNIQUE | нормализованный ключ (`normalize_substance`) |
| `inn` | VARCHAR(200) NULL | МНН (международное непатентованное), справочно |
| `synonyms` | JSON NULL | варианты написания для поиска |
| `daily_max_amt` | NUMERIC NULL | суточный предел (число) |
| `daily_max_unit` | VARCHAR(10) NULL | единица предела: мкг / мг / г / МЕ / мл |
| `daily_max_note` | VARCHAR(300) NULL | источник/комментарий («взрослым ≤100 мкг/сут, ВОЗ») |
| `is_custom` | BOOL | false = seed (LOCAL_PHARMA_SEED), true = создано пользователем |
| `created_at`/`updated_at` | | |

`norm_key`: trim → lower → ё→е → схлопывание пробелов → удаление знаков препинания.
Соль/эфир — отдельная строка; синонимы — массив (seed/ручные), поиск учитывает `name+inn+synonyms`.

Seed: системные строки из `pharma_enricher.LOCAL_PHARMA_SEED` (извлекаются `active_ingredient`,
у записей с `inn` — МНН). Пользовательские: find-or-create при сохранении препарата.

### 3.2. `med_variants` — таблетки внутри пачки

| Поле | Тип | Смысл |
|---|---|---|
| `id` | UUID PK | |
| `medication_id` | UUID FK `medications` CASCADE, index | |
| `name` | VARCHAR(100) | «белые 1–14» / «2/10 (серые)» |
| `count_per_pack` | INT NULL | сколько таких таблеток в пачке |
| `sort_order` | INT | |
| `created_at`/`updated_at` | | |

Для обычных препаратов (одна таблетка/единица) вариантов нет: `med_components.variant_id = NULL`.

### 3.3. `med_components` — состав препарата (many-to-many + дозировка)

| Поле | Тип | Смысл |
|---|---|---|
| `id` | UUID PK | |
| `medication_id` | UUID FK `medications` CASCADE, index | |
| `variant_id` | UUID FK `med_variants` (CASCADE) NULL | NULL = состав единицы без вариантов |
| `substance_id` | UUID FK `med_substances` (RESTRICT), index | |
| `amount` | NUMERIC NULL | количество на единицу (таблетку/дозу) |
| `unit` | VARCHAR(20) NULL | мг / мкг / г / МЕ / мл |
| `sort_order` | INT | |
| `created_at`/`updated_at` | | |

Ограничение: в одном препарате/варианте вещество встречается один раз
(`UNIQUE (medication_id, variant_id, substance_id)` — с учётом NULL через partial unique на PG;
в модели — составной индекс + проверка в сервисе).

**Фемостон 2/10** (пример):
- variant «белые 1–14»: эстрадиол 2 мг;
- variant «серые 15–28»: эстрадиол 2 мг + дидрогестерон 10 мг.
Расписание приёма — на препарат; выбор варианта дня — фаза G (схемы пачек).

### 3.4. `medications` (дополнение)

| Поле | Тип | Смысл |
|---|---|---|
| `allow_ul_override` | BOOL default false | явное разрешение превышать суточный предел компонентов этого препарата |

`active_ingredient` остаётся legacy-текстом; новые препараты хранят состав в `med_components`
(display-подпись формируется из компонентов).

### 3.5. `med_intakes` (фаза F)

`substituted_for_id` (FK medications NULL): приём выполнен заменителем; `medication_id` —
фактический препарат, `quantity_taken` — фактическая доза, `notes` — автотекст замены.

## 4. Backfill (в миграции 097)

Для каждой существующей `medications.active_ingredient` (непустой): find-or-create вещества,
один `med_components` без варианта с amount=NULL (силовая строка не выводится автоматически —
заполняется пользователем при редактировании). Duplicate-безопасно (повторный запуск: если
компоненты уже есть — не трогаем).

## 5. Группировка, поиск, форма (фаза E)

- **Форма препарата**:
  - «Торговое наименование» + автопоиск (см. §7);
  - блок «Состав (действующие вещества)»: строки «вещество + доза + единица (+ вариант)»,
    кнопка «+ компонент»; подсказки веществ (datalist из `med_substances`);
  - чекбокс «Разрешено превышение суточной дозы» (allow_ul_override);
  - legacy-поля (kind/form/strength/manufacturer/…) остаются.
- **Карточка препарата**: «Состав: Эстрадиол 2 мг · Дидрогестерон 10 мг» (варианты — мелким
  текстом), при отсутствии компонентов — legacy `active_ingredient`.
- **Группировка «По действующему веществу»**: для веществ, встречающихся в препаратах
  пользователя, — карточка вещества: название (и МНН), список препаратов (торговое имя,
  форма, дозировки), суммарный остаток по аптечкам. Секция на странице `medications`.
- **Поиск**: поле фильтрует карточки по `name`, именам компонентов, `inn`, синонимам.
- i18n EN/RU.

## 6. Замена при нехватке (фаза F)

Проверка достаточности на «сегодня» (как в ADR-189): `needed_units = pending × dose_quantity`
против `Σ med_stocks.quantity` препарата. Если не хватает — кандидаты:

| Условие | Поведение |
|---|---|
| тот же набор компонентов (по norm_key, amount пересчитывается в мг) и та же форма | **автовыбор** с пересчётом количества (1×500 вместо 2×250) |
| тот же набор, дозировки не парсятся | автовыбор при равенстве строк `strength`, иначе предложение |
| неполное совпадение (поливитамины и т.п.) / другая форма | **предложение** (показ препарата, аптечки, остатка, состава) |

Автовыбор детерминирован; факт фиксируется (`substituted_for_id`), расписание закрывается как
выполненное. Точки: «На сегодня», открытие препарата (блок «Эквиваленты»), JSON parity
(`GET /api/v2/medications/{id}/equivalents`, `POST …/intake` с `substituted_for_id`).

## 7. Автопоиск по наименованию (фаза E; чиню «не срабатывает»)

`POST /medications/autofill-info` (страница) и JSON-вариант → `pharma_enricher`:

1. **Seed**: точное/подстрочное совпадение по нормализованному имени (включая «по маске»:
   «Фемостон 2/10» → компоненты/варианты по маске `femoston|фемостон N/M`); ответ содержит
   все поля формы + `components[]` (name, inn, amount, unit, variant).
2. **LLM** (BYOK, если конфиг активен): `call_llm` (json_mode) — запрос составить JSON
   {kind, form, strength, manufacturer, storage_conditions, prescription_required,
   instructions, components:[{name, amount, unit, variant}]}; `json_repair` при повреждении.
3. **Fallback**: честный ответ «не найдено» (message), без мусорных значений.
4. UI: результат заполняет форму (включая строки компонентов) с пометкой «проверьте данные»;
   сохраняется только по подтверждению пользователя.

## 8. Суточные пределы: сверка и разрешение превышения (фаза G; модель в E)

- Хранение: `med_substances.daily_max_amt/unit/note`.
- Сверка при построении дня: сумма по компонентам (amount × дозы на день, с учётом вариантов
  пачки, единицы приводятся к общим: мкг↔мг, МЕ — по веществу) vs `daily_max`.
- Превышение: предупреждение в UI «превышен суточный предел: …»; кнопка «Принять с
  превышением» — если `medication.allow_ul_override` (явное разрешение) или разовое
  подтверждение; отметка в `med_intakes.notes`/поле.
- Автогруппировка: вещества с превышением собираются в блок «Контроль суточной дозы».

## 9. Миграция 097 (план)

```
CREATE TABLE med_substances (id UUID PK, name VARCHAR(200) NOT NULL, norm_key VARCHAR(200) NOT NULL UNIQUE,
  inn VARCHAR(200), synonyms JSON, daily_max_amt NUMERIC, daily_max_unit VARCHAR(10),
  daily_max_note VARCHAR(300), is_custom BOOL DEFAULT false, created_at/updated_at timestamptz);
CREATE TABLE med_variants (id UUID PK, medication_id UUID FK CASCADE, name VARCHAR(100),
  count_per_pack INT, sort_order INT DEFAULT 0, created_at/updated_at);
CREATE TABLE med_components (id UUID PK, medication_id UUID FK CASCADE,
  variant_id UUID FK med_variants CASCADE NULL, substance_id UUID FK med_substances RESTRICT,
  amount NUMERIC, unit VARCHAR(20), sort_order INT DEFAULT 0, created_at/updated_at);
ALTER TABLE medications ADD COLUMN allow_ul_override BOOL DEFAULT false;
-- индексы: med_variants.medication_id, med_components.medication_id/substance_id
-- backfill веществ и компонентов из legacy active_ingredient
```

Downgrade зеркально.

## 10. Фазы (статус)

| Фаза | Содержание | Статус |
|---|---|---|
| **E — Сущность/состав/автопоиск/группировка** | миграция 097, модели, сервис нормализации и синхронизации компонентов, `pharma_enricher` (seed+маска Фемостон+LLM), форма с составом, карточка, группировка «по веществу», поиск, i18n, тесты | ⬜ впереди |
| **F — Замена** | автовыбор по составу+форме (пересчёт мг), «Эквиваленты», `substituted_for_id`, JSON parity | ⬜ впереди |
| **G — Пределы и схемы пачек** | сверка суточных доз (предупреждение/разрешение), учёт вариантов в дне, курсы/напоминания | ⬜ впереди |

Каждая фаза: ruff, таргетные pytest, single alembic head, i18n parity, деплой по команде.
