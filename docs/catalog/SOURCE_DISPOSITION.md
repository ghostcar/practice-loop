# Матрица разбора `examples/category-chat.md`

> Матрица описывает области и правила классификации. Имена исходника ещё должны быть разнесены
> поштучно в machine-readable inventory; статус строки не наследуется автоматически от области.

| Source lines | Исходная область | Нормализованная область | Решение по умолчанию | Причина / обработка |
| --- | --- | --- | --- | --- |
| 706–746 | Жидкости, удержание, клизмы | `body_control` | `manual_only` или `excluded` | Медицинские/гигиенические риски, опасные объёмы и запрет базовых потребностей; безопасные нейтральные check-in/preparation выделять отдельно |
| 765–809 | Туалетный контроль | `toilet_control` | `manual_only` или `excluded` | Инфекционные и медицинские риски; автоматические инструкции и ingestion исключать |
| 825–865 | Ограничение дыхания | `breath_restriction` | `excluded` | Starter seed и automation полностью исключают дыхание, шею, rebreathing, пакеты, воду и потерю сознания |
| 880–924 | Интимная техника | `sexual_connection` | `manual_only` | Только явный opt-in; исключить дыхательные сочетания, принудительную глубину и injury-oriented progression |
| 939–979 | Ношение/целомудрие | `device_timer` / `sensory_play` | `allowed` или `manual_only` | Допустимы лишь capped варианты с локальным emergency exit, skin/circulation check и добровольным снятием |
| 994–1034 | Фиксация/бондаж | `restraint_bondage` | `allowed`, `manual_only` или `excluded` | Low/elevated quick-release варианты возможны; шея, suspension, полная невозможность выхода и опасные позы исключаются |
| 1049–1089 | Сенсорика | `sensory_play` | `allowed` или `excluded` | Allowlist безопасного реквизита; огонь/опасный воск, электричество, vacuum и край исключить из starter automation |
| 1104–1144 | Ударные воздействия | `impact_play` | `allowed`, `manual_only` или `excluded` | Только разрешённые безопасные зоны, лимиты и check-in; уязвимые зоны и endurance/escalation исключить |
| прочие блоки | Унижение, сервис, психоконтроль, гибриды и сценарии | `control_protocol`, `service_care`, `roleplay`, `scenario` | индивидуально | Реальное принуждение, публичность, лишение базовых потребностей и наказание за stop исключить; сценарии хранить ссылками |
| 3937+ | Долгосрочная progression/«максимумы» | `progression_policy` | `excluded` | Не переносить точные опасные режимы, автоматическое усиление и псевдомедицинские нормы |

## Decision vocabulary

- `allowed`: кандидат на редактуру и moderation; не означает готовность к импорту.
- `manual_only`: личный ручной запуск, `automation_allowed=false`, без автокомпозиции/эскалации.
- `excluded`: система не хранит как seed и не выдаёт инструкций/параметров.
- `split`: исходная строка смешивает допустимый и запрещённый элементы; создаётся только новая
  безопасная карточка, а исходный текст не переносится.

## Поштучный pass — инструкция следующему агенту

1. Извлечь 163 содержательных `Название:` с source line; строку 515 игнорировать как шаблон.
2. Не копировать описания. Для каждой строки записать только source title, normalized slug,
   `content_kind`, disposition и короткий reason code.
3. Использовать reason codes: `BREATH_NECK`, `INGESTION_BIOHAZARD`, `MEDICAL_VOLUME`,
   `NO_SELF_RELEASE`, `VULNERABLE_ZONE`, `AUTO_ESCALATION`, `BASIC_NEED_DENIAL`,
   `PUBLIC_EXPOSURE`, `FORCED_MEDIA`, `SAFE_REWRITE_POSSIBLE`.
4. Для `split` создавать отдельный новый draft только после ручной редакции; не делать
   механический paraphrase опасной инструкции.
5. Сверить количество: `source_total=164`, `template_rows=1`, `classified_content_rows=163`.
