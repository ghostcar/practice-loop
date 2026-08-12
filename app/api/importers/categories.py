"""Import handler — inventory categories (reference)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_category import InventoryCategory
from app.models.user import User

logger = logging.getLogger(__name__)


async def _import_inventory_categories(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    """Import custom inventory categories."""
    imported = skipped = 0
    for row in rows:
        try:
            slug = str(row.get("slug", ""))
            existing = (
                await db.execute(select(InventoryCategory).where(InventoryCategory.slug == slug))
            ).scalar_one_or_none()
            if existing and mode != "insert":
                if row.get("title"):
                    existing.title = str(row["title"])
                if row.get("description"):
                    existing.description = str(row["description"])
            else:
                db.add(
                    InventoryCategory(
                        slug=slug,
                        title=str(row.get("title", slug)),
                        description=str(row.get("description", "")) or None,
                    )
                )
            imported += 1
        except Exception as e:
            logger.warning(f"Skip inventory_category row: {e}")
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}
