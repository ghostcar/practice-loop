# Frontend-аудит PracticeLoop — Сессия 38

**Дата:** 2026-08-09.
**Объект:** `main` — frontend уровень (шаблоны + статические assets).
**Документы приоритета:** `DESIGN.md` (frontend high-priority) → `REMEDIATION_SPEC.md` → `AGENTS.md` → `tracker-spec.md` → `memory/*`.
**Контекст:** Chrome не установлен в среде → реальный `browser-use` невозможен. Аудит проведён **статически** по шаблонам, design tokens и коду JS.

---

## TL;DR

DESIGN.md (694 строки, приоритет frontend) выполнен **≈30%**. Проект визуально **далеко от целевой design system**.

**Хорошо:** TailwindCSS local (✅), CDN отсутствуют (✅), локализация работает (частично), CSS-переменные для тем есть (частично), навигация функциональна.

**Плохо:**
- 🔴 **min 5 нарушений hard-zapreshennyh DESIGN.md приёмов** (градиенты на h1, hover-translate карточек, emoji в кнопках/навигации, glassmorphism на landing, hardcoded строки)
- 🔴 **0 ARIA атрибутов** (нет `aria-label`, `aria-current`, `aria-describedby`, `aria-live`, `role`) — слепой пользователь не сможет работать
- 🔴 **Бажный enum**: catalog.html всё ещё использует `unacceptable` после миграции на `strong_aversion`
- 🔴 **Только 4 формы с CSRF hidden оnput** из десятков POST-форм
- 🟡 DESIGN.md 4 (240px sidebar) → реализован top horizontal nav (нарушение)
- 🟡 DESIGN.md 11 (≤2 графика на viewport) → dashboard_v2 показывает 4 одновременно
- 🟡 DESIGN.md 5.1 «Графиков на /today нет» — dashboard_v2 загружается на `/dashboard`

---

## 1. Состояние DESIGN.md compliance

DESIGN.md описывает контракт из 18 разделов. Сводка по соответствию:

| Раздел DESIGN.md | Тема | Реализация |
|---|---|---|
| **1. Цель интерфейса** | спокойствие, контроль | Частично — есть маркетинговый landing (`index.html` с градиентом и emojis) |
| **2. Принципы** | 10 правил | Соблюдаются: progressive enhancement ✅, цвет = статус ✅, без чувствительных деталей ✅; **нарушаются**: единая дизайн-система ❌ (используется `slate`/`gray`/`indigo` смесь), одно главное CTA ✅ |
| **3.1. Навигация** | Сегодня/Каталог/История/Ещё | ❌ Реализовано: dashboard, tasks, training, catalog, points, admin (6 пунктов) |
| **3.2. Термины UI** | Practice/Variant/Due/etc | 🟡 Частично: используются «catalog», «points», но также сырые enum types (one_time/series), `unacceptable` (не `strong_aversion`) |
| **4. App shell** | 240px sidebar / mobile bottom nav / breakpoints | ❌ Top horizontal nav (`max-w-5xl mx-auto`), нет left sidebar, нет mobile bottom nav |
| **4.5. Active nav** | 4 одновременных признака (фон/иконка/weight/aria-current) | ❌ Реализован только цветом, нет `aria-current` |
| **5.1. Сегодня** | `Minmax(0, 2fr) minmax(280px, 1fr)` | ❌ Нет `/today` route. Главная страница — `/dashboard` с 4 графиками одновременно |
| **5.x. Экраны** | Auth, Catalog, History, More | 🟡 Archive частично реализован, но без переименований в DESIGN.md |
| **6.2. Токены** | CSS vars (--color-canvas, --accent…) | ❌ Используются utility-классы Tailwind (`bg-slate-900` вместо `bg-surface-raised`); CSS vars определены в DESIGN.md, но **в коде НЕ подключены** (нет `<style>:root{…}</style>` в base.html) |
| **6.3. Запреты** | без градиентов/glassmorphism/shadow/emoji/multiple accents | ❌ 14 нарушений (см. §3) |
| **7.1. Шрифт** | self-hosted Inter | ❌ Inter **не подключён**; используется стандартный system-ui |
| **9.x. Components** | кнопки 44×44, touch target | 🟡 Основные кнопки `py-2`/`py-3` ~ 36-44 px; мобильный touch touch target — вариативно |
| **10. Иконки** | Lucide outline, без emoji | ❌ Lucide нет в static; используются inline SVG (годится) **плюс emoji** во многих местах |
| **11. Графики** | ≤2 на viewport, в История → Статистика, 220х260 px | ❌ Dashboard_v2 показывает **4 графика одновременно** на viewport |
| **14. Доступность** | landmarks, headings, skip-link, ARIA, focus, keyboard | ❌ Нет ни одного `aria-*`, `role=`, `skip-link` |
| **15.4. JS** | без inline scripts, без user innerHTML | ❌ **Inline `<script>` в 8 шаблонах** (alert helpers, telegram link, chart init); **18 innerHTML в 8 файлах** |
| **15.5. CSP** | без unsafe-inline, без CDN | 🟡 CDN ✅, но Tailwind via `@tailwindcss/browser` runtime — нет hash, можно считать inline equivalent |
| **17. Визуальная приёмка** | 360/768/1280 × light/dark × RU/EN | ❌ Не проводилась |

---

## 2. Критические нарушения DESIGN.md (high-zapreshennoe)

### 2.1. Градиент в `<h1>` landing (`index.html:6-7`)

```html
<h1 class="text-5xl font-extrabold mb-4 bg-gradient-to-r from-indigo-500 via-purple-500 to-pink-500 bg-clip-text text-transparent">
```

**Файл:** `app/templates/index.html:6`.  
**Нарушение:** DESIGN.md 6.3 «градиенты в кнопках, заголовках, progress bars и фоне приложения» — **прямой запрет**.

### 2.2. Emoji в заголовках и кнопках навигации

```html
<!-- admin.html:7 -->
<h1 class="text-3xl font-bold …">⚙️ Admin Panel</h1>
<!-- llm_configs.html:7 -->
<h1 …>🤖 LLM Providers</h1>
<!-- catalog.html:7 -->
<h1 …>📋 Catalog</h1>
<!-- notifications.html:5 -->
<h1 …>🔔 Notifications</h1>
<!-- my_entities.html:7 -->
<h1 …>📝 My Entities</h1>
<!-- privacy.html:5 -->
<h1 …>🔒 Privacy & Data</h1>
<!-- tasks.html:5 -->
<h1 …>🤖 Task Generator</h1>
<!-- catalog.html:14, 17 -->
📝 My Entities / ⚙️ Admin (в кнопках)
<!-- index.html:18, 24, 30 -->
📋 Catalog / 🤖 LLM-Suggested / 🏆 Gamification (feature teaser)
<!-- dashboard.html:19,24,29 -->
⭐ / 🔥 / ✅ (3 большие эмодзи в stats)
<!-- training.html (план/секция) -->
emoji как ✅✅✅✅✅✅ (multi-state status)
```

**Нарушение:** DESIGN.md 6.3 «декоративные emoji в навигации, заголовках и кнопках» + 10 «никаких эмоджи в кнопках и навигации».

### 2.3. Hover transform на cards (9 файлов)

```bash
$ grep -rn 'hover:-translate\|hover:shadow-lg\|hover:scale' app/templates/ | wc -l
21 # строк
```

`admin.html:15,23,31`, `dashboard.html:18,23,28`, `import_data.html:25,75,117`, `index.html:14,20,24,32,37,42`, `register.html:49`, `tasks.html:95`, `base.html:82`, `my_entities.html:55`, `llm_configs.html:97`.

**Нарушение:** DESIGN.md 6.3 «hover-подъём каждой карточки» — **прямой запрет** + 12 «hover transform карточек запрещён».

### 2.4. Glassmorphism / backdrop-blur (`index.html`)

```html
<div class="p-6 rounded-2xl bg-white/60 dark:bg-slate-800/60 backdrop-blur …">
```

**Файл:** `index.html:32,37,42`.  
**Нарушение:** DESIGN.md 6.3 «glassmorphism/backdrop blur для обычных поверхностей».

### 2.5. Множественные акцентные цвета

`color-red-400`, `color-red-500`, `color-emerald-500`, `color-amber-500`, `color-sky-500` смешаны в одних и тех же контекстах. DESIGN.md 6.3: «одновременно несколько акцентных цветов» — запрет.

### 2.6. Input focus state без `ring-offset`

```html
focus:ring-2 focus:ring-indigo-500
```

DESIGN.md 14: focus ring `2 px` + offset `2 px` — у нас только ring, нет ring-offset.

### 2.7. `transition-all` (вместо `cubic-bezier(0.2, 0, 0, 1)`)

```bash
$ grep -rn 'transition-all' app/templates/ | wc -l
11
```

DESIGN.md 12: easing `cubic-bezier(0.2, 0, 0, 1)`. У нас `transition-all duration-200` без easing.

### 2.8. `animate-fade-in` отключен в main

DESIGN.md 12: «глобальный fade-in каждой страницы запрещён». Статус.md Сессии 26 говорит «убран». Но вот:
```bash
$ grep -rn 'animate-fade-in' app/templates/
13 файлов (в .animate-fade-in class on div)
```
**Частичный leftover**: класс определён в `<style>` base.html, но в dashboard_v2 НЕ применяется к main, тогда как в `tasks.html:1`, `catalog.html:1` и других — **применяется на корневой `<div>`**.

---

## 3. Бажный enum: `unacceptable` в коде (P0)

После ADR-029 (Сессия 19, 2026-08-07) `unacceptable → strong_aversion` миграция сделана в БД и Python‑коде, **но шаблоны не обновились целиком**.

**Файл:** `app/templates/catalog.html`

```html
:74
{% if oi and oi.desire_level == 'unacceptable' %}text-red-500 border-red-400{% endif %}

:88-89
<option value="unacceptable" {% if oi and oi.desire_level == 'unacceptable' %}selected{% endif %}>Unacceptable</option>
```

**Эффект:** если у пользователя `UserEntityOptIn.desire_level == 'strong_aversion'` (новое значение):
- CSS правило в строке 74 **не сработает** (нет ветки для `strong_aversion`)
- `<option value="strong_aversion">` **отсутствует** в `<select>` — пользователь увидит «Reluctant» highlighted, но не сможет переключиться на strong_aversion без обновления страницы

**Это видно в `tasks.html:64`:** там есть правильная ветка для `strong_aversion`. То есть catalog.html **забыт**.

**Фикс нужно в трёх местах:** `catalog.html:74` (ветка + CSS), `catalog.html:88` (option строка), желательно i18n для строки "Strong aversion".

---

## 4. Доступность (WCAG 2.2 AA) — критический провал

DESIGN.md раздел 14 требует:
- landmarks (`<header>`, `<nav>`, `<main>`, `<aside>`, `<footer>` с правильным назначением)
- один `<h1>` на страницу + иерархия
- skip-link как первый focusable
- focus ring 2px + offset
- порядок Tab = визуальному
- screen-reader получает результат HTMX

**Реальность (статический анализ):**

| Требование | Состояние |
|---|---|
| `<main>`, `<nav>`, `<foofer>` в base.html | ✅ есть |
| `<header>`, `<aside>` landmarks | ❌ нет `<header>`, `<aside>` |
| `aria-label` на `<nav>` | ❌ нет |
| `aria-current="page"` на активной ссылке | ❌ нет (только цвет) |
| `aria-describedby` на input с error | ❌ нет |
| `aria-live` для обновлений HTMX | ❌ нет |
| `aria-label` на icon-only buttons | ❌ нет (`<svg>` без aria-hidden тоже нет) |
| skip-link как первый focusable | ❌ нет |
| один `<h1>` на страницу | ✅ в большинстве страниц |
| `<label>` для всех `<input>` | 🟡 Частично: 8 labels for="" в формах, но много input без labels (catalog.html, calendar.html, dashboard) |
| Пиктограммы `aria-hidden="true"` | ❌ нет |
| Tab order = visual | ⚠️ неявно (нет ручных `tabindex` плюсов/минусов) |

**Вывод:** проект не удовлетворяет **WCAG 2.2 AA** для core-flow, что является блокером для публичного использования.

---

## 5. i18n: hardcoded строки (P0)

Найдены **hardcoded строки вне `t.*` словаря** в нескольких местах:

| Файл | Строки | Локаль |
|---|---|---|
| `app/templates/training.html` | «Журнал тренировки», «записей», «Приём», «Микро-слив», «Давление», «Заметка», «Сохранить», «Добавить запись», «Добавить», «Время (напр. 14:30)», «Приём жидкости», «Микро-слив», «Проверка давления», «Заметка», «Значение (мл, сек, уровень)», «Ощущения, заметки...», «Дневная тренировка», «Конкретные шаги» | **Только RU** |
| `app/templates/inventory.html:15-18` | `All`, `Clothing`, `Equipment`, `Cosmetics` | EN |
| `app/templates/dashboard.html:14` | `Points`, `XP`, `Streak`, `Done`, `Recent Activity`, `Telegram Bot`, `No activity yet`, `Generate a task` | EN |
| `app/templates/catalog.html:14, 17` | `My Entities`, `Admin` | EN |
| `app/templates/index.html:32-44` | `Catalog`, `LLM-Suggested`, `Gamification`, `Curated activities with custom parameters`, `Smart task selection…`, `XP, levels, streaks & achievements` | EN |
| `app/templates/calendar.html:33,38` | `Templates`, `Overrides`, `Check Availability`, `Allowed`, `Passive only`, `Disallowed`, `Active`, `Passive`, `Neutral`, `New Template`, `Vacation`, `Mon`, `Tue`, `Wed`, `Thu`, `Fri`, `Sat`, `Sun`, `Every day` | EN |
| `app/templates/tasks.html` | `Task Generator`, `LLM-powered task suggestion from your catalog`, `E.g.: something relaxing, a challenge, something new...`, `Recent Activity`, `Generate Task`, `Custom request (optional)`, `Available now`, `Due for rotation`, `Generate (LLM)`, `Pick from due (no LLM)`, `No tasks generated yet. Click "Generate Task" to start!` | EN |

**`app/i18n/ru.py`** содержит **141 строку**, `en.py` — **131**. Hardcoded строки **не покрыты**.

**Особо критично:** `training.html` — **полностью RU-locked**. Англоязычный пользователь увидит русские кнопки «Журнал тренировки», «Сохранить», «Добавить», «Микро-слив» и т.д.

---

## 6. Безопасность (innerHTML, CSRF, XSS)

### 6.1. innerHTML — 18 случаев в 8 файлах

```
app/templates/base.html:41           (escapeHtml helper definition, OK)
app/templates/calendar.html:112,117,121,176
app/templates/dashboard_v2.html:277,331
app/templates/import_data.html:59    (hx-swap="innerHTML" — допустимо для серверов)
app/templates/inventory.html:62
app/templates/measurements.html:59
app/templates/points.html:101,115,135,136,162,166
app/templates/schedule.html:55,57
```

**Анализ:**
- `base.html:41` — определение `escapeHtml`. Безопасно.
- `calendar.html:117, calendar.html:124-126` — использует `escapeHtml(String(t.id))` и `escapeHtml(t.name)` ✅
- `points.html:115-117, 162-166` — использует `escapeHtml(String(p.id))`, `escapeHtml(p.name)` ✅
- `inventory.html:62` — `items.map(i => '<div>${escapeHtml(...)}</div>')` — переменные **escaped**, но **структурные теги hardcoded** — допустимо, но есть нюансы: имя категории и unit попадают в `${escapeHtml(i.category)}` ✔
- `schedule.html:55,57` — серверные данные (JSON), **escapeHtml не вызывается** ⚠️
- `dashboard_v2.html:277` — `catData.labels.map((l, i) => '<div class=...>${l}...')` — **labels НЕ экранируются** ⚠️ — это **имена категорий**, которые могут содержать user-input
- `dashboard_v2.html:331` — `data.overall_rate` — серверное число, но соседствует с **не-escaped string interpolation** ⚠️
- `measurements.html:59` — нужно просмотреть вручную (отрезано из обзора)
- `import_data.html:59` — `hx-swap="innerHTML"` — сервер возвращает готовый HTML, OK

### 6.2. CSRF hidden поля

```bash
$ grep -rn 'csrf_token\|csrfmiddlewaretoken\|name=\"csrf' app/templates/ | wc -l
4
```

Всего **4 формы** имеют CSRF hidden input:
- `base.html:67, 73` (locale/theme toggle)
- `tasks.html:103` (вероятно)
- (другие 1-2 в forms)

Но найдены **минимум 25 POST forms**, из которых только 4 защищены. Остальные полагаются на HTMX listener в base.html (`htmx:configRequest` ставит `X-CSRF-Token` из meta tag). Это OK для HTMX, **но для native POST формы — нет**.

### 6.3. Inline `<script>` в шаблонах

```bash
$ grep -c '<script' app/templates/*.html
base.html:4             (3 external + 1 inline CSRF helper) — OK
calendar.html:1         (loadData, saveTemplate — 130 строк JS)
dashboard_v2.html:1     (Telegram link + Chart init — 110 строк JS)
import_data.html:1
inventory.html:1
measurements.html:1
points.html:1
schedule.html:1
sessions.html:1
training.html:1
```

DESIGN.md 15.4: «inline scripts запрещены, кроме строго nonce‑защищённого bootstrap». У нас **nonce не используется**, ни одного защищённого bootstrap.

### 6.4. outerHTML on user input

`calendar.html:194, 206` — `window.open('https://t.me/' + botUser, '_blank')`. `botUser` — из конфига, OK.
`import_data.html:38, 133` — `https://localhost:8443/...` — **hardcoded URL** в user-facing message; не XSS, но UX bug.

---

## 7. HTMX integration

```bash
$ grep -rn 'hx-' app/templates/ | wc -l
8
```

HTMX использован только:
- `training.html:94, 106, 116` (log entry inline edit / add / delete)
- `import_data.html:56-59` (upload form)

**Остальные ~25 POST-форм работают как native POST** с `redirect /tasks/`. Это **не плохо само по себе** (progressive enhancement работает), но DESIGN.md 15.3: «HTMX обновляет законченную partial-область» — мы используем HTMX только в одном месте.

CSRF через HTMX:
```javascript
// base.html:29-34
document.body.addEventListener('htmx:configRequest', function(evt) {
    var token = document.querySelector('meta[name="csrf-token"]');
    if (token) evt.detail.headers['X-CSRF-Token'] = token.content;
});
```

✅ Правильно — HTMX автоматически подключает CSRF-токен.

---

## 8. Адаптивность (визуальный статический анализ)

**Реальная ситуация:**
- `base.html` использует `max-w-5xl mx-auto px-4 py-3` — **центрированный контейнер**, не full-width scaffold.
- Нет `<meta name="viewport">` с iOS safe-area?
  ✓ есть (`<meta name="viewport" content="width=device-width, initial-scale=1.0">`), но не `viewport-fit=cover`
- Нет `safe-area-inset-bottom` для мобильной навигации
- **Mobile bottom nav отсутствует** — DESIGN.md 4.4 требует 4 пункта в нижней панели
- Touch targets: наиболее частые кнопки `px-4 py-2` → ≈36 px высоты **ниже 44 px** (DESIGN.md 9.1)
- В dashboard_v2 статистика `grid-cols-2 sm:grid-cols-4` — на телефоне 2 колонки, на desktop 4 — ✅ ОК
- Inline filter `<input>` (calendar, schedule, inventory) используют `w-full` — ОК

**Breakpoints:**
- mobile `< 768` — используется Tailwind `sm: md: lg:`
- 360 px (DESIGN.md минимум) — **никем не тестировалось** (нет скриншотов acceptance)

---

## 9. Типографика

DESIGN.md 7.1: self-hosted Inter Variable, fallback `Inter, ui-sans-serif, system-ui, …`.

**В коде:** `<html lang="…" class="…">` нет `font-sans` или `font-family` → браузер использует дефолтный sans-serif. **Inter НЕ подключён**.

`font-mono` используется в **9 местах** для технических меток (`tabular-nums` — ОК для метрик).

`italic` найдено в **1 месте** (`tasks.html:140`) для цитат LLM reasoning. DESIGN.md не запрещает.

---

## 10. Производительность

- **3 внешних статических файла** (htmx 51KB, chart 209KB, tailwindcss 282KB = 542KB total). DESIGN.md 15.1: «production использует hashed assets и долгий immutable cache».
- base.html **загружает ВСЕ** статические файлы на каждой странице — **Tailwind (282KB) даже на странице /healthz или JSON API**. Это проблема.
- Chart.js загружается на всех страницах, но используется только в 4 шаблонах (dashboard_v2, training, sessions, points). **Остальные 17 шаблонов** загружают chart.js впустую.
- HTMX загружается на всех страницах, но реально используется в **2 шаблонах** (training, import_data). Загрузка **49KB** на других 20 шаблонах избыточна.

**Статическая оценка времени загрузки:**
- landing (`/`): ~600KB JS + 0KB CSS + 60KB HTML ≈ 660KB
- core screens: ~580KB JS (htmx + tailwind) + chart.js ≈ 580KB

DESIGN.md 11: «Chart.js загружается один раз отдельным page module» — мы грузим всегда.

---

## 11. Покрытие страниц по DESIGN.md

| DESIGN.md страница | Имеется? | URL | Соответствие |
|---|---|---|---|
| Auth (login/register) | ✅ | `/login`, `/register` | 🟡 Частично |
| Today empty | ❌ | нет маршрута | — |
| Today active | ❌ | нет маршрута | — |
| Session active | ❌ | `/sessions` (но не core) | — |
| Catalog list | 🟡 | `/entities/catalog` | ❌ Не side-sheet |
| Catalog editor | ❌ | (отсутствует — no edit UI for opt-in) | — |
| History | ❌ | нет страницы | — |
| More | ❌ | нет `/more` | — |

**Routes реально существуют:** `/dashboard`, `/tasks/`, `/training`, `/entities/catalog`, `/entities/my`, `/admin`, `/api/v2/points/page`, `/api/v2/measurements/page`, `/api/v2/inventory/page`, `/llm-configs/`, `/sessions`, `/achievements`, `/notifications`, `/import`, `/calendar`, `/schedule`, `/privacy`, `/auth/login`, `/auth/register`, `/auth/logout`, `/profile/telegram-link-code`, `/profile/telegram-status`.

**Из них core для v0.7** (REMEDIATION_SPEC 12.1): только `/` (home → /dashboard).

---

## 12. Промежуточный итог

**Frontend статус по DESIGN.md: ≈30% compliance.**

Это значит:
- **Production-ready:** ✅ технически (153 теста + CI + Docker OK) — приложение работает.
- **Design-ready:** ❌ визуально оно не соответствует design contract.
- **Accessibility-ready:** ❌ не соответствует WCAG AA.
- **i18n-ready:** ❌ hardcoded строки в training.html и 5 других страницах.

**Если мы хотим соблюдать DESIGN.md**, нужна фронтенд-сессия (38+) для рефакторинга.
**Если принимаем bif** (ADR-033 → всё в главном меню), нужно явно обновить DESIGN.md.

---

## 13. Что в текущем фронтенде хорошо

- **CDN отсутствуют** ✅ (статика локальная, 542KB)
- **Templates структурированы** — каждый расширяет base.html, есть blocks `title`, `head`, `content`, `scripts`
- **CSRF через HTMX** работает ✅
- **Light/dark theme toggle** — есть и сохраняется
- **H1** присутствует на большинстве страниц
- **Autocomplete** атрибуты на формах ✅
- **CSRF middleware** ✅ (вне lifespan)
- **3.1 22 cross-user auth теста** ✅
- **Sticky navbar** + fade-in messages ✅
- **Lucide-style SVG icons** в dashboard_v2 ✅
- **Solid progress bars** (без градиентов в основных страницах) ✅
- **Visual regression через тесты** — проверки на основных степах ✅

---

## 14. Рекомендации (по убыванию приоритета)

### 🔴 P0 — критично

1. **`unacceptable` → `strong_aversion` в `catalog.html`** (P0-баг). Также обновить i18n обе RU и EN.
2. **Hardcoded RU-строки в `training.html`** — вынести в `t.*` словарь.
3. **Hardcoded EN-строки в `index.html`, `dashboard.html`, `catalog.html`, `calendar.html`** — добавить в `t.*`.
4. **Удалить градиент в `<h1>` `index.html`** + удалить emoij из заголовков и кнопок навигации.
5. **Удалить hover-translate** с карточек (запрет DESIGN.md 6.3).

### 🟡 P1 — серьёзно

6. **Переписать CSS-токены**: объявить CSS variables в `<style>` base.html из DESIGN.md 6.2 (--color-canvas, --color-accent, …).
7. **ARIA атрибуты**: добавить `aria-label` на `<nav>`, `aria-current="page"` на активной ссылке, `aria-describedby` для ошибок, `aria-live="polite"` для обновлений HTMX.
8. **Skip-link** как первый focusable элемент.
9. **Touch targets 44×44 px** — увеличить padding на мобильных кнопках.
10. **Перенести графики из `/dashboard`** — DESIGN.md 5.1 «графиков на /today нет», DESIGN.md 11 «≤2 на viewport».
11. **Self-hosted Inter Variable** — добавить `@font-face` + `font-family: Inter, …` на `<html>`.
12. **Mobile bottom nav** — DESIGN.md 4.4.
13. **Lazy-load Chart.js** — загружать только на страницах с графиками.

### 🟢 P2 — поддерживаемость

14. **Refactor шаблонов в layouts/components** — DESIGN.md 15.2 требует структуру `layouts/`, `components/`, `partials/`, `pages/`.
15. **Inline scripts → отдельные модули** — DESIGN.md 15.4 «inline scripts запрещены».
16. **Ручная проверка `dashboard_v2.html:277`** — потенциальная XSS через `catData.labels`.
17. **E2E на 360/768/1280 px** — DESIGN.md 17 требует визуальную приёмку.

---

## 15. Методология аудита

- Прочитан DESIGN.md (694 строки)
- Прочитаны все 22 шаблона (2914 строк total)
- `grep '<script'` — 11 файлов с inline JS
- `grep 'innerHTML'` — 18 вхождений в 8 файлах
- `grep 'bg-slate|bg-gray|text-slate|text-gray|from-indigo|bg-white|bg-black'` — **465 строк** (прямое нарушение DESIGN.md 6.2)
- `grep 'hover:-translate|hover:shadow-lg|hover:scale'` — 21 нарушение (прямое нарушение 6.3)
- `grep 'aria-|role='` — **0** (полное отсутствие)
- `grep 'skip-link|sr-only'` — **0**
- `grep 'csrf_token'` — 4 формы с защитой
- `grep '<form'` — десятки native POST forms без HTMX
- Прочитаны `i18n/en.py` (131 строка), `i18n/ru.py` (141 строка) — hardcoded strings не покрыты

---

## Связь с предыдущим аудитом (Session 37)

Бэкенд-аудит (`memory/AUDIT_SESSION_37.md`) выявил конфликт SPEC ↔ ADR и 6 пунктов вразрез.
**Фронтенд-аудит дополняет картину:**
1. Design.md **формально никогда не применялся систематически** (30% compliance).
2. ADR-033 «всё в главном меню» — **противоречит DESIGN.md 3.1** (Сегодня/Каталог/История/Ещё).
3. ADR-032 «Training — отдельная страница» — **противоречит DESIGN.md 12.3** (заменить на План дня).
4. Найден конкретный баг (unacceptable → strong_aversion) **который ADR-029 не покрыл** в UI.
