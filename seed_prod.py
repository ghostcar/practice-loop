"""One-shot seed: populate production database with initial v2 data.

Usage:
    python seed_prod.py --email user@example.com
    python seed_prod.py --email user@example.com --database-url postgresql+asyncpg://...

Environment:
    DATABASE_URL  — PostgreSQL connection string (fallback if --database-url not given)
"""

import argparse
import asyncio
import os
import sys
from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# Import all models to ensure mapper registry is complete
import app.models.achievement  # noqa: F401
import app.models.activity_log  # noqa: F401
import app.models.entity  # noqa: F401
import app.models.life  # noqa: F401
import app.models.llm_config  # noqa: F401
import app.models.notification  # noqa: F401
import app.models.opt_in  # noqa: F401
import app.models.points  # noqa: F401
import app.models.progress  # noqa: F401
import app.models.session  # noqa: F401
import app.models.training  # noqa: F401
import app.models.user  # noqa: F401
from app.models.entity import Entity
from app.models.life import BodyMeasurement, InventoryItem, ScheduleRule
from app.models.user import User


async def seed(database_url: str, email: str | None):
    engine = create_async_engine(database_url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as db:
        if email:
            result = await db.execute(select(User).where(User.email == email).limit(1))
            user = result.scalar_one_or_none()
            if not user:
                print(f"User not found: {email}", file=sys.stderr)
                sys.exit(1)
        else:
            result = await db.execute(select(User).limit(1))
            user = result.scalar_one_or_none()
            if not user:
                print("No users! Register first.", file=sys.stderr)
                print("  curl -X POST https://your-host/auth/register -d 'email=...&password=...'", file=sys.stderr)
                sys.exit(1)

        uid = user.id
        print(f"Seeding for: {user.email}")

        # ── Entities with gamification_config ──
        entities = [
            (
                "Золотой Дождь",
                "ws",
                "series",
                50,
                {
                    "points": {"base": 50, "max_per_day": 200},
                    "penalties": {
                        "enabled": True,
                        "escalation": True,
                        "levels": [
                            {
                                "level": 1,
                                "deduction": 5,
                                "condition": "missed",
                                "redemption": {"type": "drink_sips", "count": 3},
                            },
                            {"level": 2, "deduction": 10, "condition": "partial"},
                            {"level": 3, "deduction": 20, "condition": "late"},
                        ],
                    },
                    "bonuses": [
                        {"code": "extra_fluid", "condition": "extra_fluid_ml > 0", "reward": 20, "per_unit": True},
                        {"code": "level_jump", "condition": "level_jump == true", "reward": 50},
                    ],
                    "thresholds": {"negative": -200, "warning": 0, "good": 200},
                },
            ),
            (
                "Копро",
                "ws",
                "series",
                100,
                {
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
                            }
                        ],
                    },
                    "bonuses": [
                        {"code": "extra_hours", "condition": "extra_hours > 0", "reward": 30, "per_unit": True}
                    ],
                    "thresholds": {"negative": -300, "warning": 0, "good": 300},
                },
            ),
            (
                "Прищепки",
                "punishment",
                "one_time",
                7,
                {
                    "points": {"base": 7, "max_per_day": 70},
                    "penalties": {
                        "enabled": True,
                        "levels": [
                            {
                                "level": 1,
                                "deduction": 7,
                                "condition": "missed",
                                "redemption": {"type": "clothespins", "duration_min": 35},
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
            ),
            (
                "Бондаж",
                "punishment",
                "one_time",
                50,
                {
                    "points": {"base": 50, "max_per_day": 100},
                    "penalties": {
                        "enabled": True,
                        "levels": [
                            {
                                "level": 1,
                                "deduction": 0,
                                "condition": "missed",
                                "redemption": {"type": "bondage", "duration_min": 60},
                            }
                        ],
                    },
                },
            ),
            (
                "Упаковка (Chastity)",
                "chastity",
                "infinite",
                70,
                {
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
                            }
                        ],
                    },
                    "thresholds": {"negative": -100, "warning": 0, "good": 500},
                },
            ),
        ]

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

        for name, cat, etype, _pts, gcfg in entities:
            e = Entity(
                type=etype,
                real_name=name,
                category=cat,
                tags=["seed_v2"],
                is_public=False,
                owner_id=uid,
                author_id=uid,
                gamification_config=gcfg,
            )
            db.add(e)

        for name, cat, etype, pts in sports:
            e = Entity(
                type=etype,
                real_name=name,
                category=cat,
                tags=["seed_v2"],
                is_public=False,
                owner_id=uid,
                author_id=uid,
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
                            }
                        ],
                    },
                },
            )
            db.add(e)

        print(f"  ✓ {len(entities) + len(sports)} entities")

        # ── Measurements ──
        for d, tod, w, ch, uc, wa, hi, th in [
            ("2019-04-05", "morning", 98.5, None, None, 100.0, 106.0, 61.0),
            ("2019-04-05", "evening", 98.3, None, None, None, None, None),
            ("2019-04-06", "morning", 98.1, 112.0, 100.0, 98.0, 106.0, 61.0),
            ("2019-04-07", "morning", 97.7, 112.0, 98.0, 98.0, 106.0, 61.0),
            ("2019-04-08", "morning", 98.0, None, None, None, None, None),
        ]:
            db.add(
                BodyMeasurement(
                    user_id=uid,
                    measured_date=date.fromisoformat(d),
                    time_of_day=tod,
                    weight=w,
                    chest=ch,
                    under_chest=uc,
                    waist=wa,
                    hips=hi,
                    thigh=th,
                )
            )
        print("  ✓ 5 measurements")

        # ── Inventory ──
        items = [
            ("clothing", "Стринги (разные цвета)", 7, 15, 3),
            ("clothing", "Шортики", 3, 7, 2),
            ("clothing", "Бикини", 7, 15, 3),
            ("clothing", "Колготки 40 ден", 8, 12, 3),
            ("clothing", "Чулки", 8, 8, 2),
            ("clothing", "Танга", 7, 7, 2),
            ("equipment", "Веревка 6 мм (20 м)", 7, 7, 5),
            ("equipment", "Цепь 4 мм (2 м)", 8, 12, 4),
            ("equipment", "Замки (разные)", 20, 50, 5),
            ("equipment", "Карабины", 20, 100, 5),
            ("equipment", "Стрейч-пленка (200 м)", 2, 10, 3),
            ("equipment", "Кляп-член", 1, 1, 1),
            ("equipment", "Ошейник (кожа)", 1, 1, 2),
            ("equipment", "Прищепки (5 компл)", 1, 5, 3),
            ("cosmetics", "Лак для ногтей (набор)", 0, 5, 1),
        ]
        for cat, name, qty, qty_n, prio in items:
            db.add(
                InventoryItem(
                    user_id=uid,
                    category=cat,
                    name=name,
                    quantity=qty,
                    quantity_needed=qty_n,
                    is_shopping_list=True,
                    status="need",
                    priority=prio,
                )
            )
        print(f"  ✓ {len(items)} inventory items")

        # ── Schedule ──
        rules = [
            (7, time(6, 30), time(6, 35), "mandatory", "Подъем"),
            (7, time(6, 35), time(6, 45), "mandatory", "Зарядка"),
            (7, time(6, 45), time(7, 0), "mandatory", "Водные процедуры"),
            (7, time(7, 0), time(7, 30), "mandatory", "Завтрак"),
            (7, time(18, 20), None, "mandatory", "Возвращение домой"),
            (7, time(21, 0), None, "mandatory", "Ужин"),
            (7, time(22, 0), None, "mandatory", "Отчет"),
            (7, time(23, 0), None, "optional", "Свободное время"),
            (7, time(0, 0), None, "mandatory", "Отбой"),
        ]
        for dow, st, et, tt, notes in rules:
            db.add(
                ScheduleRule(
                    user_id=uid, day_of_week=dow, start_time=st, end_time=et, task_type=tt, recurring=True, notes=notes
                )
            )
        print(f"  ✓ {len(rules)} schedule rules")

        await db.commit()
        print("\n✅ Seed complete!")


def main():
    parser = argparse.ArgumentParser(description="Seed production database with initial data")
    parser.add_argument("--email", help="User email to seed data for (default: first user in DB)")
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", "postgresql+asyncpg://tracker:REDACTED_DB_PASSWORD@localhost:5432/tracker"),
        help="PostgreSQL connection string (default: DATABASE_URL env or localhost)",
    )
    args = parser.parse_args()

    if not args.email:
        print("Warning: no --email given, will seed for the first user found.", file=sys.stderr)

    asyncio.run(seed(args.database_url, args.email))


if __name__ == "__main__":
    main()
