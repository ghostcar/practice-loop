"""One-shot: create a training day with hydration schedule for the first user.

Requires DATABASE_URL to be set (no hardcoded credentials):
    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db python seed_training.py
"""

import asyncio
import os
import sys

if not os.environ.get("DATABASE_URL"):
    print(
        "Error: DATABASE_URL is not set. Export it (e.g. postgresql+asyncpg://user:pass@host:5432/db) and retry.",
        file=sys.stderr,
    )
    sys.exit(1)

from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

import app.models.training  # noqa
import app.models.user  # noqa
from app.models.training import TrainingDay
from app.models.user import User

PLAN_TEXT = """## Стартовая сессия — Воскресенье

**Старт:** воскресенье 00:00
**Исходное:** мочевой пузырь условно пустой
**Оборудование:** клетка/пояс верности — по желанию с самого начала или с утра

### Базовый график приёма жидкости

| Время | Базовый объём | Примечание |
|---|---|---|
| 00:00 | 400 мл | Старт |
| 01:00 | 300 мл | |
| 01:40–02:00 | 100–150 мл | Перед сном |
| 02:00–06:30 | — | Сон |
| 06:30–07:15 | 350 мл | После подъёма |
| 07:20–07:50 | — | Дорога на работу (без слива) |
| 09:00 | 300 мл | |
| 10:30 | 350 мл | |
| 11:50 | 250 мл | |
| 12:00–13:00 | 400 мл | Обед |
| 14:00 | 300 мл | |
| 15:30 | 350 мл | |
| 16:20 | 200 мл | Перед выездом |
| 16:30–≈20:00 | ≤ 150–200 мл | Длинный переезд + занятость (слив невозможен) |
| 20:15–21:00 | 450 мл | |
| 21:30–22:15 | 350 мл | |
| 22:30–23:00 | 200 мл | |
| 23:00–00:00 | ≤ 100 мл | |
| 00:00–00:20 | 250–300 мл | Последняя порция + подготовка ночного блока |

**Ориентир по итогу:** 5,0–5,3 л (можно меньше или чуть больше — смотри по давлению).

### Микро-сливы
Используй по реальному давлению. Рекомендуемые окна (можно сдвигать):
- 03:00–03:30 (ночь)
- 07:00–07:20 (утро)
- 11:00–11:40
- 15:10–15:40
- 21:30–22:00
- 00:30–00:45 (если очень нужно в ночном блоке)

Каждый раз фиксируй время и секунды.

### Ночной блок (пн 00:00–01:30)
- Пробка + кляп + прищепки
- Удержание в позе
- Мокрый финал до 01:00
- Душ
- Завершение к 01:30
- Сон ≈ 02:00

### Что записывать
- Сколько реально выпил за день
- В какие окна и на сколько секунд делал микро-сливы
- Когда давление стало сильным / очень сильным
- Как прошёл участок 16:30–20:00
- Ощущения и объём на финальном сливе
- Самочувствие утром

### После завершения
Скинуть результаты — на их основе будет построена полноценная волновая программа на пн–пт
с чередованием высоких объёмов и «концентрированных» дней.
"""


async def main():
    database_url = os.environ["DATABASE_URL"]
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        if not user:
            print("No users! Register first.", file=sys.stderr)
            sys.exit(1)

        today = date.today()

        # Check if already exists
        existing = await db.execute(
            select(TrainingDay).where(
                TrainingDay.user_id == user.id,
                TrainingDay.target_date == today,
            )
        )
        if existing.scalar_one_or_none():
            print(f"Training day for {today} already exists. Skipping.")
            return

        td = TrainingDay(
            user_id=user.id,
            target_date=today,
            status="active",
            plan_summary=PLAN_TEXT,
        )
        db.add(td)
        await db.commit()
        print(f"✅ Training day created for {user.email} on {today}")
        print(f"   ID: {td.id}")
        print("   Status: active")
        print("   Open /training to see the plan")


if __name__ == "__main__":
    asyncio.run(main())
