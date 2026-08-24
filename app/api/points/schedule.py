"""Schedule — today schedule, CRUD rules."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.life import ScheduleRule
from app.models.user import User
from app.schemas.points_v2 import ScheduleRuleCreate, ScheduleRuleOut

router = APIRouter(tags=["v2"])


@router.get("/schedule/today")
async def get_today_schedule(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get schedule for today (returns rules for this day of week)."""
    today = datetime.now(UTC)
    dow = today.weekday()  # 0=Mon
    result = await db.execute(
        select(ScheduleRule)
        .where(
            ScheduleRule.user_id == user.id,
            ScheduleRule.is_active.is_(True),
            (ScheduleRule.day_of_week == dow) | (ScheduleRule.day_of_week == 7),
        )
        .order_by(ScheduleRule.start_time)
    )
    rules = result.scalars().all()
    out = []
    for r in rules:
        d = ScheduleRuleOut.model_validate(r).model_dump()
        d["day_of_week"] = r.day_of_week
        d["start_time"] = r.start_time.strftime("%H:%M") if r.start_time else None
        d["end_time"] = r.end_time.strftime("%H:%M") if r.end_time else None
        if r.entity:
            d["entity_name"] = r.entity.real_name
        out.append(d)
    return out


@router.post("/schedule/rules", response_model=ScheduleRuleOut)
async def create_schedule_rule(
    data: ScheduleRuleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rule = ScheduleRule(user_id=user.id, **data.model_dump())
    db.add(rule)
    await db.refresh(rule)
    return ScheduleRuleOut.model_validate(rule)


@router.delete("/schedule/rules/{rule_id}")
async def delete_schedule_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(ScheduleRule).where(ScheduleRule.id == rule_id, ScheduleRule.user_id == user.id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")
    await db.delete(rule)
    return {"status": "deleted"}
