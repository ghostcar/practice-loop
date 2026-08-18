# P1 — сводный owner review всех source manifests

> Статус: подготовлен к review. Ни один manifest не разрешает запись в production.
> `import_allowed=false` во всех файлах; importer отсутствует. Production-каталог остаётся пустым
> до отдельного решения владельца после этого review.

## 1. Что находится под review

Все файлы — read-only proposal в `data/seed/`. Полный реестр исходных идей отделён от
исполняемого каталога: производные карточки создаются только с provenance, исходники не удаляются
и не переписываются «нейтральными» названиями.

| # | Manifest | Слой | Объём | Ключевой инвариант |
| --- | --- | --- | --- | --- |
| 1 | `adult_activity_foundation.v1.json` | 7 foundation cards (consent/aftercare) | 7 draft, all `low` | foundation без штрафов, медиа не требуется |
| 2 | `adult_activity_editorial_candidates.v1.json` | производные карточки | 34 cards | elevated/sexual_connection → `automation_allowed=false` |
| 3 | `adult_activity_source_inventory.v1.json` | полный реестр идей чата | 163 rows | все retained, `seed_ready=false` |
| 4 | 8 × `adult_activity_*_review.v1.json` | поштучные editorial review | 163/163 ровно по одному разу | automation выключена у всего review |
| 5 | `adult_inventory_source.v1.json` | справочный инвентарь | 186 rows → 135 items | без цен/дат/количеств/штрафов/сессий |
| 6 | `adult_category_taxonomy_source.v1.json` | таксономия | 13 категорий + 2 extensions | consent/aftercare — platform extensions |
| 7 | `adult_additional_activity_titles.v1.json` | доп. названия | 289 rows → 286 → 277 semantic | `seed_ready=false`, dedupe аддитивный |
| 8 | `adult_parameter_vocabulary.v1.json` | словарь параметров | 27 definitions | legacy defaults не импортируются |
| 9 | `adult_body_zone_vocabulary.v1.json` | словарь зон | 39 existing + 9 proposed | уязвимые зоны → `no_automation` |
| 10 | `adult_scenario_source.v1.json` | сценарии | 13 | `steps_imported=false`, шаги не переносятся |
| 11 | `adult_progression_source.v1.json` | прогрессия | 6 иерархий | `escalation_automation=false`, без баллов |
| 12 | `adult_timer_source.v1.json` | таймеры | 9 типов | `emergency_stop_always_available=true` |
| 13 | `adult_evidence_source.v1.json` | обратная связь | 7 типов | `media_required=false` |

Проверка: `python3 -m tools.adult_catalog_manifest <manifest> --preview` (все — `MANIFEST_OK`),
`pytest tests/test_adult_catalog_manifest.py` — 39 passed, ruff зелёный.

> Статус review: **выполнен** (сводный, 2026-08-18). Решения зафиксированы в §6 и ADR-105.

## 2. Foundation cards (слой 1) — приоритетный пакет

7 карточек согласия и восстановления, все `low`, `penalty_enabled=false`, медиа не требуется:

- `agree-session-boundaries` — согласовать границы сессии
- `choose-stop-signals` — выбрать сигналы остановки
- `pre-session-readiness-check` — проверка готовности перед сессией
- `mid-session-checkin` — промежуточная проверка состояния
- `prepare-aftercare-plan` — план заботы после сессии
- `post-session-debrief` — обсуждение сессии
- `later-wellbeing-check` — проверка состояния позднее

**Требует решения:** утвердить эти 7 как первый прод-пакет (после выбора схемы хранения), либо
скорректировать формулировки.

## 3. Editorial candidates (слой 2) — 34 карточки

Категории: consent_communication 9, connection_aftercare 5, sexual_connection 7,
sensory_play 3, restraint_bondage 2, impact_play 2, device_timer 2, control_protocol 3,
service_care 1. Риски: low 17 / elevated 17.

`automation_allowed=true` имеют только 6 low-risk карточек (проверка снаряжения, проверка зон,
снятие устройства, сенсорика blindfold/texture/vibration). Все `elevated`, все `sexual_connection`
и обе fluid/breath-проверки — `automation_allowed=false`.

**Требует решения:** подтвердить список из 6 карточек, допущенных к автоматизации, и в целом
разрешить перенос 34 candidates в прод-схему после выбора хранения.

## 4. Review-батчи (слой 4) — итог по областям

| Область | recs | promote | manual | rewrite | research |
| --- | --- | --- | --- | --- | --- |
| fluid/toilet | 42 | 12 | 17 | 7 | 6 |
| breath | 20 | 1 | 0 | 1 | 18 |
| sexual technique | 20 | 9 | 5 | 5 | 1 |
| wearing/chastity | 20 | 5 | 4 | 9 | 2 |
| restraint/bondage | 20 | 4 | 5 | 9 | 2 |
| sensory | 20 | 5 | 5 | 5 | 5 |
| impact | 20 | 6 | 5 | 4 | 5 |
| standalone | 1 | 0 | 0 | 1 | 0 |
| **Итого** | **163** | **42** | **41** | **41** | **39** |

Promoted-источники (42) уже связаны с производными editorial candidates через `derived_card_slug`.
Breath остаётся research-контуром (18/20), исполняемых инструкций нет.

## 5. Второй extraction pass (слои 5–13) — справочные данные

- **Inventory** (135 items): restraint_hardware 30, clothing_fetish 30, body_device 18,
  electronic_concept 18, consumable_material 15, sensory_equipment 8, other 14, care_supply 2.
  Routing: standard 51 / moderated 45 / specialist_review 21 / future_research 18.
- **Taxonomy** (13+2): 8 manual_only, 3 moderated, 1 research_only (breath), 1 scenario_review.
- **Titles**: 277 семантически уникальных (9 dedupe-групп), 11 research_only остальное — editorial_review.
- **Parameters** (27): 7 standard / 6 moderated / 4 manual_only / 4 specialist_review /
  4 required_safety / 2 privacy_review.
- **Body zones** (39+9): 26 standard / 16 specialist_review / 4 no_automation / 2 moderated.
  В `no_automation` входят neck/throat/eyes/nose.
- **Scenarios** (13): 11 research_only, 2 manual_only (checkpoint-based, aftercare-integrated).
- **Progression** (6): только структура, эскалация ручная.
- **Timers** (9): emergency stop всегда доступен.
- **Evidence** (7): текст/фото/видео/голос/таймер/чек-поинт/очередь — медиа никогда не обязательно.

## 6. Решения владельца (сводный review 2026-08-18)

1. ✅ **Foundation-пакет принят как есть** — 7 карточек переведены в `reviewed`,
   `review_required=false`.
2. ✅ **Хранение safety contract — JSONB** (ADR-105): типизированный `safety_contract` JSONB +
   `automation_allowed`/`adult_only`/`content_status`/`content_version` на `Entity`.
   Нормализация не выполняется, ADR-031 в силе.
3. ✅ **Automation выключен у всех 34 editorial candidates** (`automation_allowed=false`) до
   первого прод-прогона; lint теперь требует false для всех candidates.

Оставшийся gate: dry-run importer (backup → dry-run → import gate), затем production import
как отдельный шаг с отдельным подтверждением.

## 7. Что остаётся запрещённым независимо от review

- Автоматизация elevated/manual-only/research карточек.
- Штраф за stop/отказ/пропуск check-in/снижение сложности.
- Обязательное медиа-подтверждение; принудительный «запрет выключать» таймер.
- Автоматическая эскалация длительности/интенсивности/повторов.
- Перенос breath-инструкций, опасных объёмов/времён и персональных правил из DOCX.
