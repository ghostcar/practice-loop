# Adult activity data pipeline

Эта директория пока содержит только proposal-данные. Ни один файл не является разрешением на
запись в production.

## Слои

1. `adult_activity_source_inventory.v1.json` — полный реестр 163 идей из исходного чата.
   Записи не удаляются и не считаются готовыми карточками.
2. `adult_activity_editorial_candidates.v1.json` — производные краткие карточки для редакторского
   review. Каждая ссылается на один или несколько `source_id`.
3. `adult_activity_foundation.v1.json` — наиболее полный proposal исполняемого контракта для
   consent/check-in/aftercare foundation.
4. `adult_activity_fluid_toilet_review.v1.json` — поштучное редакторское решение для 42 идей
   fluid/enema/toilet без удаления исходников и без исполняемых медицинских параметров.
5. `adult_activity_breath_review.v1.json` — полный research review 20 breath-related идей. Все
   записи сохранены, автоматизация выключена, исполняемые инструкции и таймеры отсутствуют.
6. `adult_activity_sexual_technique_review.v1.json` — formal review всех 20 sexual-technique
   источников; manual selection и отдельный opt-in обязательны, promoted sources связаны с
   производными editorial candidates.
7. `adult_activity_wearing_chastity_review.v1.json` — formal review 20 wearing/chastity идей;
   независимое снятие, emergency exit, duration cap и проверки состояния обязательны.
8. `adult_activity_restraint_bondage_review.v1.json` — formal review 20 restraint/bondage идей;
   quick release, независимое освобождение, нейтральная поза и проверки обязательны.
9. `adult_activity_sensory_review.v1.json`, `adult_activity_impact_review.v1.json` и
   `adult_activity_standalone_review.v1.json` закрывают оставшиеся 41 source record.
10. `adult_inventory_source.v1.json` — allowlisted inventory extraction из chat/DOCX/XLSX без
    исторических дат, цен, количеств, штрафов и фактических сессий.
11. `adult_category_taxonomy_source.v1.json` — 13 source-категорий и две обязательные platform
    extensions для consent и aftercare.
12. `adult_additional_activity_titles.v1.json` — 289 title rows из concrete chat tables,
    `Задачи.xlsx` и иерархии `Книга1.xlsx`; semantic dedupe ещё не выполнен.
13. `adult_parameter_vocabulary.v1.json` и `adult_body_zone_vocabulary.v1.json` — ADR-041/043
    overlays без legacy defaults: 27 parameter definitions и фактические 39 existing + 9 proposed zones.
14. `adult_scenario_source.v1.json` — названия сценариев, фазы и связи с reviewed cards; исходные шаги
    не переносятся (`steps_imported=false`).
15. `adult_progression_source.v1.json` — только структура уровней/циклов из `Книга1.xlsx`; баллы,
    штрафы, описания и автоматическая эскалация не переносятся.
16. `adult_timer_source.v1.json` — типы таймеров с инвариантом `emergency_stop_always_available=true`;
    запрет выключения из источника не переносится.
17. `adult_evidence_source.v1.json` — типы обратной связи (текст/фото/видео/голос/таймер/чек-поинты)
    с инвариантом `media_required=false`; медиа никогда не обязательно.

## Значение статусов источника

- `candidate` — можно готовить производную карточку.
- `manual_only` — пользователь может выбрать отредактированную карточку вручную; планировщик и
  LLM не назначают её автоматически.
- `needs_safe_rewrite` — идея сохранена, но требует новых hard caps, stop/check-in и описания.
- `research_only` — идея сохранена для отдельной проработки; исходная запись не является
  пользовательской инструкцией или исполняемой карточкой.

Ни один из этих статусов не удаляет запись. Переход в пользовательский справочник выполняется
созданием производной карточки с provenance, а не сменой смысла исходной строки.

## Dry-run importer

`tools/adult_catalog_import.py` проектирует foundation (7 reviewed) + editorial candidates (34)
в `entities` с типизированным `safety_contract` и `content_status=approved` (ADR-105).

```bash
python3 -m tools.adult_catalog_import                      # read-only dry-run (без БД)
python3 -m tools.adult_catalog_import --apply --yes \\
    --database-url postgresql+asyncpg://...                 # gated: откажет при import_allowed=false
```

Импорт-гейт: запись отказывает, пока **все** манифесты не выставят `import_allowed=true`.
Foundation и editorial candidates уже подняли гейт (`import_allowed=true`) и залиты в боевую БД
(41 сущность, `content_status=approved`); остальные source-файлы остаются `import_allowed=false`.
Idempotent по `slug`.

## Проверка

```bash
python3 -m tools.adult_catalog_manifest data/seed/adult_activity_source_inventory.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_activity_editorial_candidates.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_activity_foundation.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_activity_fluid_toilet_review.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_activity_breath_review.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_activity_sexual_technique_review.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_activity_wearing_chastity_review.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_activity_restraint_bondage_review.v1.json --preview
pytest -q tests/test_adult_catalog_manifest.py
python3 -m tools.adult_catalog_manifest data/seed/adult_inventory_source.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_category_taxonomy_source.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_additional_activity_titles.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_parameter_vocabulary.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_body_zone_vocabulary.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_scenario_source.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_progression_source.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_timer_source.v1.json --preview
python3 -m tools.adult_catalog_manifest data/seed/adult_evidence_source.v1.json --preview
```

Все команды read-only. Importer намеренно отсутствует.

## Semantic dedupe дополнительных названий

`adult_additional_activity_titles.v1.json` содержит аддитивный слой `semantic_groups`:
9 групп схлопывают RU/EN и перефразированные дубликаты (286 → 277 семантически уникальных
названий). Исходные 289 rows и 286 normalized titles не удаляются — группа хранит
`canonical_title_id` и `member_title_ids` с причиной слияния.

## Gate продвижения карточки

1. Проверить provenance и отсутствие механического переноса опасной инструкции.
2. Добавить RU/EN title и summary.
3. Указать adult-only, explicit opt-in и необходимость актуального session check-in.
4. Определить `risk_level` и отдельно `automation_allowed`.
5. Добавить типизированные параметры с units/min/max и без автоматической эскалации.
6. Добавить prerequisites, stop conditions, quick release, checkpoints и aftercare.
7. Запретить обязательное медиа-подтверждение и штраф за safety stop.
8. Прогнать lint/preview и выполнить ручной owner review.
9. Только после выбора физической схемы реализовать dry-run importer (`tools/adult_catalog_import.py`).
