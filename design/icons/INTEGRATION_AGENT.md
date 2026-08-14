# Задание агенту: интеграция PracticeLoop icon pack

## Цель

Подключить готовый пакет из `design/icons/` к Jinja/HTMX frontend. Геометрию иконок не менять,
новый внешний icon package и CDN не добавлять. До начала работы прочитать обязательные документы
проекта и соблюдать `DESIGN.md`, особенно разделы 10, 14, 15 и 18.

## 1. Перенос runtime-assets

1. Скопировать `design/icons/sprite.svg` в `app/static/icons/sprite.svg`.
2. Скопировать содержимое `design/icons/favicon/` в `app/static/favicon/`.
3. Отдельные файлы из `design/icons/svg/` в runtime не копировать, если sprite работает во всех
   целевых браузерах. Они являются исходниками и fallback-набором.

## 2. Jinja-компонент

Создать `app/templates/components/icon.html` с макросом `icon(name, class_name='w-5 h-5',
label=None)`. Рекомендуемая разметка:

```jinja2
{% macro icon(name, class_name='w-5 h-5', label=None) -%}
<svg class="{{ class_name }}" fill="none" stroke="currentColor" stroke-width="1.75"
     stroke-linecap="round" stroke-linejoin="round"
     {% if label %}role="img" aria-label="{{ label }}"{% else %}aria-hidden="true"{% endif %}>
  <use href="/static/icons/sprite.svg#icon-{{ name }}"></use>
</svg>
{%- endmacro %}
```

Импортировать макрос в шаблонах через `{% from "components/icon.html" import icon %}`. Не
передавать в `name` пользовательские данные. Для динамического имени использовать только
серверный allowlist.

## 3. Browser/navigation icons

Добавить в `<head>` файла `app/templates/base.html`:

```html
<link rel="icon" href="/static/favicon/favicon.ico" sizes="any">
<link rel="icon" href="/static/favicon/favicon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="/static/favicon/apple-touch-icon.png">
<link rel="manifest" href="/static/favicon/site.webmanifest">
<link rel="mask-icon" href="/static/favicon/safari-pinned-tab.svg" color="#6B57A5">
<meta name="theme-color" content="#6B57A5">
```

Проверить, что FastAPI StaticFiles отдаёт `.webmanifest`, SVG, PNG и ICO без auth redirect.

## 4. Карта основной навигации

| UI | icon name |
| --- | --- |
| Dashboard / Сегодня | `dashboard` или `home` |
| Tasks | `tasks` |
| Training | `training` |
| Catalog | `catalog` |
| Points | `points` |
| Import | `import` |
| Diets | `diet` |
| Social | `users` |
| Lock Timer | `timer` |
| Admin | `admin` |
| Notifications | `bell` |
| Logout | `logout` |
| Theme light/dark | `sun` / `moon` |

Сохранить фактическую навигацию v0.8-actual и ADR-033; не перестраивать её по v0.7-spec в рамках
этой задачи.

## 5. Карта разделов и действий

| Семантика | icon name |
| --- | --- |
| History / recent activity | `history` |
| Calendar / schedule | `calendar` / `schedule` |
| Measurements / body areas | `measurement` / `body` |
| Inventory / locations | `inventory` / `location` |
| Achievements | `trophy` |
| LLM / provider / API key | `ai` / `key` |
| Telegram | `telegram` |
| Privacy / verification | `privacy` / `shield` |
| Profile / relationships | `profile` / `relationship` |
| Feed / publish | `activity` / `send` |
| Add / edit / save / delete | `plus` / `edit` / `save` / `delete` |
| Search / filter / more | `search` / `filter` / `more` |
| Upload / download / export | `upload` / `download` / `export` |
| Start / pause / skip / stop | `play` / `pause` / `skip` / `stop` |
| Success / warning / error / info | `check-circle` / `warning` / `error` / `info` |
| Public / private | `globe` / `lock` |
| Previous / next | `chevron-left` / `chevron-right` |

Остальные имена перечислены в `design/icons/preview.html` и `design/icons/svg/`.

## 5.1. Карта будущей архитектуры (`examples/New_doc`)

Эти иконки зарезервированы для будущих модулей. Их наличие в пакете не означает, что модуль уже
реализован или что его разрешено включать без соответствующего roadmap gate.

| Будущий контур | icon name |
| --- | --- |
| Today projection | `today` |
| Media Vault | `media-vault` |
| Consent / discretion | `consent` / `discretion` |
| Audit / restore / outbox transport | `audit` / `restore` / `transport` |
| Chastity device / comfort | `device` / `comfort` |
| Check-in / accepted agreement | `check-in` / `agreement` |
| Hidden end / extension | `hidden` / `extension` |
| Aftercare / private journal | `aftercare` / `report` |
| Personal Care / routines | `nail-care` / `routine` |
| Medication / prescription | `medication` / `prescription` |
| Health / symptoms / sleep / labs | `health` / `symptoms` / `sleep` / `lab` |
| Cycle / Personal Insights | `cycle` / `insights` / `correlation` |
| Social community / comments | `community` / `comment` |
| Verification / voting / block | `verification` / `vote` / `block` |
| D/s Dynamics | `dynamics` |
| Capability grant / policy | `capability` / `grant` / `policy` |
| Explicit confirmation | `confirm` |

Не использовать `dynamics`, `grant`, `policy` или `capability` как обозначение глобальной роли
аккаунта: будущая модель хранит независимые отношения и ограниченные объектные полномочия.

## 6. Правила замены

1. Заменить все emoji, используемые как UI-иконки, на макрос. Текстовые emoji внутри реального
   пользовательского контента не трогать.
2. Заменить существующие inline-SVG на макрос, если в пакете есть семантически точная иконка.
3. Декоративным иконкам оставить `aria-hidden="true"`. Icon-only кнопкам обязательно дать
   локализованный `aria-label` и видимый tooltip/title.
4. Статус никогда не обозначать только цветом: рядом оставить текст или доступное имя.
5. Размеры: `w-4 h-4` внутри compact controls, `w-5 h-5` в навигации/кнопках, `w-6 h-6` в
   заголовках, максимум `w-12 h-12` в empty state.
6. Цвет задавать Tailwind-классом на `<svg>`, геометрия использует `currentColor`.
7. Не вставлять SVG через `innerHTML` и не формировать строками из пользовательских значений.

## 7. Проверки после интеграции

1. `rg -n "[\\x{1F300}-\\x{1FAFF}]" app/templates` — вручную классифицировать остатки emoji.
2. `rg -n "<svg" app/templates` — оставить только обоснованные уникальные иллюстрации.
3. Проверить отсутствие битых `<use>` по allowlist имён из `sprite.svg`.
4. Проверить light/dark, hover, focus, disabled и active-nav состояния.
5. Вручную проверить `360×800`, `768×1024`, `1280×800`.
6. Проверить Chrome/Firefox favicon, Safari pinned tab и iOS Apple Touch Icon.
7. Запустить frontend/template тесты, полный pytest и ruff в соответствии с правилами проекта.
8. Добавить тест, который сверяет использованные Jinja icon names с ID символов в sprite.

## Не входит в задачу

- изменение информационной архитектуры;
- редизайн экранов;
- добавление JS icon-loader;
- загрузка иконок с CDN;
- изменение доменной логики или API.
