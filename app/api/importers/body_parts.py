"""Import handler — body parts (reference)."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.body_part import BodyPart
from app.models.user import User

logger = logging.getLogger(__name__)


async def _import_body_parts(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    """Import custom body parts (reference data)."""
    imported = skipped = 0
    for row in rows:
        try:
            slug = str(row.get("slug", ""))
            existing = (await db.execute(select(BodyPart).where(BodyPart.slug == slug))).scalar_one_or_none()
            if existing and mode != "insert":
                if row.get("title_ru"):
                    existing.title_ru = str(row["title_ru"])
                if row.get("title_en"):
                    existing.title_en = str(row["title_en"])
            else:
                parent_id = None
                if row.get("parent_slug"):
                    pr = await db.execute(select(BodyPart.id).where(BodyPart.slug == str(row["parent_slug"])))
                    p = pr.first()
                    if p:
                        parent_id = p[0]
                db.add(
                    BodyPart(
                        slug=slug,
                        title_ru=str(row.get("title_ru", slug)),
                        title_en=str(row.get("title_en", "")) or None,
                        body_system=str(row.get("body_system", "general")),
                        is_sensitive=str(row.get("is_sensitive", "false")).lower() == "true",
                        parent_id=parent_id,
                    )
                )
            imported += 1
        except Exception as e:
            logger.warning(f"Skip body_part row: {e}")
            skipped += 1
    return {"status": "ok", "imported": imported, "skipped": skipped}
