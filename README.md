# Practice Loop

Consensual Adult Activity & LLM Tracker — веб-приложение для отслеживания и управления активностями с геймификацией, тренировками и LLM-подбором задач.

## Возможности

- 🎯 **Гибкая балльная система** — base points, бонусы, штрафы с эскалацией и искуплением
- 🏋️ **Тренировки** — дневной план от LLM, чек-лист подзадач, анализ дня
- 📏 **Замеры тела** — вес, объёмы с графиками Chart.js
- 📦 **Инвентаризация** — учёт оборудования/одежды/косметики, списки покупок
- 📅 **Расписание дня** — обязательные/дополнительные задания по времени
- 📊 **Графики** — активность, баланс баллов, XP, замеры
- 🤖 **LLM-подбор задач** — OpenAI-совместимые провайдеры (Omniroute, Groq, OpenRouter)
- 🏆 **Достижения и уровни** — XP, streak, доска достижений
- 🌐 **i18n** — EN/RU, тёмная/светлая тема
- 🔒 **Приватность** — экспорт/удаление данных, JWT-аутентификация

## Быстрый старт

### Development (SQLite)

```bash
pip install -r requirements.txt
cp .env.example .env
# отредактируй .env: DATABASE_URL=sqlite+aiosqlite:///./tracker.db
python3 -c "import uvicorn; from app.main import app; uvicorn.run(app, port=8000)"
```

Открой http://localhost:8000, зарегистрируйся.

### Production (Docker + PostgreSQL + HTTPS)

```bash
cp .env.example .env
# заполни JWT_SECRET_KEY и POSTGRES_PASSWORD в .env
mkdir -p nginx/ssl
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout nginx/ssl/privkey.pem -out nginx/ssl/fullchain.pem \
  -subj "/CN=localhost"
docker compose up -d
```

Открой https://localhost:8443 (HTTP на 8080 редиректит на HTTPS).

## API (v2)

| Endpoint | Описание |
|---|---|
| `GET /api/v2/points/balance` | Баланс баллов и транзакции |
| `GET /api/v2/measurements` | Замеры тела |
| `GET /api/v2/inventory` | Инвентарь (с фильтрами) |
| `GET /api/v2/schedule/today` | Расписание на сегодня |
| `GET /api/v2/charts/activity` | График активности за N дней |
| `GET /api/v2/charts/points-trend` | Тренд баллов |
| `GET /api/v2/charts/xp-history` | История XP |

## Стек

Python 3.11+, FastAPI (async), SQLAlchemy 2.0, PostgreSQL 15, Alembic, Jinja2, Chart.js, Docker Compose, Nginx + SSL.

## Тесты

```bash
ruff check && pytest tests/ -q
```

## Структура

```
app/            — исходники (api, models, schemas, gamification, llm, i18n)
alembic/        — миграции БД
nginx/          — конфигурация Nginx + SSL (сертификаты — локально, не в git)
tests/          — pytest тесты
memory/         — память проекта (контекст, решения, статус)
```

## Лицензия

MIT
