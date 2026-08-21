"""Cross-Activity Dead Man's Switch Engine Service."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dead_mans_switch import DeadMansSwitchRule

logger = logging.getLogger(__name__)


async def record_activity_heartbeat(
    db: AsyncSession,
    user_id: uuid.UUID,
    switch_type: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Records user activity (wear checkin, task complete, meds, general heartbeat) and extends deadline."""
    now = datetime.now(UTC)

    # Find matching switch rule
    stmt = select(DeadMansSwitchRule).where(
        DeadMansSwitchRule.user_id == user_id,
        DeadMansSwitchRule.switch_type == switch_type,
    )
    rule = (await db.execute(stmt)).scalar_one_or_none()

    if not rule:
        # Auto-provision switch if not exists
        interval = 24
        if switch_type == "medication":
            interval = 12
        elif switch_type == "daily_task":
            interval = 24
        elif switch_type == "wear_checkin":
            interval = 18

        rule = DeadMansSwitchRule(
            user_id=user_id,
            switch_type=switch_type,
            title=f"{switch_type.replace('_', ' ').title()} Deadline Monitor",
            interval_hours=interval,
            grace_period_hours=2,
            last_heartbeat_at=now,
            next_deadline_at=now + timedelta(hours=interval),
            status="active",
            penalty_xp=50,
            action_on_miss="penalty_xp",
            is_enabled=True,
        )
        db.add(rule)
    else:
        rule.last_heartbeat_at = now
        rule.next_deadline_at = now + timedelta(hours=rule.interval_hours)
        rule.status = "active"
        rule.miss_count = 0

    await db.flush()

    return {
        "status": "heartbeat_recorded",
        "switch_type": switch_type,
        "last_heartbeat_at": rule.last_heartbeat_at.isoformat(),
        "next_deadline_at": rule.next_deadline_at.isoformat(),
        "interval_hours": rule.interval_hours,
        "message": (
            f"Heartbeat принят для {switch_type}. "
            f"Дедлайн продлен до {rule.next_deadline_at.strftime('%Y-%m-%d %H:%M UTC')}."
        ),
    }


async def evaluate_all_dead_mans_switches(db: AsyncSession) -> dict[str, Any]:
    """Checks all active Dead Man's Switch rules and applies warnings / penalty escalations on misses."""
    now = datetime.now(UTC)
    stmt = select(DeadMansSwitchRule).where(
        DeadMansSwitchRule.is_enabled == True,  # noqa: E712
        DeadMansSwitchRule.status.in_(["active", "warning"]),
    )
    rules = (await db.execute(stmt)).scalars().all()

    violations = []
    warnings_list = []

    for r in rules:
        dl = r.next_deadline_at
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=UTC)

        grace_limit = dl + timedelta(hours=r.grace_period_hours)

        if now > grace_limit:
            # Overdue beyond grace period -> Penalty
            r.status = "triggered_penalty"
            r.miss_count += 1
            violations.append(
                {
                    "user_id": str(r.user_id),
                    "switch_type": r.switch_type,
                    "deadline": dl.isoformat(),
                    "miss_count": r.miss_count,
                    "penalty_xp": r.penalty_xp,
                }
            )
            logger.warning(f"Dead Man's Switch TRIGGERED for user {r.user_id}, switch: {r.switch_type}")
        elif now > dl:
            # Within grace period -> Warning
            if r.status != "warning":
                r.status = "warning"
                warnings_list.append(
                    {
                        "user_id": str(r.user_id),
                        "switch_type": r.switch_type,
                        "deadline": dl.isoformat(),
                    }
                )

    await db.flush()

    return {
        "checked_rules_count": len(rules),
        "violations_count": len(violations),
        "warnings_count": len(warnings_list),
        "violations": violations,
        "warnings": warnings_list,
    }
