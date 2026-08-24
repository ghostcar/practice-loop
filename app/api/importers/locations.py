"""Import handler — locations (reference)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.task_location import TaskLocation
from app.models.user import User

logger = logging.getLogger(__name__)


async def _import_locations(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    """Import custom locations."""
    imported = skipped = 0
    for row in rows:
        try:
            slug = str(row.get("slug", ""))
            existing = (
                await db.execute(
                    select(TaskLocation).where(TaskLocation.slug == slug, TaskLocation.owner_id == user.id)
                )
            ).scalar_one_or_none()
            if existing and mode != "insert":
                if row.get("title_ru"):
                    existing.title_ru = str(row["title_ru"])
                if row.get("location_type"):
                    existing.location_type = str(row["location_type"])
            else:
                parent_id = None
                if row.get("parent_slug"):
                    pr = await db.execute(select(TaskLocation.id).where(TaskLocation.slug == str(row["parent_slug"])))
                    p = pr.first()
                    if p:
                        parent_id = p[0]
                db.add(
                    TaskLocation(
                        slug=slug,
                        title_ru=str(row.get("title_ru", slug)),
                        title_en=str(row.get("title_en", "")) or None,
                        location_type=str(row.get("location_type", "other")),
                        privacy_level=str(row.get("privacy_level", "private")),
                        is_custom=True,
                        owner_id=user.id,
                        parent_id=parent_id,
                    )
                )
            imported += 1
        except Exception as e:
            logger.warning(f"Skip location row: {e}")
            skipped += 1
    return {"status": "ok", "imported": imported, "skipped": skipped}
