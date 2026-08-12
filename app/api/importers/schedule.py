"""Import handler — schedule rules."""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.life import ScheduleRule
from app.models.user import User

logger = logging.getLogger(__name__)


async def _import_schedule(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
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

            start_time = datetime.strptime(str(row.get("start_time", "00:00")), "%H:%M").time()
            end_time = None
            if row.get("end_time"):
                end_time = datetime.strptime(str(row["end_time"]), "%H:%M").time()

            rule = ScheduleRule(
                user_id=user.id,
                entity_id=entity_id,
                day_of_week=int(row.get("day_of_week", 0)),
                start_time=start_time,
                end_time=end_time,
                task_type=str(row.get("task_type", "mandatory")),
                recurring=str(row.get("recurring", "true")).lower() == "true",
                notes=str(row.get("notes", "")) or None,
            )
            db.add(rule)
            imported += 1
        except Exception as e:
            logger.warning(f"Skip schedule row: {e}")
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}
