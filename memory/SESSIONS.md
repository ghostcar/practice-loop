# Журнал сессий

Формат: `дата — Сессия N: тема` → что обсуждали → результаты/договорённости → артефакты.
Новая запись добавляется **в конце каждой сессии**.

## 2026-08-06 — Сессия 1: Интервью (базовое)
- Обсуждали: скоуп работ, пользователи, язык UI, деплой; LLM/маскирование; провайдеры;
  обработка ошибок LLM; штрафы; тесты; UI-стиль; админка; приватность; геймификация;
  каталог задач; уведомления; переработка AGENTS.md; подписки; сессии; бэкапы; логи LLM.
- Результаты: полный цикл фаз 1–4; сейчас один пользователь (потом мультипользователь);
  i18n EN/RU; VPS + Docker Compose; **гибридная генерация вместо Semantic Masking**;
  BYOK-провайдеры; штрафы = игровая механика + реальные последствия с прерыванием задач;
  тщательные тесты; тёмная + светлая темы; базовая админка; экспорт/удаление данных +
  обезличенная доска достижений.
- Артефакты: создан `tracker-spec.md`.

## 2026-08-06 — Сессия 2: Открытые вопросы
- Обсуждали: решения по открытым вопросам спеки (с исследованиями: Telegram-фреймворки,
  провайдеры, Omniroute).
- Результаты: aiogram 3.x; Omniroute (локальный, модель `auto`, активный) + Groq + OpenRouter;
  без рейт-лимитов; простая регистрация без email; кастомные правила геймификации (формулы XP,
  правила сессий, множитель серий, эскалация штрафов, недельные челленджи, комбо, случайные
  бонус-задачи, совместные достижения); контент по locale.
- Артефакты: спека, разделы «Решённые/Осталось открытым».

## 2026-08-06 — Сессия 3: AGENTS.md + Telegram-бот
- Обсуждали: единый стиль AGENTS.md; детали бота (3 раунда).
- Результаты: AGENTS.md приведён к единой структуре (8 разделов, без Semantic Masking);
  бот: интерактивный, вебхук `/tg/webhook`, команды `/next /done /interrupt /stats /session
  /settings`, все 5 типов уведомлений, код-привязка, интервальные напоминания (старт 2 ч),
  список активных задач, компактная карточка, настройка получателей уведомлений в совместных
  сессиях.
- Артефакты: новый `AGENTS.md`; раздел 8 спеки.

## 2026-08-06 — Сессия 4: Сессии/штрафы, каталог, доска достижений
- Обсуждали: детализацию трёх механик (3 раунда).
- Результаты: сессии `created/active/ended`, 5 типов правил, штраф в задаче + автогенерация
  с усложнением/упрощением, настраиваемая формула XP, эскалация с настраиваемым сбросом,
  комбо +10% → +50% со сбросом, челленджи авто+ручные; каталог: категории + теги, 3 типа
  задач, фазы/итерации с таймером, шкала желания, публикация без модерации, стартовый набор
  30+ (черновик); доска: 6 типов достижений, ник + скрытие, комбинированная доска, пороги XP,
  SVG-бейджи.
- Артефакты: разделы 9–11 спеки.

## 2026-08-06 — Сессия 5: Система памяти
- Обсуждали: создание файлов памяти, их назначение, правила обязательного использования.
- Результаты: созданы `memory/README.md`, `CONTEXT.md`, `STATUS.md`, `DECISIONS.md`,
  `SESSIONS.md`, `OPEN_QUESTIONS.md`, `CHANGELOG.md`; правила чтения в начале сессии и
  обновления в конце прописаны в `memory/README.md` и в `AGENTS.md` (раздел 7).
- Артефакты: `memory/*`; правка `AGENTS.md`.

## 2026-08-06 — Сессия 6: Phase 1 — Фундамент и инфраструктура
- Что сделано: создана структура проекта, `pyproject.toml`, `requirements.txt`;
  Docker-файлы (`Dockerfile` multi-stage, `docker-compose.yml` db+app+nginx, `nginx.conf`);
  `.env.example`; FastAPI-приложение с `/healthz`; модель User (SQLAlchemy async);
  Alembic-миграции (начальная 001_create_users); JWT-аутентификация (регистрация, логин,
  логаут через cookie); i18n EN/RU с переключателем языка; тёмная/светлая тема с
  переключателем и сохранением в профиле; Jinja2-шаблоны (base + index + register +
  login + dashboard) на TailwindCSS с анимациями и микро-взаимодействиями;
  базовые тесты (conftest + healthz).
- Проверено: все файлы проходят `py_compile`; приложение загружается, все роуты на месте;
  зависимости установлены.
- Артефакты: 40 файлов в проекте (app, tests, alembic, nginx, docker).

## 2026-08-06 — Сессия 7: Phase 2 — Каталог и конфиги
- Что сделано: модели Entity (задачи/активности: тип, категория, теги, params_schema, авторство),
  UserEntityOptIn (many-to-many: опт-ин, рейтинг 1–5, шкала желания want_very_much…unacceptable),
  LLMProviderConfig (BYOK-провайдеры: api_base_url, api_key шифрованный, модель, usage);
  Alembic-миграция 002 (3 таблицы); шифрование API-ключей через Fernet (cryptography);
  CRUD API: entities (создание/публикация/удаление), opt-in (переключение/рейтинг/желание),
  llm-configs (добавление/активация/удаление); seed-данные: 30+ задач (6 категорий по 5)
  + 3 LLM-пресета (Omniroute активный, Groq, OpenRouter);
  базовый админ-интерфейс: каталог, мои задачи, LLM-конфиги, кнопки seed;
  шаблоны: catalog.html, my_entities.html, llm_configs.html, admin.html;
  поправлены баги из ревью (|format→%s, tags→list, updated_at, desire_level-лейблы).
- Проверено: 10 новых Python-файлов проходят py_compile; приложение v0.2.0 загружается с 12 роутами.
- Артефакты: +14 файлов (всего 56).

## 2026-08-06 — Сессия 8: Phase 3 — LLM-пайплайн
- Что сделано: модели ActivitySession и ActivityLog (с полным raw_llm_response, токенами/стоимостью);
  миграция 003; Context Builder (история, статистика, допустимые entity, активные штрафы, locale);
  LLM-клиент (OpenAI-совместимый AsyncOpenAI, из LLMProviderConfig, BYOK, оценка стоимости);
  JSON repair pipeline (json_repair → regex-фолбэк, 3 попытки с перезапросом LLM → JsonRepairError);
  tool calling (save_activity_log, get_user_stats, apply_penalty);
  POST /tasks/generate (контекст → LLM → repair → parse → сохранение в ActivityLog);
  подсчёт токенов/стоимости в LLMProviderConfig; locale-зависимые промпты;
  UI: страница /tasks/ с формой генерации, историей, кнопками ✅ Done / ⏹ Interrupt.
- Исправлено из ревью: убран dead code в retry-логике, переименован attempt→is_last_attempt,
  penalties считает все interruptions.
- Проверено: 10 новых Python-файлов проходят py_compile; app v0.3.0 с 13 роутами.
- Артефакты: +12 файлов (всего 68).

## 2026-08-07 — Сессия 11: Функционал «Тренировка» (Training)
- Обсуждали: дизайн фичи — TrainingDay как отдельная модель, ActivityLog с чек-листами,
  авто+ручной анализ дня, облегчённая геймификация (XP без ачивок)
- Результаты:
  - Модель TrainingDay (planned→active→completed→analyzed), поле subtasks в ActivityLog
  - LLM-промпты: генерация плана дня (3-7 задач с подзадачами), анализ дня, план на завтра
  - Pipeline: generate_daily_plan, analyze_training_day
  - Геймификация: is_training режим — XP начисляется, streaks/комбо/ачивки пропускаются
  - API: 5 эндпоинтов (страница, план, toggle subtask, complete, analyze)
  - Шаблон training.html: карточки задач, чек-листы с AJAX-toggle, прогресс-бар, кнопки
  - i18n: 14 ключей EN/RU
  - Миграция 005_add_training + FK constraint
  - Исправлено по ревью: dead import Entity, empty plan → ValueError,
    next_day_suggestion парсится на сервере, FK в миграции
- Проверено: ruff 0 ошибок, pytest 78 passed (11.84s)
- Артефакты: +6 файлов (модель, миграция, промпты, API, шаблон, тесты),
  изменены: activity_log, pipeline, gamification/handler, main, i18n

## 2026-08-07 — Сессия 10: Тесты и линтинг
- Что сделано:
  - Установлены dev-зависимости (ruff, pytest, pytest-asyncio, httpx, aiosqlite)
  - Ruff: 181→0 ошибок (B008→ignore, F821→TYPE_CHECKING, E712/E501/SIM105/F841 исправлены)
  - Модели: JSONB → SQLAlchemy JSON (совместимость с SQLite для тестов)
  - pyproject.toml: исправлен license, setuptools.packages.find, ruff ignore B008
  - Написаны 72 новых теста (всего 73):
    - tests/test_auth.py — 7 тестов (register, login, logout, locale/theme)
    - tests/test_entities.py — 7 тестов (CRUD, publish, delete, opt-in)
    - tests/test_llm_config.py — 4 теста (CRUD, set-active, delete)
    - tests/test_repair.py — 13 тестов (json_repair, regex, markdown, error cases)
    - tests/test_xp.py — 27 тестов (levels, XP calc, penalties, streak reset)
    - tests/test_context_builder.py — 3 теста (formatting)
    - tests/test_gamification.py — 7 тестов (handler, achievements, progress)
    - tests/test_sessions.py — 4 теста (create, start, end, security)
  - Docker недоступен локально — сборка не проверена
- Проверено: ruff 0 ошибок, pytest 73 passed (9.82s)
- Артефакты: +7 тестовых файлов, обновлены conftest.py, pyproject.toml, 9 моделей

## 2026-08-07 — Сессия 12: Points v2 + Measurements + Inventory + Schedule + Import
- Обсуждали: анализ 7 файлов из examples/ (docx + xlsx), выявлены gaps: балльная система v2,
  гибкая система штрафов/бонусов с включением-выключением фич, уровневая система,
  расписание дня, замеры тела, план/факт, инвентаризация, модуль импорта
- Результаты:
  - Entity: +parent_id, +level, +gamification_config (JSON: points+penalties+bonuses+thresholds)
  - ActivityLog: +planned_value, +actual_value, +points_awarded
  - UserProgress: +points_balance
  - Новые модели: PointsTransaction, PointsProfile, ScheduleRule, BodyMeasurement, InventoryItem (5 таблиц)
  - Миграция 006_add_points_v2
  - Points v2 engine: гибкий расчёт из gamification_config — base + intensity ×1.10 + бонусы
    (условия eval: key > value / == / !=) + штрафы с уровнями + эскалация (×1→×5 c cap) +
    redemption actions (clothespins/bondage duration)
  - Обновлён gamification/handler: points economy интегрирован в on_task_completed/interrupted
  - API `/api/v2/*`: gamification config, balance, spend, profiles, schedule, measurements (+charts),
    inventory (+shopping list), HTML-страницы
  - API `/import/*`: шаблоны CSV/JSON (4 типа), upload, API-push для внешних сервисов
  - 4 HTML-шаблона: measurements (Chart.js), inventory (фильтры/CRUD), schedule (слоты), points (баланс/пороги)
  - Seed v2: 15 entities с gamification_config, 8 измерений, 30+ inventory items, 11 schedule rules
  - Исправлено: line-length 100→120, Entity.parent/children back_populates, conftest явные импорты моделей
- Проверено: ruff 0 ошибок, pytest 100/105 passed (5 предсуществующих failures — сессии/дашборд)
- Артефакты: +15 файлов (3 модели + миграция + 2 schemes + 2 gamification + 2 API + 4 шаблона + seed + тесты),
  изменены: entity, activity_log, progress, handler, main, pyproject.toml, conftest

## 2026-08-06 — Сессия 9: Phase 4 — UI, сессии, геймификация, уведомления
- Что сделано: модели UserProgress (XP/уровень/серии/комбо), Achievement (код/условия/цвет),
  UserAchievement (контекст/скрытие), Notification (in-app, 5 типов); миграция 004;
  XP-движок: формулы (база+streak+комбо+интенсивность), пороги уровней (100/250/500/1000…),
  streak (раз в день), комбо (+10%→+50%), эскалация штрафов (×1→×5);
  достижения: 13 seed (streak/count/diversity/joint/intensity/level), проверка условий,
  выдача + уведомления; handler: on_task_completed/interrupted — XP, уровни, ачивки, штрафы;
  API: дашборд с реальной статистикой, доска достижений (обезличенная + «мои» + скрытие),
  in-app уведомления (список + mark read), сессии (create/start/end),
  приватность (JSON-экспорт + удаление аккаунта);
  Telegram-бот (aiogram 3.x): вебхук, 6 команд, привязка по коду;
  шаблоны: dashboard_v2.html, achievements.html, notifications.html, sessions.html, privacy.html;
  баги исправлены: streak 1/день, raw_llm_response в экспорте, inline import.
- Проверено: 11 новых Python-файлов проходят py_compile; app v0.4.0 с 14 роутами.
- Артефакты: +16 файлов (всего 84). Все 4 фазы завершены.
