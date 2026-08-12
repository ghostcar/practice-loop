"""Import handler — training days."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.training import TrainingDay
from app.models.user import User

logger = logging.getLogger(__name__)


async def _import_training_days(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
    for row in rows:
        try:
            td = TrainingDay(
                user_id=user.id,
                target_date=date.fromisoformat(str(row.get("target_date", date.today().isoformat()))),
                status=str(row.get("status", "planned")),
                plan_summary=str(row.get("plan_summary", "")) or None,
                analysis_summary=str(row.get("analysis_summary", "")) or None,
            )
            db.add(td)
            imported += 1
        except Exception as e:
            logger.warning(f"Skip training_day row: {e}")
            skipped += 1
    await db.commit()
    return {"status": "ok", "imported": imported, "skipped": skipped}
