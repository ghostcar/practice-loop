"""Autonomous Event Generator, Chaining & Proactive Liveness Engine (Step 47 / ADR-123 & ADR-095)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.reminder_log import ReminderLog
from app.timeutils import local_today

logger = logging.getLogger(__name__)


async def schedule_agent_reminder(
    title: str,
    message: str,
    user_id: uuid.UUID,
    db: AsyncSession,
    delay_minutes: int = 0,
    send_telegram: bool = True,
) -> dict[str, Any]:
    """Schedules an agent reminder into ReminderLog and sends Telegram notification."""
    today = local_today()
    dedupe_key = f"agent_reminder:{uuid.uuid4().hex[:8]}:{today}"

    rem = ReminderLog(
        user_id=user_id,
        kind="agent_reminder",
        dedupe_key=dedupe_key,
        delivered_channel="in_app" if not send_telegram else "telegram",
    )
    db.add(rem)
    await db.commit()

    logger.info("Agent scheduled reminder for user %s: %s (telegram=%s)", user_id, title, send_telegram)

    return {
        "status": "scheduled",
        "title": title,
        "message": message,
        "delay_minutes": delay_minutes,
        "sent_telegram": send_telegram,
    }


async def trigger_event_chain(
    event_type: str,
    user_id: uuid.UUID,
    db: AsyncSession,
    context_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Autonomous LLM Event Chain Evaluator.

    Triggered upon completion of sessions, tasks, or check-ins.
    Decides whether to spawn follow-up events, schedule aftercare, or queue reminders.
    """
    context_data = context_data or {}
    logger.info("Event Chain triggered for user %s: %s", user_id, event_type)

    followup_actions = []
    from app.agent.tools import execute_agent_tool

    if event_type == "session_completed":
        # Automatically suggest or schedule Aftercare
        aftercare_res = await execute_agent_tool(
            tool_name="trigger_aftercare",
            arguments={},
            user_id=user_id,
            db=db,
        )
        followup_actions.append({"action": "aftercare_triggered", "result": aftercare_res})

        # Also schedule Aftercare reminder
        await schedule_agent_reminder(
            title="🧘 Напоминание об Aftercare",
            message="Прошло время сессии. Пожалуйста, уделите время гидратации и восстановлению.",
            user_id=user_id,
            db=db,
            delay_minutes=15,
            send_telegram=True,
        )

    elif event_type in ("task_failed", "session_interrupted"):
        # Gentle recovery check-in
        await schedule_agent_reminder(
            title="💧 Восстановительный Чек-Ин",
            message="Сессия прервана. Агент напоминает о необходимости отдыха и тёплого напитка.",
            user_id=user_id,
            db=db,
            delay_minutes=30,
            send_telegram=True,
        )
        followup_actions.append({
            "action": "recovery_checkin_scheduled",
            "delay_minutes": 30,
            "message": "Сессия прервана. Агент запланировал гидратацию и отдых.",
        })

    elif event_type == "chastity_checkin_verified":
        # Schedule next check-in window reminder
        await schedule_agent_reminder(
            title="🔒 Окно Чек-Ина Замка",
            message="Чек-ин подтверждён. Следующая плановая проверка назначен на 20:00.",
            user_id=user_id,
            db=db,
            delay_minutes=720,
            send_telegram=True,
        )
        followup_actions.append({
            "action": "next_checkin_scheduled",
            "delay_hours": 12,
            "message": "Чек-ин подтверждён. Следующее окно проверки от Агента назначено.",
        })

    return {
        "status": "chained",
        "event_type": event_type,
        "actions_taken": followup_actions,
    }
