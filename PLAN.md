# План работ — Practice Loop

> **Правила файла:** только дополняется и корректируется (статус → ✅). Строки не удаляются.
> Новые шаги добавляются в конец списка. Читаемый для владельца, кратко, без тех. деталей.
> Технические детали — в `docs/memory-rfc/STAGE_PLAN.md`; продукты — в `ROADMAP.md` и `PRODUCT.md`.

> **Правило проверок (сессия 131):** полный `pytest tests/` (~9 мин) — только перед деплоем/релизом. При правке фронта/шаблонов — таргетный набор: `test_shell_v2 test_design_v2_9b test_design_v2_9c test_icon_pack test_audit_s57 test_phase3_task_ui test_locktimer_device test_media_verification test_dnd_diets_uploads` (~2 мин, 127 тестов). При правке конкретного модуля — его тест-файлы.
> **Browser-тесты НЕ скипать (сессия 131, решение владельца):** playwright установлен (node `@playwright/test` 1.62 + браузеры chromium/firefox/webkit в `~/.cache/ms-playwright`; python-пакет — по требованию). Полноценный набор — `npx playwright test` (5 проектов: desktop/tablet/mobile chromium, firefox, webkit; smoke/a11y/usability против `E2E_BASE_URL`, default `http://127.0.0.1:8000` — живой прод). Старый pytest-e2e `tests/e2e/test_browser_smoke.py` — тоже не скипать (python playwright; `pip install playwright`). Файлы настроек (package.json, playwright.config.ts, tests/browser/, tools/browser/, docs/BROWSER_TESTING.md) — часть проекта, node_modules/ в git не заносится.

---

## Актуальный план (Сессия 131)

### Выполнено

- [x] **Шаг 1 — Безопасность (Gate A остаток)** — Сессия 119. XSS-граница в validate таймера закрыта, readiness не раскрывает детали ошибки, добавлены базовые security-заголовки (HSTS/nosniff/frame/referrer/permissions + CSP в режиме наблюдения). 743/743 ✅
- [x] **Шаг 2 — LLM и медиа границы** — Сессия 119. Недельный план задач строго валидируется (даты, уникальность, полнота, атомарность); привязка медиа к объектам проверяет владельца цели (10 типов); версия приложения — из одного источника. 755/755 ✅
- [x] **Шаг 3 — Память (M5)** — Сессия 120. Legacy-память заморожена (v1 → архив), активная память — Memory v2 (ADR-068). CI проверка памяти стала обязательной. В benchmark добавлена метрика impact-recall (находят ли все затронутые файлы/тесты/миграции — задел под code-graph пилот). 758/758 ✅
- [x] **Шаг 4 — Полировка личного таймера** — Сессия 120. Штрафы честно приходят в HTTP: skip задачи применяет политику правила (points/add_time), позднее закрытие окна — политику late_close; API возвращает JSON с реальным результатом штрафа, UI показывает «Штраф применён: …» вместо «Penalty may apply». Параметры Omniroute (host/key из .env) внедрены в портал: seed-пресет Omniroute активен по умолчанию с шифрованием ключа. 767/767 ✅
- [x] **Шаг 5 — Стабилизация + икон-пак** — Сессия 120. **PracticeLoop icon pack интегрирован**: sprite + favicon в static, макрос icon() для Jinja, все emoji/inline-SVG в навигации и ключевых экранах заменены, JS-хелпер plIcon (без innerHTML), тест сверки имён со спрайтом, обязательство «иконки только из пакета» в AGENTS.md/DESIGN.md. **Gate B остаток**: медиа обрабатываются в thread pool с защитой от decompression bomb (P2-2); транзакции — единый владелец: новые роутеры без db.commit() + boundary-тест (P1-5); браузерный smoke-тест на Playwright (login → дашборд → таймер) + CI job (P1-4). 776/776 ✅
- [x] **Шаг 6 — LLM-инструменты личного контура** — Сессия 120. **Библиотека промптов** (/llm/prompts): реестр 8 типовых системных промптов (задачи/тренировки/диеты) с RU/EN-описаниями и «создать шаблон из этого». **Промпт-шаблоны** (/llm/templates): пользователь создаёт приватный шаблон с переменными {{var}} и схемой параметров (ADR-041) — LLM генерирует текстовый ответ или выбирает задачу из каталога; история запусков, usage. **Приватная база знаний — служебная**: свои данные (история, диеты, тренировки) автоиндексируются в векторный индекс (Qdrant + Omniroute) и подмешиваются в контекст генерации; недоступна пользователю напрямую. 800/800 ✅

### Впереди (следующие 5 шагов)

> **Планирование покрывает весь личный контур**, а не только разрабатываемые сейчас модули:
> будущие модули из `examples/New_doc` (Today projection, Media Vault, Consent/Discretion,
> Chastity device/comfort, Check-in/Agreement, Aftercare, Personal Care, Medication, Health/Sleep/
> Labs, Cycle, Personal Insights, Social community/verification, D/s capability grants) учтены в
> икон-паке, в `ROADMAP.md` и в планах ниже; работа с фронтом всегда идёт через PracticeLoop
> icon pack (`design/icons/`, AGENTS.md/DESIGN.md).

- [x] **Шаг 7 — LLM-верификация медиа** — Сессия 121. **Vision через Omniroute** (подтверждена `openrouter/openai/gpt-4o-mini`): `call_llm` поддерживает image parts (data URL); движок `app/llm/pipeline/media_verify.py` — два типа проверки: `code_match` (LLM сравнивает код на фото с ожидаемым; при активном VerificationChallenge LLM читает код, сервер сверяет HMAC — сервер авторитет) и `chastity_closed` (оценка закрыт ли замок); verdict/confidence/reasoning, plaintext кода не хранится (только HMAC); таблица `media_verification_results` (миграция 037). API: `POST /api/v2/media/{id}/verify` (JSON, `auto_consume_challenge` — потребление challenge только по явному запросу), `GET .../verification-results`, страница `/llm/verify` (выбор медиа + форма + история). 825/825 ✅ (+25), ruff ✅ (ADR-075).
- [x] **Шаг 8 — Второй эшелон личного контура** — Сессия 122. **Device inventory для таймера**: `lock_sessions.device_id` → inventory_items (миграция 038); устройство выбирается в настройках черновика / при создании сессии, показывается чипом в шапке и на овервью; авто-статусы: при старте device → `in_use`, при safety-stop → `available`; чужое/архивное устройство отклоняется; unbind через явный sentinel `__none__` (FastAPI мапит пустую форму в default). **Честный UI**: оставшиеся emoji-иконки заменены на икон-пак по всем шаблонам (dashboard/achievements/diets/notifications/tasks/training/locktimer/login/social) и JS (plIcon DOM API); тест запрещает emoji-иконки в шаблонах и JS (исключение — content-значения social verification). **Personal Telegram-команды**: `/lock` (статус активной сессии: с, до, остаток, следующее окно, задачи), `/lock_start` (старт последнего черновика с подтверждением), `/lock_stop` (safety-stop с подтверждением), inline-кнопки, help обновлён. 847/847 ✅ (+22), ruff ✅ (ADR-076).
- [x] **Шаг 8 (деплой)** — Сессия 122. **Задеплоено на прод** (docker compose up -d --build): миграции 036/037/038 применены (Шаги 6–8 live), health 200. Прод-смоук пройден: регистрация → логин → дашборд; устройство создано в инвентаре; сессия с устройством (чип на детали), старт → `in_use`, safety-stop → `available` (проверено в БД); страницы `/llm/prompts`, `/llm/templates`, `/llm/verify`, `/locktimer*`, `/api/v2/*` — 200; TG_BOT_TOKEN задан (команды /lock live). Найден и исправлен баг деплоя: миграция 038 была записана с экранированными кавычками (`\"\"\"`) — alembic падал на старте; переписана, py_compile + single head, контейнер поднялся.
- [ ] **Шаг 9 — Редизайн фронта по DESIGN_V2.md** — «Тёмный архив»: новый UI-контракт (темы, типографика, компоненты, навигация) поверх существующих экранов, с соблюдением обязательства по икон-паку. Запланирован по решению владельца.
    - ✅ **9a — Фундамент + shell (сессия 128)**: токены DESIGN_V2 §4 (canvas/surface/border/text/accent + доменные оттенки, legacy-алиасы `--color-*` сохранены), self-hosted шрифты (Source Serif 4 Variable + IBM Plex Mono, кириллица+латиница, 21 файл), сигил в shell; sidebar 72/272px с группами §7 и feature flags, utility bar 64px, mobile top bar 56px + полноэкранный sheet (вместо глобального bottom nav); dashboard-шапка по §9 (дата + ритуальная формула, токены в стат-картах/XP-баре); i18n shell-ключи EN/RU; тесты test_shell_v2 (8) + правки test_audit_s57. ADR-077.
    - ✅ **9a — деплой (сессия 128)**: `docker compose up -d --build`, health 200. Прод-smoke: `scripts/prod_smoke.sh` — SMOKE_OK (регистрация/логин, device flow in_use→available, страницы Шагов 6–8, точки/инвентарь). Проверка shell на живом контуре: sidebar (группы «Now/Personal/Data/System», 47 nav-пунктов), mobile sheet + menu, sigil, `pl-display` (serif-дата), aria-current — все маркеры в HTML; static: sigil/fonts/sprite 200; анонимная страница без shell; старый bottom nav отсутствует. Тестовые пользователи вычищены (4).
    - ✅ **9a — фронт-фикс «верстка поехала» (сессия 131)**: на дашборде контент уходил под sidebar — `<main>`/`<footer>` были вне `.pl-shell` (margin-left 72px имел только shell); фикс: `body:has(.pl-sidebar) { padding-left: 72px/272px }` (desktop), все дети body смещаются синхронно. Вторая причина: `dark:`-вариант Tailwind v4 browser-build следовал `prefers-color-scheme` ОС, а не классу `.dark` на `<html>` → цвета «плыли» при несовпадении темы приложения и ОС; фикс: `@custom-variant dark (&:where(.dark, .dark *))` в `<style type="text/tailwindcss">`. 873/873 ✅ (+3 регрессионных теста в test_shell_v2), задеплоено, SMOKE_OK.
    - ✅ **9a — фронт-фикс #2: shell на весь экран + мёртвый sidebar (сессия 131)**: (1) `.pl-shell` имел `min-height: 100vh` (задумка флекс-колонки с main внутри), но main/footer снаружи → пустой блок во весь экран, дашборд под ним; убран min-height/flex у shell (footer-якорь держит body-флекс). (2) Кнопка раскрытия sidebar была `display:none` в свёрнутом состоянии → полоска 72px мёртвая, раскрыть нельзя; теперь кнопка всегда видна (chevron поворачивается на 180° в свёрнутом, aria-label из i18n data-атрибутов). (3) Скролбар `.pl-sidebar-nav` в свёрнутом виде скрыт (`scrollbar-width: none`), в раскрытом — тонкий стилизованный. 49/49 таргетных ✅ (+3/переписаны в test_shell_v2), задеплоено, живые проверки: дашборд 200, правила в HTML.
    - ✅ **9a — фронт-фикс #3: иконки свёрнутого рейла уезжали за левый край (сессия 131)**: лейблы навигации скрывались только `opacity: 0`, но оставались в flex-строке → строка «иконка+невидимый лейбл» центрировалась и переполняла 72px, иконка уходила влево и обрезалась `overflow:hidden`; фикс: `body:not(.pl-sidebar-open) .pl-nav-label { display: none }` (лейбл полностью уходит из лейаута). +1 регрессионный тест, задеплоено.
    - ✅ **9a — фронт-фиксы по browser-тестам (сессия 131)**: (1) **баг «Chart is not defined»** — пре-`{% extends %}` скрипты dashboard_v2.html (page-i18n + dashboard.js) рендерились в самое начало документа ДО `chart.umd.min.js` → графики дашборда не рисовались; перенесены в `{% block head %}` (после chart.umd). (2) `--text-muted` не проходил WCAG 4.5:1 на surface (4.16 dark / 3.47 light) → тёмная `#96877b` (4.95/4.55), светлая `#75675c` (4.65, остаётся светлее text-secondary). Найдено browser-smoke + axe на живом проде.
    - ✅ **9a — остаточный долг a11y закрыт (сессия 131, в рамках 9d)**: axe-тест `@a11y` desktop-chromium **зелёный** (dashboard/tasks/catalog/timer). Что починено: новый токен **`--accent-text`** (accent сам не проходит 4.5:1 как текст на тёмном: #743a37 light / #c9897f dark; класс `.pl-accent-text` и `.pl-accent-soft` используют его); тёмный `--accent` чуть затемнён `#a95f58 → #a25a53` (кнопки accent-bg + белый текст 4.40 → 4.76); индиго-ссылки получили dark-варианты (`text-indigo-600 dark:text-indigo-400`); aria-label добавлены фильтр-селектам /tasks и `desire_level` /entities/catalog (select-name, critical); density-переключатель задач — accent-text. `prototype.spec.ts` скипается осознанно (нужен DESIGN_PROTOTYPE_URL).
    - ✅ **9b — Active Timer + Tasks (сессия 129)**: hero активной сессии — крупный serif-таймер (pl-display 6xl/7xl, tabular), честная строка режима (duration_from_start/infinite локализованы) + устройство + tz, диапазон started→end с потолком (cap, max_end_at) и merge gap, safety stop — первый и самый крупный CTA; draft без hero (настройки остаются); токен-рестайл session_detail/overview (96+70 замен на pl-surface/токены, accent-кнопки, статусы на success/warning/danger/info); Tasks — переключатель плотности compact/comfortable (localStorage, CSS-классы, JS в tasks.js — без inline-скриптов по audit), due-строка (scheduled_at), токен-рестайл rows. 863/863 ✅ (+8 test_design_v2_9b). ADR-078.
    - ✅ **9c — Inventory / Media patterns (сессия 130)**: новая страница **Media Vault `/media`** (SSR-галерея по §10/§11: плитки с изображением ≥160×120 object-cover, подпись «дата · тип · provenance», verified-бейдж из `media_verification_results` (match/mismatch/unclear + тип + уверенность), retention (приватно/архив), state-чипы staged/ready/archived, upload-форма (staged), пустое состояние); nav в sidebar → `/media` (был JSON-эндпоинт); i18n-ключи переименованы в `mvt_*` (коллизия с `mv_title` страницы верификации); Inventory — изображение 160×120 (w-40 aspect-[4/3]) + placeholder-метка, токен-бейджи категорий/статусов, токен-рестайл оболочки; 869/869 ✅ (+6 test_design_v2_9c). ADR-079.
    - ✅ **9d — остальные Personal-разделы (сессия 131)**: токен-пасс 25 шаблонов (training, calendar, points, llm_configs, prompt_*, import_data, diets, measurements, media_verify, my_entities, schedule, admin, catalog, locations, index, achievements, sessions, notifications, privacy, register/login, body_parts, dashboard_v2 (быстрый-линки внизу)) — legacy `bg-white/slate-*`, `text-slate-*`, `border/divide-slate-*`, индиго-кнопки → `pl-surface/-soft`, токены текста/границ, `pl-accent-bg` (индиго-кнопки), focus-ring → `--focus`; осиротевшие `dark:*` после замен вычищены; намеренно оставлены: тёмный код-блок import_data, семантические цветные чипы/алерты (indigo/amber/emerald), градиенты. Browser-набор desktop-chromium: **5/5 ✅** (smoke, a11y, usability×3) + 1 осознанный skip (prototype). 113/113 таргетных pytest ✅.
    - [ ] **9e — Social domain tone + customization/discretion** (§13, §16: холодный сине-серый тон, настройка блоков дашборда, discretion-режим)
    - [ ] **9f — Visual QA** 360×800 / 768×1024 / 1280×800 / 1440×900 + DoD (§20)
- [ ] **Шаг 10 — Mobile Foundation (M4)** — по ROADMAP.md: JSON-first API для всех ключевых модулей (уже есть для media/verification/prompt-templates/locktimer), bearer-auth токены, push-канал, адаптивный контур для будущего мобильного клиента.
- [ ] **Шаг 11 — M3 Personal Suite** — журналы и Care/Health foundation из `examples/New_doc`: Media Vault (унификация медиа-галереи), Aftercare, Personal Care, Medication, Health/Sleep/Labs, Cycle — по мере приоритизации владельцем.
- [ ] **Шаг 12 — Social: следующий эшелон** — после стабилизации Personal: S8 keyholder-контур, публичный доступ/витрина, community — по решению владельца (сейчас Social закрыт для внешних).

### Долги (зафиксированы, не удаляются)

- **Иконки для social encourage** (thumbs-up/fire/party/muscle) — в пакете нет точных соответствий, а значения хранятся в БД как контент; остались emoji. Добавить иконки в `design/icons/svg/` и заменить, когда понадобится.
- **Остальные явные db.commit() в legacy-роутерах** (28 файлов в allowlist boundary-теста) — осознанный долг; новые роутеры обязаны коммитить только в сервисах.
- **OCR-верификация (Q13)** — отложена; медиа-верификация остаётся HMAC (Шаг 7 добавил LLM-оценку фото через vision — `code_match`/`chastity_closed`; OCR как распознавание текста отдельно не реализовано).
- **Редизайн по DESIGN_V2.md** — запланирован (Шаг 9): целевой UI-контракт «Тёмный архив» уже готов в `DESIGN_V2.md` + прототип в `design/prototype/`; ждёт решения владельца по приоритету относительно Mobile Foundation.
- **Иконки flame/target/star для streak/goal** — в пакете нет точных соответствий (🔥/🎯 заменены на history/chart/flag); при доработке икон-пака добавить flame/target/star и заменить.
- **Reaction-иконки social (thumbs-up/fire/party/muscle)** — остались emoji как content-значения (БД); добавить в икон-пак, когда потребуется.
- **Mobile Foundation (M4)** — запланирован как Шаг 10; сейчас API уже JSON-first для ключевых модулей (media, verification, prompt-templates, locktimer commands); останется bearer-auth, push и полное покрытие модулей.
- **OCR-верификация (Q13)** — LLM-оценка фото есть (vision); OCR как распознавание кода в общем виде остаётся опцией на будущее.
- **Смоук-скрипт прод-деплоя** — полезно вынести `/tmp/prod_smoke_s122.sh` в `scripts/` (с параметризацией BASE_URL) для повторного использования при следующих деплоях.
- **Полная CSP (enforcing)** — сейчас report-only; включение после выноса inline JS в модули и сборки Tailwind.

---

## Исторический план (завершённые серии)

### Серии 114–118 — Память v2 и векторный пилот

- [x] **Этап 1 — Bootstrap** — детерминированный context pack + sentinel из текущего HEAD (memoryctl bootstrap).
- [x] **Этап 2 — Benchmark + пилот** — 12 задач, baseline recall@5 0.26; решение по пилотам (ADR-069); реализация; реальный A/B через Omniroute: **recall@5 0.24 → 0.37, MRR 0.356 → 0.496** → пилот принят (shadow/assist).
- [x] **Этап 3 — Preflight** — sentinel/impact/launcher/SKILL/pre-commit; память стала частью обязательного workflow.

### Серии 108–113 — Аудит и стабилизация

- [x] **Аудит проекта (Сессия 111)** — полный review → `docs/audits/PROJECT_REVIEW_2026-08-13.md` (2 P0, 7 P1, 4 P2).
- [x] **P0-блокеры (Сессия 113)** — приватные файлы больше не раздаются публично; CHALLENGE_HMAC_KEY обязателен в production.
- [x] **P2-4 (Сессия 112)** — denylist/allowlist памяти уточнены, lint 0 предупреждений.

### Серии 73–107 — Social, Timer UI, рефакторинг, время

- [x] **Platform Social S0–S7 (73–76)** — профили, отношения, публикации, верификация, модерация, адаптеры; hardening + privacy audit.
- [x] **Timer UI (69–72)** — интерактивные действия, countdown, шаблоны, номерные бирки (seal).
- [x] **Refactoring 1–7 (82–88)** — декомпозиция крупных файлов (execution, import_data, references, points_v2, social, pipeline) с сохранением контрактов.
- [x] **Серии по времени (92–101)** — всё в UTC, отображение/границы суток в tz устройства, графики по device-дню, фоновые задачи в конфиг-tz.

### Серии 58–62 — Новая модель активностей

- [x] Категории (16), статус-машина 11 состояний + аудит, типизированные параметры, title-генератор, справочники (зоны тела, места, категории инвентаря), сессии-accepted, честные штрафы.

### Ранние серии 1–57 — Фундамент, фазы 1–11, каталог, LLM, геймификация, диеты, точки

- [x] Phase 1–11 полностью: фундамент, каталог, LLM-пайплайн, UI/геймификация, Training, Points v2/замеры/инвентарь, импорт/экспорт/графики, календарь, штрафы, Telegram-бот v2, автоанализ.
- [x] Внешний аудит P0 (Сессия 55): зависимости, CSRF, safety-gate LLM, целостность, cross-user.
- [x] Диеты v2/v3 (56): история оценок, синергия с тренировками, inline-редактирование, фото.
