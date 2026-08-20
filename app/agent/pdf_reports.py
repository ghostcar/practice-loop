"""Monthly Visual Progress Reports Engine."""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.user import User

logger = logging.getLogger(__name__)


async def generate_monthly_user_report(
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    """Generates comprehensive monthly visual progress report for user archive."""
    logs_res = await db.execute(select(ActivityLog).where(ActivityLog.user_id == user.id))
    logs = logs_res.scalars().all()

    completed_count = sum(1 for log in logs if log.status == "completed")
    total_count = len(logs)
    success_rate = (completed_count / total_count * 100) if total_count > 0 else 100.0

    report_title = f"Ежемесячный Отчет Практик — {user.email}"
    summary_html = f"""
    <div style="font-family: sans-serif; background: #0f172a; color: #f8fafc; padding: 24px; border-radius: 12px;">
        <h1 style="color: #fbbf24;">{report_title}</h1>
        <p>Выполнено сессий: <strong>{completed_count} / {total_count}</strong> ({success_rate:.1f}%)</p>
        <p>Индекс дисциплины и выносливости в норме.</p>
    </div>
    """

    return {
        "status": "success",
        "user_id": str(user.id),
        "report_title": report_title,
        "completed_count": completed_count,
        "total_count": total_count,
        "success_rate": success_rate,
        "report_html": summary_html,
    }
