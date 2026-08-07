# PracticeLoop — дизайн-система и UI-контракт

> Версия: 1.0 для PracticeLoop v0.7.  
> Статус: обязательный источник требований для frontend.  
> Связанная спецификация: `REMEDIATION_SPEC.md`.

## 1. Цель интерфейса

PracticeLoop должен восприниматься как спокойный, приватный и взрослый персональный ассистент,
а не как игровая админ-панель, fitness-dashboard или набор несвязанных CRUD-форм.

Основное ощущение:

- **спокойствие** — минимум визуального шума и соревновательного давления;
- **ясность** — в каждый момент виден один главный следующий шаг;
- **приватность** — нейтральные формулировки и отсутствие чувствительных деталей вне нужного
  контекста;
- **контроль** — понятно, почему пункт появился, как изменить частоту и как остановить выполнение;
- **зрелость** — сдержанная типографика, один акцентный цвет, иконки вместо emoji.

## 2. Обязательные принципы

1. **Сначала действие, потом аналитика.** План и текущий пункт находятся выше графиков и метрик.
2. **Один основной CTA на экран.** Вторичные действия визуально тише.
3. **Состояние важнее украшения.** Цвет сообщает статус, а не создаёт декор.
4. **Одна дизайн-система.** В шаблонах нет параллельных наборов `slate`, `gray`, произвольных
   hex-цветов и уникальных карточек.
5. **Одинаковая семантика в обеих темах.** Светлая тема не является инверсией тёмной.
6. **Mobile-first.** Core-flow полностью работает на ширине 360 px.
7. **Progressive enhancement.** Базовые формы и переходы работают без JavaScript; HTMX улучшает
   опыт, но не является единственным способом завершить действие.
8. **Никаких скрытых решений.** Пользователь видит due-причину, частоту, вариант и результат.
9. **Остановка всегда заметна.** В активной сессии кнопка Stop не скрывается в меню.
10. **Интерфейс не нормализует риск.** `manual only`, ограничения сложности и предупреждения
    показываются явно и не перекрываются геймификацией.

## 3. Информационная архитектура

### 3.1. Основная навигация

| Раздел | Route | Содержание |
| --- | --- | --- |
| Сегодня | `/today` | План, активный пункт, обязательные/перенесённые элементы, короткая рефлексия |
| Каталог | `/catalog` | Доступные и личные практики, включение, отношение, частота, варианты |
| История | `/history` | Хронология выполнения, фильтры, feedback и отдельная аналитика |
| Ещё | `/more` | Расписание, баллы, замеры, инвентарь, импорт, LLM, приватность и настройки |

Правила:

- для авторизованного пользователя `/` перенаправляет на `/today`;
- admin/moderation не находятся в основной навигации;
- уведомления и профиль доступны из utility-зоны shell;
- отдельные пункты `Tasks`, `Training`, `Points` и `Admin` удаляются из верхнего уровня;
- feature flag скрывает раздел полностью, а не оставляет неработающую ссылку.

### 3.2. Термины интерфейса

| Внутреннее понятие | RU | EN |
| --- | --- | --- |
| Practice | Практика | Practice |
| Daily plan | План дня | Daily plan |
| Session | Сессия | Session |
| Variant | Вариант | Variant |
| Difficulty | Сложность | Difficulty |
| Due | Пора повторить | Due |
| Overdue | Срок превышен | Overdue |
| Mandatory rotation | Обязательная ротация | Required rotation |
| Complete | Завершить | Complete |
| Stop | Остановить | Stop |
| Skip | Пропустить | Skip |
| Strong aversion | Крайне не хочется | Strong aversion |
| Manual only | Только вручную | Manual only |

В пользовательском UI не использовать `Entity`, `opt-in`, `unacceptable`, `raw response`,
`penalty escalation` и названия внутренних статусов без перевода.

## 4. App shell и адаптивность

### 4.1. Breakpoints

Используются стандартные контрольные ширины:

- mobile: `< 768 px`;
- tablet: `768–1023 px`;
- desktop: `>= 1024 px`;
- wide: `>= 1280 px`.

QA выполняется минимум на `360×800`, `768×1024` и `1280×800`.

### 4.2. Desktop

- фиксированная левая панель: `240 px`;
- логотип/название сверху, 4 основных пункта посередине, профиль и настройки снизу;
- utility header контента: `64 px`, содержит title context, уведомления и page actions;
- максимальная ширина полезного контента: `1120 px`;
- внешний padding: `32 px`, между крупными секциями `24 px`;
- sidebar не прокручивается вместе с контентом.

### 4.3. Tablet

- левая icon rail: `72 px`;
- подписи доступны в tooltip и для screen reader;
- content padding: `24 px`;
- двухколоночный layout разрешён только при минимальной ширине колонки `320 px`.

### 4.4. Mobile

- верхняя панель: `56 px`, title + notifications/profile;
- нижняя навигация: `64 px` + safe-area inset, ровно 4 пункта;
- content padding: `16 px`;
- все core screens одноколоночные;
- sticky CTA не перекрывает последний элемент: снизу оставляется соответствующий padding;
- таблицы заменяются карточками/списками, горизонтальная прокрутка core-контента запрещена.

### 4.5. Активная навигация

Активный пункт отличается одновременно:

- мягким accent-фоном;
- accent-иконкой;
- font weight `600`;
- `aria-current="page"`.

Одного изменения цвета текста недостаточно.

## 5. Экранные контракты

### 5.1. Сегодня

Это домашний экран продукта. Порядок блоков фиксирован.

1. Дата и заголовок `Сегодня`.
2. Краткая строка состояния: сколько due, overdue и manual-only.
3. Активная сессия **или** primary card следующего действия.
4. План дня с due-reason у каждого пункта.
5. Перенесённые/конфликтующие пункты с объяснением.
6. Ручные due-практики.
7. Небольшая сводка прогресса; ссылка на Историю.

Desktop может использовать раскладку `minmax(0, 2fr) minmax(280px, 1fr)`:

- слева active/plan;
- справа manual due, upcoming и компактная сводка.

На mobile всё идёт в указанном выше порядке. Графиков на `/today` нет.

#### Состояния Today

| Состояние | Главный CTA | Дополнительное действие |
| --- | --- | --- |
| Нет плана | `Собрать план` | `Настроить практики` |
| План готов | `Начать` | `Изменить план` |
| Есть active item | `Продолжить` | Stop виден в самой карточке |
| LLM недоступен | `Собрать без LLM` | `Повторить` |
| Нет включённых практик | `Перейти в каталог` | Нет пустого disabled CTA |
| Все выполнено | `Завершить день` | `Посмотреть историю` |

### 5.2. Активная сессия

На экране одновременно доминирует один active item:

- название и variant;
- краткие утверждённые шаги;
- прогресс по фазам/времени, если он определён шаблоном;
- компактное объяснение `Почему сейчас`;
- primary action `Завершить`;
- secondary action `Пропустить`;
- постоянное отдельное действие `Остановить` с danger-семантикой, но без пугающего оформления;
- следующий пункт показан только превью, без конкурирующего CTA.

После результата показывается короткий feedback sheet:

- оценка сложности: `слишком легко / подходяще / слишком сложно`;
- необязательная заметка;
- кнопка `Сохранить`;
- отсутствие feedback не блокирует выход.

### 5.3. Каталог

Каталог — список, а не декоративная сетка карточек.

Верхняя зона:

- поиск;
- tabs `Подключённые`, `Доступные`, `Личные`;
- filters: category, status, automation, attitude;
- CTA `Создать личную практику`.

Строка практики содержит:

- title, category и version/source;
- badges `Private`, `Published`, `Manual only`, risk state при необходимости;
- отдельный переключатель `В ротации`;
- краткое значение отношения и частоты;
- действие `Настроить`.

Отсутствующая персональная настройка трактуется как `enabled=false`. Нельзя визуально показывать
неподключённую практику включённой.

Редактор открывается в side sheet на desktop и full-screen sheet на mobile. Порядок полей:

1. `В ротации`;
2. отношение;
3. желаемый интервал;
4. максимальный перерыв;
5. предел сложности;
6. разрешённые варианты;
7. режим автоматизации;
8. Save.

При выборе отношения интерфейс может предложить значения частоты, но всегда показывает реальные
числа до сохранения.

### 5.4. История

По умолчанию показывается хронология, сгруппированная по локальной дате.

Каждый элемент содержит:

- status icon + текстовый status;
- practice/variant;
- время;
- due reason;
- points/XP только вторичной строкой;
- feedback, если он есть.

Фильтры: period, status, category, practice. Аналитика находится в отдельной вкладке `Статистика`
и не загружается до её открытия.

### 5.5. Ещё

Раздел использует сгруппированный список:

- `Планирование`: расписание;
- `Данные`: баллы, замеры, инвентарь, импорт/экспорт;
- `Подключения`: LLM, Telegram после включения feature flag;
- `Аккаунт`: язык, тема, приватность, экспорт, удаление.

Каждый пункт имеет одну иконку, title, краткое описание и chevron. Dashboard-tiles запрещены.

### 5.6. Admin и moderation

- отдельный `admin_shell` с явной маркировкой роли;
- навигация: moderation queue, templates, users, system settings;
- пользовательские метрики и Today в admin shell не дублируются;
- destructive actions требуют confirmation dialog и причины;
- email и приватные данные не показываются там, где достаточно ID/псевдонима.

### 5.7. Auth

- центрированная колонка `400 px`, mobile `100%`;
- логотип, короткий нейтральный title, форма;
- без feature teaser, emoji и маркетинговых градиентов;
- ошибки рядом с полем и общий alert только для системной ошибки;
- password manager и browser autofill не ломаются.

## 6. Цветовая система

### 6.1. Правило использования

Шаблоны используют только semantic tokens. Запрещены прямые классы вида `bg-slate-800`,
`text-gray-400`, `from-indigo-*`, `bg-white`, произвольные hex и opacity-комбинации для
семантических состояний.

### 6.2. Токены

```css
:root,
html[data-theme="light"] {
  --color-canvas: #F7F7FA;
  --color-surface: #FFFFFF;
  --color-surface-soft: #F0EFF4;
  --color-surface-raised: #FFFFFF;
  --color-border: #E1DFE7;
  --color-border-strong: #C9C6D1;

  --color-text: #1C1B22;
  --color-text-secondary: #656472;
  --color-text-disabled: #92909B;

  --color-accent: #6B57A5;
  --color-accent-hover: #59458F;
  --color-accent-soft: #EEE9F8;
  --color-on-accent: #FFFFFF;

  --color-success: #2F7657;
  --color-success-soft: #E4F2EA;
  --color-warning: #9A6415;
  --color-warning-soft: #F8EEDC;
  --color-danger: #A83B4A;
  --color-danger-soft: #F8E4E7;
  --color-info: #356A9A;
  --color-info-soft: #E3EEF7;

  --color-focus: #8065C5;
  --color-overlay: rgb(18 17 22 / 48%);
}

html[data-theme="dark"] {
  --color-canvas: #121116;
  --color-surface: #1A191F;
  --color-surface-soft: #232129;
  --color-surface-raised: #292731;
  --color-border: #34313B;
  --color-border-strong: #4A4653;

  --color-text: #F3F0F7;
  --color-text-secondary: #AAA6B2;
  --color-text-disabled: #77727F;

  --color-accent: #B8A3EE;
  --color-accent-hover: #C8B7F3;
  --color-accent-soft: #2C2540;
  --color-on-accent: #1C1629;

  --color-success: #71C89D;
  --color-success-soft: #183629;
  --color-warning: #E4B064;
  --color-warning-soft: #3A2D1C;
  --color-danger: #FF9AA4;
  --color-danger-soft: #402228;
  --color-info: #8DB9E6;
  --color-info-soft: #1D3042;

  --color-focus: #B8A3EE;
  --color-overlay: rgb(0 0 0 / 64%);
}
```

Основной текст, secondary text и accent-комбинации должны соответствовать WCAG AA. Статус
никогда не кодируется только цветом: рядом есть icon и/или текст.

### 6.3. Запрещённые визуальные приёмы

- градиенты в кнопках, заголовках, progress bars и фоне приложения;
- glassmorphism/backdrop blur для обычных поверхностей;
- постоянные цветные тени;
- hover-подъём каждой карточки;
- одновременно несколько акцентных цветов;
- красный цвет для `strong_aversion`: это настройка частоты, а не ошибка;
- декоративные emoji в навигации, заголовках и кнопках.

## 7. Типографика

### 7.1. Шрифт

Основной: self-hosted `Inter Variable`; fallback:

```css
font-family: Inter, ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif;
```

Удалённые Google Fonts и другие font CDN запрещены. Метрики используют `font-variant-numeric:
tabular-nums`.

### 7.2. Шкала

| Token | Размер/line-height | Weight | Использование |
| --- | --- | --- | --- |
| `display` | 32/40 desktop, 28/36 mobile | 700 | Только landing/empty milestone |
| `h1` | 28/36 desktop, 24/32 mobile | 700 | Заголовок страницы |
| `h2` | 22/28 | 650 | Крупная секция |
| `h3` | 18/24 | 600 | Card/подсекция |
| `body` | 16/24 | 400 | Основной текст |
| `body-sm` | 14/20 | 400/500 | Controls, secondary text |
| `caption` | 12/16 | 500 | Metadata, badge |

Текстовая строка не шире `72ch`. Uppercase используется только для коротких технических codes,
не для заголовков.

## 8. Геометрия и плотность

Сетка основана на `4 px`.

| Token | Значение |
| --- | --- |
| `space-1` | 4 px |
| `space-2` | 8 px |
| `space-3` | 12 px |
| `space-4` | 16 px |
| `space-5` | 20 px |
| `space-6` | 24 px |
| `space-8` | 32 px |
| `space-10` | 40 px |

Радиусы:

- input/button: `10 px`;
- card/panel: `12 px`;
- dialog/sheet: `16 px`;
- badge/avatar: `999 px`;
- вложенный элемент не может иметь радиус больше родителя.

Тени:

- обычные cards: без тени, border `1 px`;
- raised popover/dialog: `0 12px 32px rgb(18 17 22 / 16%)`;
- focus использует ring, а не shadow elevation.

## 9. Компоненты

### 9.1. Buttons

Варианты: `primary`, `secondary`, `ghost`, `danger`, `link`.

- стандартная высота `44 px`;
- mobile touch target не менее `44×44 px`;
- horizontal padding `16 px`, gap icon/text `8 px`;
- один primary CTA в видимой области;
- destructive action не может выглядеть как primary accent;
- disabled-состояние не заменяет объяснение: причина доступна рядом;
- loading сохраняет ширину кнопки и содержит текст/aria state.

### 9.2. Form controls

- label всегда видим, placeholder не заменяет label;
- input/select/textarea высотой минимум `44 px`;
- hint и error связаны через `aria-describedby`;
- error содержит текст, border и icon;
- checkbox используется для независимого множества, radio — для взаимоисключающего выбора;
- switch используется только для мгновенного boolean-состояния (`В ротации`);
- сохранение сложной настройки выполняется отдельной кнопкой, не onchange autosubmit;
- frequency поля показывают единицы и итоговую фразу: `примерно раз в 7 дней, не реже 14 дней`.

### 9.3. Cards и list rows

Card применяется только для смысловой группы, а не для каждого числа.

- padding `16 px` mobile, `20 px` desktop;
- title и action выровнены по первой строке;
- вложенность card-in-card запрещена; использовать section/divider;
- hover state только у полностью кликабельных rows;
- кликабельная область имеет явный focus state.

### 9.4. Status badges

Допустимы: neutral, accent, success, warning, danger, info.

- высота `24 px`;
- padding `6–8 px`;
- caption weight `600`;
- status отображается полным словом, не `comp`, `inte` или raw enum;
- badge не используется как интерактивная кнопка без соответствующей семантики.

### 9.5. Alerts и notifications

- inline alert остаётся рядом с причиной;
- toast используется только для результата фонового/HTMX-действия;
- critical error не исчезает автоматически;
- success toast может исчезнуть через 4–6 секунд;
- ошибки LLM не показывают raw response;
- область обновлений имеет `aria-live="polite"`.

### 9.6. Dialog и sheet

- dialog для подтверждения; sheet для редактирования большого набора полей;
- desktop dialog max-width `480 px`, editor sheet `520 px`;
- mobile sheet занимает экран и сохраняет видимые Back/Save;
- focus trap, Escape, возврат фокуса инициатору обязательны;
- опасное действие формулируется конкретно: что будет удалено и обратимо ли это.

### 9.7. Empty/loading/error states

Каждый экран имеет три самостоятельных состояния:

- empty: причина + один релевантный CTA;
- loading: skeleton структуры, не полноэкранный spinner;
- error: понятный текст + retry/escape path.

Emoji-иллюстрации запрещены. Допустима простая нейтральная SVG-иконка из общего набора.

## 10. Иконки и графика

- единый набор: Lucide или эквивалентный open-source outline set, поставляемый локально;
- базовый размер `20 px`, компактный `16 px`, empty state `32 px`;
- stroke `1.75–2 px`;
- декоративная иконка получает `aria-hidden="true"`;
- icon-only button имеет `aria-label` и tooltip;
- нельзя смешивать emoji, filled icons и outline icons;
- логотип не должен определять цветовую систему интерфейса; до отдельного брендинга используется
  wordmark `PracticeLoop` без градиента.

## 11. Графики и метрики

Графики находятся только в `История -> Статистика` и профильных экранах данных.

- не более двух графиков на одном viewport;
- высота `220 px` mobile, `260 px` desktop;
- каждый график имеет title, период, единицы и текстовую сводку;
- доступна табличная альтернатива;
- palette: accent, info, success, warning, neutral; danger только для реальной негативной метрики;
- линии минимум `2 px`, точки минимум `4 px` при интерактивности;
- сетка и подписи используют semantic border/text-secondary;
- Chart.js загружается один раз отдельным page module;
- canvas не получает конфликтующие height-классы и inline dimensions;
- данные и итоговые числа вычисляет backend, не browser chart code.

## 12. Motion

- micro interaction: `120 ms`;
- обычный transition: `180 ms`;
- sheet/dialog: `240 ms`;
- easing: `cubic-bezier(0.2, 0, 0, 1)`;
- анимация не смещает постоянный layout;
- глобальный fade-in каждой страницы запрещён;
- hover transform карточек запрещён;
- `prefers-reduced-motion: reduce` отключает все необязательные transitions/animations.

## 13. Язык и тон

Тон: спокойный, прямой, без оценивания и детской геймификации.

Предпочтительно:

- `Пора повторить по вашему интервалу`;
- `Этот пункт остаётся в ротации`;
- `План не поместился полностью: 2 пункта перенесены`;
- `Можно остановить сейчас и вернуться позже`.

Не использовать:

- `Ты провалил`, `Наказание`, `Непослушание`, `AI решил`, `Сюрприз!`;
- чрезмерные восклицания;
- технические ошибки провайдера в пользовательском тексте;
- hardcoded EN/RU строки в шаблонах или JavaScript.

Все строки, включая aria-label, tooltip, chart labels и server errors, проходят через i18n.
Интерфейс должен выдерживать увеличение текста на 30% без обрезки.

## 14. Доступность

Минимальная цель — WCAG 2.2 AA для core-flow.

- landmarks: `header`, `nav`, `main`, `aside`, `footer` по назначению;
- один `h1` на страницу и последовательная иерархия headings;
- skip-link первым focusable элементом;
- полностью видимый focus ring `2 px` + offset `2 px`;
- порядок Tab совпадает с визуальным;
- все действия доступны с клавиатуры;
- screen reader получает результат HTMX-обновления;
- status не кодируется только цветом;
- форма после ошибки фокусирует первый невалидный control;
- dialog/sheet управляет фокусом корректно;
- zoom 200% не вызывает горизонтальный scroll core-flow;
- touch target минимум `44 px`;
- charts имеют текстовую/табличную альтернативу.

## 15. Техническая реализация frontend

### 15.1. Assets

- Tailwind собирается build step, runtime CDN запрещён;
- HTMX, Chart.js, icons и fonts хранятся локально или собираются из lock-файла;
- production использует hashed assets и долгий immutable cache;
- CSS entry содержит semantic tokens и component layers;
- templates не используют произвольные цвета вне semantic mapping.

Целевые выходы:

```text
app/static/dist/app.css
app/static/dist/app.js
app/static/dist/pages/today.js
app/static/dist/pages/catalog.js
app/static/dist/pages/history.js
app/static/dist/pages/charts.js
```

### 15.2. Templates

```text
app/templates/
  layouts/
    base.html
    app_shell.html
    auth_shell.html
    admin_shell.html
  components/
    button.html
    card.html
    form.html
    badge.html
    alert.html
    empty_state.html
    icon.html
  partials/
    today_plan.html
    active_item.html
    catalog_row.html
    history_list.html
  pages/
```

Обязательные blocks базового layout:

```jinja2
{% block title %}{% endblock %}
{% block head %}{% endblock %}
{% block content %}{% endblock %}
{% block scripts %}{% endblock %}
```

`active_nav`, locale, theme, current user и role передаются единым page-context builder.

### 15.3. HTMX

- HTMX обновляет законченную partial-область;
- сервер возвращает одинаковую бизнес-валидацию для HTML и JSON;
- после swap восстанавливаются focus и aria-live announcement;
- ошибки формы возвращаются с исходными значениями и field errors;
- destructive requests включают CSRF;
- `hx-confirm` не заменяет нормальный dialog для необратимых действий;
- полный redirect остаётся рабочим fallback.

### 15.4. JavaScript

- inline scripts запрещены, кроме строго nonce-защищённого bootstrap при доказанной необходимости;
- никакого пользовательского `innerHTML`;
- DOM создаётся через HTMX/Jinja или безопасные DOM APIs с `textContent`;
- page module проверяет наличие root-элемента до инициализации;
- повторный HTMX swap не создаёт дубликаты listeners/charts;
- ошибки логируются нейтрально и отображаются через общий error component;
- бизнес-правила и расчёт rewards не дублируются в browser.

### 15.5. CSP

Целевой production policy не требует `unsafe-inline` для scripts. Внешние CDN origins отсутствуют.
Стиль и script загружаются с текущего origin. Frame ancestors запрещены, если нет отдельного
требования на embedding.

## 16. Правила для coding/LLM-агента

Перед изменением frontend агент обязан:

1. назвать затрагиваемый экран и компонент;
2. использовать существующий semantic token/component либо сначала добавить его в систему;
3. проверить light/dark и RU/EN;
4. проверить mobile/tablet/desktop;
5. добавить/обновить smoke или visual regression test;
6. не добавлять новый паттерн, если существующий решает задачу.

Агенту запрещено:

- «улучшать» дизайн новым градиентом, emoji, shadow или произвольным цветом;
- создавать уникальную button/card-разметку внутри страницы;
- добавлять top-level navigation item без изменения этого документа;
- возвращать графики на Today;
- скрывать Stop в overflow menu;
- использовать autosubmit сложной формы;
- подменять отсутствующие данные нулями без empty state;
- оставлять hardcoded строки «временно»;
- считать работу завершённой только по HTTP 200 без проверки поведения в браузере.

## 17. Визуальная приёмка

Для каждого core screen сохраняются screenshots:

| Экран | 360 | 768 | 1280 | Light | Dark | RU | EN |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Auth | ✓ | — | ✓ | ✓ | ✓ | ✓ | ✓ |
| Today empty | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Today active | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Session active | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Catalog list | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Catalog editor | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| History | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| More | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |

Обязательные автоматические проверки:

- нет horizontal overflow на 360 px;
- нет console errors;
- нет запросов к runtime CDN;
- keyboard проходит весь core-flow;
- automated accessibility scan не содержит critical/serious нарушений;
- все state-changing формы содержат CSRF;
- theme сохраняется после reload;
- active nav корректен;
- локализованные строки не выходят за container;
- скрипты page blocks действительно исполняются после наследования шаблонов.

## 18. Definition of Done для отдельного экрана

Экран считается готовым, только если:

- реализованы loading, empty, error и populated states;
- использованы semantic tokens и общие components;
- все строки локализованы;
- light/dark и три контрольные ширины проверены;
- keyboard/focus/aria проверены;
- нет inline user HTML и дублированного JavaScript;
- есть smoke/e2e test основного действия;
- screenshot review не выявил расхождений с этим документом;
- экран поддерживает core-flow, а не превращается в новый dashboard.
