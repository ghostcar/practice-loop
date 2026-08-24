"""Import handler — body measurements."""

from __future__ import annotations

import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.importers.base import _float_or_none
from app.models.life import BodyMeasurement
from app.models.user import User

logger = logging.getLogger(__name__)


async def _import_measurements(rows: list[dict], db: AsyncSession, user: User, mode: str = "upsert") -> dict:
    imported = skipped = 0
    for row in rows:
        try:
            d = {
                "measured_date": date.fromisoformat(str(row.get("measured_date", row.get("date", "")))),
                "time_of_day": str(row.get("time_of_day", "morning")),
                "weight": _float_or_none(row.get("weight")),
                "chest": _float_or_none(row.get("chest")),
                "under_chest": _float_or_none(row.get("under_chest")),
                "waist": _float_or_none(row.get("waist")),
                "hips": _float_or_none(row.get("hips")),
                "thigh": _float_or_none(row.get("thigh")),
                "notes": str(row.get("notes", "")) or None,
            }
            result = await db.execute(
                select(BodyMeasurement).where(
                    BodyMeasurement.user_id == user.id,
                    BodyMeasurement.measured_date == d["measured_date"],
                    BodyMeasurement.time_of_day == d["time_of_day"],
                )
            )
            existing = result.scalar_one_or_none()
            if existing and mode != "insert":
                for k, v in d.items():
                    setattr(existing, k, v)
            else:
                db.add(BodyMeasurement(user_id=user.id, **d))
            imported += 1
        except (ValueError, KeyError) as e:
            logger.warning(f"Skip measurement row: {e}")
            skipped += 1
    return {"status": "ok", "imported": imported, "skipped": skipped}
