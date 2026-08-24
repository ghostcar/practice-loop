"""Import handler — inventory / shopping list."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.inventory_category import InventoryCategory
from app.models.life import InventoryItem
from app.models.user import User

logger = logging.getLogger(__name__)


async def _import_inventory(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
    for row in rows:
        try:
            # Resolve inventory_category_id from slug if provided
            cat_id = None
            cat_slug = row.get("inventory_category_slug")
            if cat_slug:
                cat_res = await db.execute(select(InventoryCategory.id).where(InventoryCategory.slug == str(cat_slug)))
                cat_row = cat_res.first()
                if cat_row:
                    cat_id = cat_row[0]

            item = InventoryItem(
                user_id=user.id,
                category=str(row.get("category", "other")),
                name=str(row.get("name", "")),
                description=str(row.get("description", "")) or None,
                quantity=int(row.get("quantity", 1)),
                quantity_needed=int(row.get("quantity_needed", 1)),
                is_shopping_list=str(row.get("is_shopping_list", "false")).lower() == "true",
                status=str(row.get("status", "need")),
                inventory_category_id=cat_id,
                inventory_status=str(row.get("inventory_status", "available")),
                priority=int(row.get("priority", 0)),
            )
            db.add(item)
            imported += 1
        except (ValueError, KeyError) as e:
            logger.warning(f"Skip inventory row: {e}")
            skipped += 1
    return {"status": "ok", "imported": imported, "skipped": skipped}
