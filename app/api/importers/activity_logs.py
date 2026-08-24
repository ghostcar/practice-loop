"""Import handler — activity logs."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.user import User

logger = logging.getLogger(__name__)


async def _import_activity_logs(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
    for row in rows:
        try:
            entity_id = None
            entity_name = row.get("entity_name") or row.get("entity_code")
            if entity_name:
                e_result = await db.execute(
                    select(Entity.id)
                    .where(
                        Entity.real_name == str(entity_name),
                        (Entity.owner_id == user.id) | Entity.is_public.is_(True),
                    )
                    .limit(1)
                )
                e_row = e_result.first()
                if e_row:
                    entity_id = e_row[0]

            created_at = datetime.now(UTC)
            if row.get("created_at"):
                created_at = datetime.fromisoformat(str(row["created_at"]))

            completed_at = None
            if row.get("completed_at"):
                completed_at = datetime.fromisoformat(str(row["completed_at"]))

            log = ActivityLog(
                user_id=user.id,
                entity_id=entity_id,
                status=str(row.get("status", "created")),
                selected_entity_name=str(row.get("selected_entity_name", "")),
                created_at=created_at,
                completed_at=completed_at,
            )
            db.add(log)
            imported += 1
        except Exception as e:
            logger.warning(f"Skip activity_log row: {e}")
            skipped += 1
    return {"status": "ok", "imported": imported, "skipped": skipped}
