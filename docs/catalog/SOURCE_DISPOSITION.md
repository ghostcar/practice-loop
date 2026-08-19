# Матрица разбора `examples/category-chat.md`

> Все 163 содержательных названия сохранены поштучно в
> `data/seed/adult_activity_source_inventory.v1.json`. Ни одна идея не удалена: ограниченный
> статус означает отдельную доработку и запрет автоматизации, а не потерю записи.

| Source lines | Исходная область | Нормализованная область | Решение по умолчанию | Причина / обработка |
| --- | --- | --- | --- | --- |
| 706–746 | Жидкости, удержание, клизмы | `body_control` | `manual_only` / `needs_safe_rewrite` / `research_only` | Медицинские и гигиенические риски; исходная идея сохраняется, безопасные производные выделяются отдельно |
| 765–809 | Туалетный контроль | `toilet_control` | `manual_only` / `needs_safe_rewrite` / `research_only` | Карточки сохраняются для ручного выбора и доработки, но не автоматизируются |
| 825–865 | Ограничение дыхания | `breath_restriction` | `research_only` | Идеи сохранены отдельно; starter seed и automation их не исполняют |
| 880–924 | Интимная техника | `sexual_connection` | `manual_only` | Только явный opt-in; исключить дыхательные сочетания, принудительную глубину и injury-oriented progression |
| 939–979 | Ношение/целомудрие | `device_timer` / `sensory_play` | `candidate` / `manual_only` / `needs_safe_rewrite` | Для исполняемой производной нужны hard caps, emergency exit и проверки состояния |
| 994–1034 | Фиксация/бондаж | `restraint_bondage` | `candidate` / `manual_only` / `research_only` | Quick-release варианты возможны; остальные идеи сохраняются в research-контуре |
| 1049–1089 | Сенсорика | `sensory_play` | `candidate` / `manual_only` / `research_only` | Реквизит и воздействие требуют отдельной классификации до создания seed |
| 1104–1144 | Ударные воздействия | `impact_play` | `candidate` / `manual_only` / `needs_safe_rewrite` | Нужны зоны, лимиты и check-in; исходные идеи сохраняются с пометкой |
| прочие блоки | Унижение, сервис, психоконтроль, гибриды и сценарии | `control_protocol`, `service_care`, `roleplay`, `scenario` | индивидуально | Реальное принуждение, публичность, лишение базовых потребностей и наказание за stop исключить; сценарии хранить ссылками |
| 3937+ | Долгосрочная progression/«максимумы» | `progression_policy` | `needs_safe_rewrite` | Идея сохранена, но не переносится в исполняемую автоматическую progression |

## Decision vocabulary

- `candidate`: кандидат на редактуру и moderation; не означает готовность к импорту.
- `manual_only`: disposition источника — карточка не выводится из источника автоматически;
  в рантайме опт-ин пользователя = одобрение по умолчанию (ADR-106), `automation_allowed` —
  информационные метаданные.
- `needs_safe_rewrite`: идея сохранена, но исполняемая карточка требует редакции.
- `research_only`: идея сохранена в источниковом справочнике, но не участвует в LLM,
  планировщике, сценариях или progression.
- `split`: исходник сохраняется, а производная карточка создаётся отдельно после редакции.

## Поштучный pass — инструкция следующему агенту

1. [x] Извлечь 163 содержательных `Название:` с source line; строку 515 игнорировать как шаблон.
2. [x] Не копировать описания. Для каждой строки записать source title, стабильный source ID,
   предварительный disposition и короткий reason code.
3. Использовать reason codes: `BREATH_NECK`, `INGESTION_BIOHAZARD`, `MEDICAL_VOLUME`,
   `NO_SELF_RELEASE`, `VULNERABLE_ZONE`, `AUTO_ESCALATION`, `BASIC_NEED_DENIAL`,
   `PUBLIC_EXPOSURE`, `FORCED_MEDIA`, `SAFE_REWRITE_POSSIBLE`.
4. [ ] Для `split` создавать отдельный новый draft только после ручной редакции; не делать
   механический paraphrase опасной инструкции.
5. [x] Сверить количество: `source_total=164`, `template_rows=1`, `classified_content_rows=163`.
