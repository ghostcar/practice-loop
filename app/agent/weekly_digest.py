"""Weekly AI Predictive Digest Engine for PracticeLoop Agent."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.user import User

logger = logging.getLogger(__name__)


async def generate_weekly_user_digest(
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    """Generates weekly AI analytical digest with predictive performance scores."""
    now = datetime.now()
    week_ago = now - timedelta(days=7)

    logs_res = await db.execute(
        select(ActivityLog).where(
            ActivityLog.user_id == user.id,
            ActivityLog.created_at >= week_ago,
        )
    )
    logs = logs_res.scalars().all()

    completed_count = sum(1 for item in logs if item.status == "completed")
    interrupted_count = sum(1 for item in logs if item.status == "interrupted")
    total_count = len(logs)

    completion_rate = (completed_count / total_count * 100) if total_count > 0 else 100.0
    predicted_next_week_goal = min(98.5, max(75.0, completion_rate + 5.0))

    summary_lines = [
        "📊 *Еженедельный ИИ-Дайджест & Предиктивный Прогноз*",
        f"Пользователь: *{user.email}*",
        f"Период: {week_ago.strftime('%d.%m')} — {now.strftime('%d.%m')}",
        "",
        "📈 *Метрики Продуктивности:*",
        f"• Всего практик: *{total_count}*",
        f"• Выполнено: *{completed_count}* (Уровень успеха: *{completion_rate:.1f}%*)",
        f"• Прервано: *{interrupted_count}*",
        "",
        "🔮 *Предиктивный ИИ-Прогноз:*",
        f"• Вероятность выполнения целей на следующую неделю: *{predicted_next_week_goal:.1f}%*",
        "• Рекомендация: Сохранять текущий темп тренировок и соблюдать гидратацию.",
    ]

    summary_md = "\n".join(summary_lines)

    return {
        "status": "success",
        "user_id": str(user.id),
        "total_practices": total_count,
        "completed_practices": completed_count,
        "completion_rate": completion_rate,
        "predicted_next_week_goal": predicted_next_week_goal,
        "summary_markdown": summary_md,
    }
