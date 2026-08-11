"""Seed data: inventory category reference (update2.md §5).

Idempotent: upsert by slug.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_category import InventoryCategory

# (slug, title)
INVENTORY_CATEGORIES_SEED: list[tuple[str, str]] = [
    ("impact_tool", "Ударный инструмент"),
    ("bondage_equipment", "Фиксация и бондаж"),
    ("wearable", "Носимый предмет"),
    ("restraint", "Средство фиксации"),
    ("sensory_tool", "Сенсорный предмет"),
    ("fitness_equipment", "Тренировочное оборудование"),
    ("cardio_equipment", "Кардио-оборудование"),
    ("recovery_item", "Восстановление и уход"),
    ("hygiene_supply", "Гигиена"),
    ("consumable", "Расходник"),
    ("measurement_tool", "Измерение и таймеры"),
    ("service_item", "Сервис и ритуалы"),
    ("clothing", "Одежда"),
    ("footwear", "Обувь"),
    ("storage", "Хранение"),
    ("other", "Другое"),
]


async def seed_inventory_categories(db: AsyncSession) -> list[InventoryCategory]:
    """Upsert inventory categories by slug."""
    created: list[InventoryCategory] = []

    for idx, (slug, title) in enumerate(INVENTORY_CATEGORIES_SEED):
        result = await db.execute(select(InventoryCategory).where(InventoryCategory.slug == slug))
        existing = result.scalar_one_or_none()

        if existing:
            existing.title = title
            existing.sort_order = idx
            existing.is_active = True
            created.append(existing)
        else:
            cat = InventoryCategory(slug=slug, title=title, sort_order=idx, is_active=True)
            db.add(cat)
            created.append(cat)

    await db.flush()
    return created
