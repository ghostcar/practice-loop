"""Consent & Boundary Safety Auditor Engine."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.care import CareEntry
from app.models.user import User

logger = logging.getLogger(__name__)


async def audit_user_safety_and_burnout(
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    """Audits opt-in boundaries and fatigue indicators to prevent burnout."""
    now = datetime.now()
    week_ago = now - timedelta(days=7)

    logs_res = await db.execute(
        select(ActivityLog).where(
            ActivityLog.user_id == user.id,
            ActivityLog.created_at >= week_ago,
        )
    )
    logs = logs_res.scalars().all()
    interrupted_count = sum(1 for item in logs if item.status == "interrupted")

    care_res = await db.execute(
        select(CareEntry).where(
            CareEntry.user_id == user.id,
            CareEntry.entry_date >= week_ago.date(),
        )
    )
    care_entries = care_res.scalars().all()
    low_comfort_count = sum(1 for c in care_entries if (c.skin_reaction or 5) <= 2)

    burnout_score = min(100.0, (interrupted_count * 30.0) + (low_comfort_count * 25.0))
    is_freeze_triggered = burnout_score >= 70.0

    safety_notes = []
    if is_freeze_triggered:
        safety_notes.append("🛡️ АКТИВИРОВАНА ЗАЩИТНАЯ ЗАМОРОЗКА НАГРУЗКИ (Индекс выгорания > 70%).")
        safety_notes.append("Рекомендация: 48 часов полного покоя и Aftercare-восстановления.")

    return {
        "status": "success",
        "user_id": str(user.id),
        "burnout_score": burnout_score,
        "is_freeze_triggered": is_freeze_triggered,
        "interrupted_count_7d": interrupted_count,
        "safety_notes": safety_notes,
    }
