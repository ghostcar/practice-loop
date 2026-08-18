# Предлагаемый контракт карточки adult activity

> Статус: proposal для review. Это логический manifest-контракт, а не утверждённая схема БД.
> ADR-031 сохраняется: до отдельного решения владельца базовой сущностью остаётся `Entity`.

## Разделение сущностей

1. **Activity card** — одно заранее отредактированное действие без свободно сгенерированных шагов.
2. **Preparation/recovery card** — самостоятельная безопасная подготовка, check-in или aftercare.
3. **Scenario** — упорядоченные ссылки на карточки с checkpoint между ними; не копия инструкций.
4. **Progression policy** — отдельная ручная политика; никогда не повышает риск автоматически.

## Manifest v1

| Поле | Тип | Назначение |
| --- | --- | --- |
| `schema_version` | const `adult-activity/v1alpha1` | Версия контракта |
| `slug` | string | Стабильный уникальный ASCII slug |
| `status` | enum | `draft`, `reviewed`, `approved`, `rejected` |
| `content_kind` | enum | `activity`, `preparation`, `checkin`, `aftercare` |
| `title.ru/en` | string | Локализованное короткое название |
| `summary.ru/en` | string | Курируемое описание, не LLM-инструкция |
| `category` / `subcategory` | slug | Нормализованная таксономия |
| `tags`, `role_tags` | string[] | Машинные locale-neutral признаки |
| `participants` | object | min/max и допустимые режимы `solo/partnered` |
| `eligibility` | object | adult-only, opt-in, актуальный pre-session check-in |
| `risk` | object | level, automation, запрещённые сочетания и review notes |
| `parameters` | object | Только типизированные значения, единицы и hard caps |
| `requirements` | object | Инвентарь, пространство, quick release, доступность помощи |
| `safety` | object | prerequisites, stop conditions, checkpoints, recovery |
| `evidence_policy` | object | `none`, optional timer/text; медиа только добровольно |
| `gamification` | object | Награда допустима; safety stop и foundation без штрафа |
| `source` | object | Provenance без копирования чувствительного исходного текста |

## Инварианты lint

- `adult_only=true`, `explicit_opt_in_required=true` и `session_checkin_required=true`.
- `risk.level in {low,elevated}` для seed; `elevated` требует подтверждения каждой сессии.
- `automation_allowed=false` для неоценённых/high/manual-only карточек.
- `penalty_enabled=false` для consent, check-in, stop, debrief и aftercare.
- Любой числовой параметр имеет единицу, минимум и hard maximum.
- Нельзя задавать автоматический рост длительности, интенсивности или повторов.
- Нельзя штрафовать отказ, остановку, пропуск check-in или снижение сложности.
- `stop_conditions` непусты; для restraint требуется `quick_release_required=true`.
- Фото/видео не бывают обязательными доказательствами.
- LLM выбирает только slug/approved parameter value; свободный текст не становится заданием.

## Отображение на текущую `Entity`

Без миграции можно отобразить identity/category/tags/role/risk/penalty/params, но нельзя надёжно
разместить eligibility, requirements, stop/checkpoint/aftercare и evidence policy. Не следует
складывать их в `real_name`, произвольные tags либо невалидируемый `gamification_config`.

Перед importer нужен выбор владельца:

- рекомендуемый переходный вариант — типизированный `safety_contract` JSONB плюс
  `automation_allowed`, `adult_only`, `content_status` и `content_version`;
- нормализация в отдельные таблицы требует явного пересмотра ADR-031 и сейчас не предполагается.
