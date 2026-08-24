"""Import handler — task entities."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.user import User

logger = logging.getLogger(__name__)


async def _import_entities(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
    for row in rows:
        try:
            gc = row.get("gamification_config")
            if isinstance(gc, dict):
                pass
            elif isinstance(gc, str) and gc:
                gc = json.loads(gc)
            else:
                gc = None

            parent_id = None
            parent_code = row.get("parent_code")
            if parent_code:
                # Only link to own/public entities — never to another user's private one.
                p_result = await db.execute(
                    select(Entity.id)
                    .where(
                        Entity.real_name == str(parent_code),
                        (Entity.owner_id == user.id) | Entity.is_public.is_(True),
                    )
                    .limit(1)
                )
                p_row = p_result.first()
                if p_row:
                    parent_id = p_row[0]

            tags = row.get("tags")
            if isinstance(tags, str) and tags:
                tags = [t.strip() for t in tags.split(",")]

            entity = Entity(
                type=str(row.get("type", "one_time")),
                real_name=str(row.get("real_name", "")),
                category=str(row.get("category", "general")),
                level=int(row.get("level", 1)),
                parent_id=parent_id,
                tags=tags,
                is_public=str(row.get("is_public", "false")).lower() == "true",
                author_id=user.id,
                owner_id=user.id,
                gamification_config=gc,
            )
            db.add(entity)
            imported += 1
        except Exception as e:
            logger.warning(f"Skip entity row: {e}")
            skipped += 1
    return {"status": "ok", "imported": imported, "skipped": skipped}
