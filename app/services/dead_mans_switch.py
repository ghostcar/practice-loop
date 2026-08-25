"""Cross-Activity Dead Man's Switch Engine Service (R8.1 audit)."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dead_mans_switch import DeadMansSwitchRule
from app.services.capability import ActorContext

logger = logging.getLogger(__name__)


async def record_activity_heartbeat(
    db: AsyncSession,
    user_id: uuid.UUID,
    switch_type: str,
    note: str | None = None,
    actor: ActorContext | None = None,
) -> dict[str, Any]:
    """Records user activity and extends deadline (R8.1 audit)."""
    _ctx = actor or ActorContext(actor_id=user_id, actor_type="human", source="web")
    now = datetime.now(UTC)

    stmt = select(DeadMansSwitchRule).where(
        DeadMansSwitchRule.user_id == user_id,
        DeadMansSwitchRule.switch_type == switch_type,
    )
    rule = (await db.execute(stmt)).scalar_one_or_none()

    if not rule:
        interval = {"medication": 12, "daily_task": 24, "wear_checkin": 18}.get(switch_type, 24)
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
    logger.debug("DMS heartbeat %s/%s by actor %s", user_id, switch_type, _ctx.actor_id)

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
    """Checks all active DMS rules and applies warnings / penalty escalations.

    This is a batch operation (no single actor), logged as system scheduler.
    """
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
            logger.warning("DMS TRIGGERED for user %s, switch: %s", r.user_id, r.switch_type)
        elif now > dl:
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
