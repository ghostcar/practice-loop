"""Seed data: system location reference (update2.md §3).

Idempotent: upsert by slug.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_location import TaskLocation

# (slug, title_ru, parent_slug_or_None, location_type, privacy_level)
# Order: top-level groups first, then concrete locations.
LOCATIONS_SEED: list[tuple[str, str, str | None, str, str]] = [
    # Top-level groups
    ("home", "Дом", None, "home", "private"),
    ("room", "Комната", None, "room", "shared"),
    ("bathroom", "Ванная / санузел", None, "bathroom", "private"),
    ("training", "Тренировочная зона", None, "training", "private"),
    ("furniture", "Мебель и поверхность", None, "furniture", "private"),
    ("remote", "Удалённый формат", None, "remote", "remote"),
    ("virtual", "Виртуальный формат", None, "virtual", "remote"),
    ("outdoor", "На улице", None, "outdoor", "public"),
    ("other", "Другое", None, "other", "private"),
    # Concrete locations
    ("bedroom", "Спальня", "home", "room", "private"),
    ("living_room", "Гостиная", "home", "room", "shared"),
    ("kitchen", "Кухня", "home", "room", "shared"),
    ("bathroom_room", "Ванная", "bathroom", "bathroom", "private"),
    ("shower", "Душ", "bathroom_room", "bathroom", "private"),
    ("home_gym", "Домашний спортзал", "home", "training", "private"),
    ("bed", "Кровать", "bedroom", "furniture", "private"),
    ("sofa", "Диван", "living_room", "furniture", "shared"),
    ("floor", "Пол", "home", "furniture", "private"),
    ("against_wall", "У стены", "home", "furniture", "private"),
    ("in_front_of_mirror", "Перед зеркалом", "home", "furniture", "private"),
    ("training_mat_area", "На тренировочном коврике", "home_gym", "training", "private"),
    ("gym", "В спортзале", "training", "training", "shared"),
    ("outdoors", "На улице", "outdoor", "outdoor", "public"),
    ("remote_loc", "Удалённо", "remote", "remote", "remote"),
    ("online", "Онлайн", "virtual", "virtual", "remote"),
]


async def seed_locations(db: AsyncSession) -> list[TaskLocation]:
    """Upsert system locations by slug."""
    created: list[TaskLocation] = []
    slug_to_id: dict[str, uuid.UUID] = {}

    for idx, (slug, title, parent_slug, loc_type, privacy) in enumerate(LOCATIONS_SEED):
        result = await db.execute(select(TaskLocation).where(TaskLocation.slug == slug))
        existing = result.scalar_one_or_none()

        parent_id: uuid.UUID | None = None
        if parent_slug:
            parent_id = slug_to_id.get(parent_slug)
            if parent_id is None:
                pr = await db.execute(select(TaskLocation.id).where(TaskLocation.slug == parent_slug))
                parent_id = pr.scalar_one_or_none()

        if existing:
            existing.title_ru = title
            existing.location_type = loc_type
            existing.privacy_level = privacy
            existing.sort_order = idx
            if parent_id is not None:
                existing.parent_id = parent_id
            created.append(existing)
        else:
            loc = TaskLocation(
                slug=slug,
                title_ru=title,
                location_type=loc_type,
                privacy_level=privacy,
                is_custom=False,
                sort_order=idx,
                parent_id=parent_id,
            )
            db.add(loc)
            created.append(loc)

        await db.flush()
        if existing:
            slug_to_id[slug] = existing.id
        else:
            slug_to_id[slug] = loc.id

    # Second pass: fix parent relationships
    for slug, _title, parent_slug, _lt, _priv in LOCATIONS_SEED:
        if parent_slug:
            pid = slug_to_id.get(parent_slug)
            if pid:
                result = await db.execute(select(TaskLocation).where(TaskLocation.slug == slug))
                loc = result.scalar_one_or_none()
                if loc and loc.parent_id != pid:
                    loc.parent_id = pid

    await db.flush()
    return created
