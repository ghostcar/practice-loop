"""Seed data: hierarchical body part reference (update2.md §1).

Idempotent: upsert by slug so repeated invocations are safe.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.body_part import BodyPart

# (slug, title_ru, parent_slug_or_None, body_system, is_sensitive)
# Order matters: parents must be inserted before children.
BODY_PARTS_SEED: list[tuple[str, str, str | None, str, bool]] = [
    # Top-level
    ("whole_body", "Всё тело", None, "general", False),
    ("head", "Голова", None, "head_neck", False),
    ("torso_shoulders", "Плечи", None, "torso", False),
    ("torso_chest", "Грудь", None, "torso", True),
    ("torso_abdomen", "Живот", None, "torso", False),
    ("torso_waist", "Талия", None, "torso", False),
    ("torso_back", "Спина", None, "torso", False),
    ("torso_buttocks", "Ягодицы", None, "torso", False),
    ("torso_pelvis", "Таз", None, "torso", False),
    ("arms", "Руки", None, "upper_limb", False),
    ("legs", "Ноги", None, "lower_limb", False),
    ("intimate_area", "Интимная зона", None, "intimate", True),
    # Head children
    ("hair", "Волосы", "head", "head_neck", False),
    ("face", "Лицо", "head", "head_neck", False),
    ("neck", "Шея", "head", "head_neck", True),
    # Face children
    ("forehead", "Лоб", "face", "head_neck", False),
    ("cheeks", "Щёки", "face", "head_neck", False),
    ("lips", "Губы", "face", "head_neck", True),
    ("mouth", "Рот", "face", "head_neck", True),
    ("ears", "Уши", "head", "head_neck", True),
    # Neck children
    ("throat", "Горло", "neck", "head_neck", True),
    # Chest children
    ("nipples", "Соски", "torso_chest", "torso", True),
    # Abdomen children
    ("abs", "Пресс", "torso_abdomen", "torso", False),
    # Back children
    ("lower_back", "Поясница", "torso_back", "torso", False),
    # Arms children
    ("upper_arm", "Плечо", "arms", "upper_limb", False),
    ("elbows", "Локти", "arms", "upper_limb", False),
    ("forearms", "Предплечья", "arms", "upper_limb", False),
    ("wrists", "Запястья", "arms", "upper_limb", False),
    ("hands", "Кисти", "arms", "upper_limb", False),
    # Hands children
    ("fingers", "Пальцы рук", "hands", "upper_limb", False),
    # Legs children
    ("thighs", "Бёдра", "legs", "lower_limb", False),
    ("knees", "Колени", "legs", "lower_limb", False),
    ("shins", "Голени", "legs", "lower_limb", False),
    ("calves", "Икры", "legs", "lower_limb", False),
    ("ankles", "Лодыжки", "legs", "lower_limb", False),
    ("feet", "Ступни", "legs", "lower_limb", False),
    # Feet children
    ("toes", "Пальцы ног", "feet", "lower_limb", False),
    # Intimate children
    ("genitals", "Гениталии", "intimate_area", "intimate", True),
    ("anal_area", "Анальная зона", "intimate_area", "intimate", True),
]


async def seed_body_parts(db: AsyncSession) -> list[BodyPart]:
    """Upsert body parts by slug. Returns all created/updated records."""
    created: list[BodyPart] = []

    # Collect existing slugs to resolve parent references
    slug_to_id: dict[str, uuid.UUID] = {}

    # First pass: upsert top-level, collecting IDs
    for idx, (slug, title, parent_slug, body_system, is_sensitive) in enumerate(BODY_PARTS_SEED):
        result = await db.execute(select(BodyPart).where(BodyPart.slug == slug))
        existing = result.scalar_one_or_none()

        parent_id: uuid.UUID | None = None
        if parent_slug:
            parent_id = slug_to_id.get(parent_slug)
            if parent_id is None:
                # Parent not yet created — look it up
                pr = await db.execute(select(BodyPart.id).where(BodyPart.slug == parent_slug))
                parent_id = pr.scalar_one_or_none()

        if existing:
            # Update mutable fields
            existing.title_ru = title
            existing.body_system = body_system
            existing.is_sensitive = is_sensitive
            existing.sort_order = idx
            if parent_id is not None:
                existing.parent_id = parent_id
            created.append(existing)
        else:
            bp = BodyPart(
                slug=slug,
                title_ru=title,
                body_system=body_system,
                is_sensitive=is_sensitive,
                sort_order=idx,
                parent_id=parent_id,
            )
            db.add(bp)
            created.append(bp)

        await db.flush()
        # Refresh ID map (in case it was newly created)
        if existing:
            slug_to_id[slug] = existing.id
        else:
            slug_to_id[slug] = bp.id

    # Second pass: ensure all parent_ids are set (for already-seeded records
    # where the parent relationship wasn't established)
    for slug, _title, parent_slug, _bs, _is in BODY_PARTS_SEED:
        if parent_slug:
            pid = slug_to_id.get(parent_slug)
            if pid:
                result = await db.execute(select(BodyPart).where(BodyPart.slug == slug))
                bp = result.scalar_one_or_none()
                if bp and bp.parent_id != pid:
                    bp.parent_id = pid

    await db.flush()
    return created
