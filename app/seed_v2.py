"""Seed v2: import structured data from examples/ into the new models.

Run: python -m app.seed_v2
"""

import asyncio
import os
import sys
from datetime import date, time

from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.models.entity import Entity
from app.models.life import BodyMeasurement, InventoryItem, ScheduleRule
from app.models.user import User


async def seed_entities(db: AsyncSession, user_id) -> None:
    """Seed hierarchical entities from Книга1.xlsx structure."""
    categories = {
        "ЗД": {
            "real_name": "Золотой Дождь",
            "category": "ws",
            "type": "series",
            "gamification_config": {
                "points": {"base": 50, "max_per_day": 200},
                "penalties": {
                    "enabled": True,
                    "escalation": True,
                    "levels": [
                        {
                            "level": 1,
                            "deduction": 5,
                            "condition": "missed",
                            "redemption": {
                                "type": "drink_sips",
                                "count": 3,
                                "description": "Drink 3 sips",
                            },
                        },
                        {"level": 2, "deduction": 10, "condition": "partial"},
                        {"level": 3, "deduction": 20, "condition": "late"},
                    ],
                },
                "bonuses": [
                    {
                        "code": "extra_fluid",
                        "condition": "extra_fluid_ml > 0",
                        "reward": 20,
                        "per_unit": True,
                        "description": "Per extra glass of fluid",
                    },
                    {
                        "code": "level_jump",
                        "condition": "level_jump == true",
                        "reward": 50,
                        "description": "Jumped to next level in one day",
                    },
                ],
                "thresholds": {"negative": -200, "warning": 0, "good": 200},
            },
        },
        "КП": {
            "real_name": "Копро",
            "category": "ws",
            "type": "series",
            "gamification_config": {
                "points": {"base": 100, "max_per_day": 300},
                "penalties": {
                    "enabled": True,
                    "escalation": True,
                    "levels": [
                        {
                            "level": 1,
                            "deduction": 20,
                            "condition": "missed",
                            "redemption": {"type": "toilet_cleaning", "duration_min": 5},
                        },
                    ],
                },
                "bonuses": [
                    {
                        "code": "extra_hours",
                        "condition": "extra_hours > 0",
                        "reward": 30,
                        "per_unit": True,
                        "description": "Per extra 90 min of accumulation",
                    },
                ],
                "thresholds": {"negative": -300, "warning": 0, "good": 300},
            },
        },
        "Прищепки": {
            "real_name": "Clothespins",
            "category": "punishment",
            "type": "one_time",
            "gamification_config": {
                "points": {"base": 7, "max_per_day": 70},
                "penalties": {
                    "enabled": True,
                    "levels": [
                        {
                            "level": 1,
                            "deduction": 7,
                            "condition": "missed",
                            "redemption": {
                                "type": "clothespins",
                                "duration_min": 35,
                                "description": "35 min clothespins",
                            },
                        },
                        {
                            "level": 2,
                            "deduction": 5,
                            "condition": "short_time",
                            "redemption": {"type": "clothespins", "duration_min": 10},
                        },
                    ],
                },
            },
        },
        "Бондаж": {
            "real_name": "Bondage",
            "category": "punishment",
            "type": "one_time",
            "gamification_config": {
                "points": {"base": 50, "max_per_day": 100},
                "penalties": {
                    "enabled": True,
                    "levels": [
                        {
                            "level": 1,
                            "deduction": 0,
                            "condition": "missed",
                            "redemption": {"type": "bondage", "duration_min": 60},
                        },
                    ],
                },
            },
        },
        "Упаковка": {
            "real_name": "Packaging (Chastity)",
            "category": "chastity",
            "type": "infinite",
            "gamification_config": {
                "points": {"base": 70, "max_per_day": 70},
                "penalties": {
                    "enabled": True,
                    "escalation": True,
                    "levels": [
                        {
                            "level": 1,
                            "deduction": 70,
                            "condition": "missed",
                            "redemption": {"type": "bondage", "duration_min": 120},
                        },
                    ],
                },
                "thresholds": {"negative": -100, "warning": 0, "good": 500},
            },
        },
    }

    # Sport/fitness entities
    sports = [
        ("Планка", "sport", "one_time", 10),
        ("Скалолаз", "sport", "one_time", 10),
        ("Пресс за 30 дней", "sport", "series", 20),
        ("Худеем за 30 дней", "sport", "series", 20),
        ("Растяжка шпагат", "sport", "one_time", 15),
        ("Утренняя зарядка", "sport", "one_time", 15),
        ("Оральная техника", "technique", "one_time", 30),
        ("Анальная техника", "technique", "one_time", 30),
        ("Глубокое горло", "technique", "one_time", 30),
        ("Питьё", "health", "one_time", 5),
    ]

    for code, cfg in categories.items():
        entity = Entity(
            type=cfg["type"],
            real_name=cfg["real_name"],
            category=cfg["category"],
            tags=[code],
            is_public=False,
            author_id=user_id,
            owner_id=user_id,
            gamification_config=cfg["gamification_config"],
        )
        db.add(entity)

    for name, cat, etype, pts in sports:
        entity = Entity(
            type=etype,
            real_name=name,
            category=cat,
            tags=["seed_v2"],
            is_public=False,
            author_id=user_id,
            owner_id=user_id,
            gamification_config={
                "points": {"base": pts, "max_per_day": pts * 2},
                "penalties": {
                    "enabled": True,
                    "levels": [
                        {
                            "level": 1,
                            "deduction": pts // 2,
                            "condition": "missed",
                            "redemption": {"type": "extra_training", "duration_min": 15},
                        },
                    ],
                },
            },
        )
        db.add(entity)

    await db.flush()
    print(f"Seeded {len(categories) + len(sports)} entities")


async def seed_measurements(db: AsyncSession, user_id) -> None:
    """Seed sample measurements from Задачи.xlsx."""
    sample = [
        ("2019-04-05", "morning", 98.5, None, None, 100.0, 106.0, 61.0),
        ("2019-04-05", "evening", 98.3, None, None, None, None, None),
        ("2019-04-06", "morning", 98.1, 112.0, 100.0, 98.0, 106.0, 61.0),
        ("2019-04-06", "evening", 98.5, None, None, None, None, None),
        ("2019-04-07", "morning", 97.7, 112.0, 98.0, 98.0, 106.0, 61.0),
        ("2019-04-07", "evening", 98.5, None, None, None, None, None),
        ("2019-04-08", "morning", 98.0, None, None, None, None, None),
        ("2019-04-08", "evening", 99.0, None, None, None, None, None),
    ]

    for d, tod, w, ch, uc, wa, hi, th in sample:
        m = BodyMeasurement(
            user_id=user_id,
            measured_date=date.fromisoformat(d),
            time_of_day=tod,
            weight=w,
            chest=ch,
            under_chest=uc,
            waist=wa,
            hips=hi,
            thigh=th,
        )
        db.add(m)

    await db.flush()
    print(f"Seeded {len(sample)} measurements")


async def seed_inventory(db: AsyncSession, user_id) -> None:
    """Seed inventory from Книга_j.xlsx shopping lists."""
    items = [
        ("clothing", "Стринги (разные цвета)", 7, 15, True, "need", 3),
        ("clothing", "Шортики (разные цвета)", 3, 7, True, "need", 2),
        ("clothing", "Бикини", 7, 15, True, "need", 3),
        ("clothing", "Колготки 40 ден (разные цвета)", 8, 12, True, "need", 3),
        ("clothing", "Чулки (разные цвета)", 8, 8, True, "need", 2),
        ("clothing", "Колготки 70 ден", 10, 10, True, "need", 1),
        ("clothing", "Танга", 7, 7, True, "need", 2),
        ("equipment", "Веревка 6 мм (20 м)", 7, 7, True, "need", 5),
        ("equipment", "Веревка 4 мм (20 м)", 7, 7, True, "need", 5),
        ("equipment", "Веревка 2 мм (20 м)", 7, 7, True, "need", 5),
        ("equipment", "Цепь 4 мм (2 м)", 8, 12, True, "need", 4),
        ("equipment", "Цепь 2 мм (1 м)", 10, 10, True, "need", 3),
        ("equipment", "Замки (разные)", 20, 50, True, "need", 5),
        ("equipment", "Карабины", 20, 100, True, "need", 5),
        ("equipment", "Стрейч-пленка (200 м)", 2, 10, True, "need", 3),
        ("equipment", "Кляп-член (Модель 1)", 1, 1, True, "need", 1),
        ("equipment", "Кляп-шар (Модель 2)", 1, 1, True, "need", 1),
        ("equipment", "Ошейник (кожа)", 1, 1, True, "need", 2),
        ("equipment", "Наручники кожаные", 2, 2, True, "need", 3),
        ("equipment", "Браслеты кожаные (руки)", 2, 2, True, "need", 3),
        ("equipment", "Браслеты кожаные (ноги)", 2, 2, True, "need", 3),
        ("equipment", "Маска", 1, 3, True, "need", 2),
        ("equipment", "Spreader bars", 1, 3, True, "need", 1),
        ("equipment", "Вибратор/дилдо", 1, 1, True, "need", 2),
        ("equipment", "Анальная пробка (3 шт)", 1, 3, True, "need", 2),
        ("equipment", "Прищепки (5 компл)", 1, 5, True, "need", 3),
        ("equipment", "Таймеры", 1, 4, True, "need", 3),
        ("cosmetics", "Лак для ногтей прозрачный", 1, 2, True, "need", 1),
        ("cosmetics", "Лак для ногтей цветной (набор)", 0, 5, True, "need", 1),
        ("other", "Туфли на шпильке", 0, 3, True, "need", 1),
        ("other", "Сапоги на шпильке", 0, 4, True, "need", 1),
    ]

    for cat, name, qty, qty_n, shop, status, prio in items:
        item = InventoryItem(
            user_id=user_id,
            category=cat,
            name=name,
            quantity=qty,
            quantity_needed=qty_n,
            is_shopping_list=shop,
            status=status,
            priority=prio,
        )
        db.add(item)

    await db.flush()
    print(f"Seeded {len(items)} inventory items")


async def seed_schedule(db: AsyncSession, user_id) -> None:
    """Seed daily schedule from Регламент.docx."""
    rules = [
        (7, time(6, 30), time(6, 35), "mandatory", "Подъем"),
        (7, time(6, 35), time(6, 45), "mandatory", "Зарядка"),
        (7, time(6, 45), time(7, 0), "mandatory", "Водные процедуры"),
        (7, time(7, 0), time(7, 30), "mandatory", "Завтрак"),
        (7, time(7, 30), time(7, 50), "mandatory", "Сборы на работу"),
        (7, time(18, 20), None, "mandatory", "Возвращение домой"),
        (7, time(19, 0), None, "mandatory", "Водные процедуры"),
        (7, time(21, 0), None, "mandatory", "Ужин"),
        (7, time(22, 0), None, "mandatory", "Отчет"),
        (7, time(23, 0), None, "optional", "Свободное время"),
        (7, time(0, 0), None, "mandatory", "Отбой"),
    ]

    for dow, st, et, tt, notes in rules:
        rule = ScheduleRule(
            user_id=user_id,
            day_of_week=dow,
            start_time=st,
            end_time=et,
            task_type=tt,
            recurring=True,
            notes=notes,
        )
        db.add(rule)

    await db.flush()
    print(f"Seeded {len(rules)} schedule rules")


async def main():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import settings

    db_url = settings.database_url.replace("postgresql+asyncpg", "sqlite+aiosqlite")
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        # Get the first user
        from sqlalchemy import select as sa_select

        result = await db.execute(sa_select(User).limit(1))
        user = result.scalar_one_or_none()
        if not user:
            print("No users found. Create a user first.")
            return
        print(f"Seeding for user: {user.email}")

        await seed_entities(db, user.id)
        await seed_measurements(db, user.id)
        await seed_inventory(db, user.id)
        await seed_schedule(db, user.id)

        await db.commit()
        print("\n✅ Seed v2 complete!")


if __name__ == "__main__":
    asyncio.run(main())
