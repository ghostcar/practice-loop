"""Automation Trigger Engine & AI Agent Auto-Generation from History."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.automation import AutomationTrigger
from app.models.care import CareEntry
from app.models.user import User

logger = logging.getLogger(__name__)


async def generate_agent_automation_triggers(
    db: AsyncSession,
    user: User,
) -> dict[str, Any]:
    """AI Agent analyzes 14-day user history and creates tailored automation triggers."""
    now = datetime.now()
    two_weeks_ago = now - timedelta(days=14)

    logs_res = await db.execute(
        select(ActivityLog).where(
            ActivityLog.user_id == user.id,
            ActivityLog.created_at >= two_weeks_ago,
        )
    )
    logs = logs_res.scalars().all()

    interrupted_count = sum(1 for item in logs if item.status == "interrupted")

    care_res = await db.execute(
        select(CareEntry).where(
            CareEntry.user_id == user.id,
            CareEntry.entry_date >= two_weeks_ago.date(),
        )
    )
    care_entries = care_res.scalars().all()

    created_triggers = []

    if interrupted_count >= 1:
        trigger_1 = AutomationTrigger(
            user_id=user.id,
            condition_type="missed_tasks_count",
            threshold_value=2.0,
            action_type="apply_penalty",
            action_params=json.dumps({"xp_penalty": 50, "reason": "Превышение пропущенных практик"}),
            is_active=True,
            is_agent_generated=True,
            reasoning_notes=f"ИИ выявил {interrupted_count} пропусков за 14 дней и создал триггер авто-штрафа.",
        )
        db.add(trigger_1)
        created_triggers.append("missed_tasks_count -> apply_penalty")

    if care_entries:
        trigger_2 = AutomationTrigger(
            user_id=user.id,
            condition_type="high_stress_score",
            threshold_value=7.0,
            action_type="generate_emergency_quest",
            action_params=json.dumps({"quest_type": "care_hydration", "title": "Экстренный Сеанс Восстановления"}),
            is_active=True,
            is_agent_generated=True,
            reasoning_notes="ИИ выявил уязвимость к стрессу и настроил авто-выдачу сеансов ухода.",
        )
        db.add(trigger_2)
        created_triggers.append("high_stress_score -> generate_emergency_quest")

    await db.flush()

    return {
        "status": "success",
        "user_id": str(user.id),
        "triggers_created_count": len(created_triggers),
        "created_triggers": created_triggers,
    }


async def evaluate_user_triggers(
    db: AsyncSession,
    user: User,
    condition_type: str,
    current_value: float,
) -> list[dict[str, Any]]:
    """Evaluates active triggers against current metrics and triggers actions."""
    triggers_res = await db.execute(
        select(AutomationTrigger).where(
            AutomationTrigger.user_id == user.id,
            AutomationTrigger.condition_type == condition_type,
            AutomationTrigger.is_active == True,  # noqa: E712
        )
    )
    triggers = triggers_res.scalars().all()

    executed_actions = []

    for trg in triggers:
        if current_value >= trg.threshold_value:
            params = json.loads(trg.action_params) if trg.action_params else {}
            executed_actions.append(
                {
                    "trigger_id": str(trg.id),
                    "action_type": trg.action_type,
                    "params": params,
                    "executed": True,
                }
            )

    return executed_actions
