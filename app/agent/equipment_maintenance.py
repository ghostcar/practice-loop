"""Equipment Maintenance & Hygiene Tracker Engine."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.equipment_maintenance import EquipmentMaintenanceLog
from app.models.user import User

logger = logging.getLogger(__name__)


async def schedule_equipment_maintenance_reminders(
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    """Scans equipment logs and generates maintenance & hygiene check-in reminders."""
    now = datetime.now()
    two_weeks_ago = now - timedelta(days=14)

    logs_res = await db.execute(
        select(EquipmentMaintenanceLog).where(
            EquipmentMaintenanceLog.user_id == user.id,
            EquipmentMaintenanceLog.created_at >= two_weeks_ago,
        )
    )
    recent_logs = logs_res.scalars().all()

    reminders = []
    if not recent_logs:
        reminders.append(
            "🧼 Рекомендуется провести полную чистку и дезинфекцию основного инвентаря (прошло > 14 дней)."
        )

    logger.info(f"Сформировано {len(reminders)} напоминаний об обслуживании инвентаря для пользователя {user.email}")

    return {
        "status": "success",
        "user_id": str(user.id),
        "recent_maintenance_count": len(recent_logs),
        "reminders": reminders,
    }
