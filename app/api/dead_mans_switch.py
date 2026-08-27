"""API Router for Cross-Activity Dead Man's Switch Engine."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.dead_mans_switch import DeadMansSwitchRule
from app.models.user import User
from app.services.dead_mans_switch import (
    evaluate_all_dead_mans_switches,
    record_activity_heartbeat,
)
from app.templates_setup import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/dms", tags=["dead_mans_switch"])
page_router = APIRouter(tags=["dead_mans_switch_page"])


class ConfigureSwitchRequest(BaseModel):
    switch_type: str = Field(..., description="wear_checkin | daily_task | medication | training | general_heartbeat")
    interval_hours: int = Field(default=24, ge=1, le=168)
    grace_period_hours: int = Field(default=2, ge=0, le=48)
    penalty_xp: int = Field(default=50, ge=0)
    action_on_miss: str = Field(default="penalty_xp")
    is_enabled: bool = True


@router.get("/status")
async def get_dms_status_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns all active Dead Man's Switch monitors and their countdowns for user."""
    stmt = (
        select(DeadMansSwitchRule)
        .where(DeadMansSwitchRule.user_id == user.id)
        .order_by(DeadMansSwitchRule.created_at.asc())
    )
    rules = (await db.execute(stmt)).scalars().all()
    now = datetime.now(UTC)

    monitors: list[dict[str, Any]] = []
    for r in rules:
        dl = r.next_deadline_at
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=UTC)

        remaining_seconds = max(0, int((dl - now).total_seconds()))
        monitors.append(
            {
                "id": str(r.id),
                "switch_type": r.switch_type,
                "title": r.title,
                "interval_hours": r.interval_hours,
                "grace_period_hours": r.grace_period_hours,
                "last_heartbeat_at": r.last_heartbeat_at.isoformat(),
                "next_deadline_at": dl.isoformat(),
                "remaining_seconds": remaining_seconds,
                "status": r.status,
                "miss_count": r.miss_count,
                "penalty_xp": r.penalty_xp,
                "is_enabled": r.is_enabled,
            }
        )

    return JSONResponse(
        {
            "status": "success",
            "monitors": monitors,
            "count": len(monitors),
        }
    )


@router.post("/heartbeat")
async def record_heartbeat_endpoint(
    switch_type: str = Form(default="general_heartbeat"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Records a live heartbeat, resetting and extending the deadline."""
    result = await record_activity_heartbeat(db, user.id, switch_type)
    return JSONResponse({"status": "success", **result})


@router.post("/configure")
async def configure_switch_endpoint(
    payload: ConfigureSwitchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates or reconfigures a Dead Man's Switch monitor."""
    stmt = select(DeadMansSwitchRule).where(
        DeadMansSwitchRule.user_id == user.id,
        DeadMansSwitchRule.switch_type == payload.switch_type,
    )
    rule = (await db.execute(stmt)).scalar_one_or_none()

    now = datetime.now(UTC)
    if not rule:
        rule = DeadMansSwitchRule(
            user_id=user.id,
            switch_type=payload.switch_type,
            title=f"{payload.switch_type.replace('_', ' ').title()} Monitor",
            interval_hours=payload.interval_hours,
            grace_period_hours=payload.grace_period_hours,
            last_heartbeat_at=now,
            next_deadline_at=now + timedelta(hours=payload.interval_hours),
            status="active",
            penalty_xp=payload.penalty_xp,
            action_on_miss=payload.action_on_miss,
            is_enabled=payload.is_enabled,
        )
        db.add(rule)
    else:
        rule.interval_hours = payload.interval_hours
        rule.grace_period_hours = payload.grace_period_hours
        rule.penalty_xp = payload.penalty_xp
        rule.action_on_miss = payload.action_on_miss
        rule.is_enabled = payload.is_enabled

    await db.flush()

    return JSONResponse(
        {
            "status": "configured",
            "switch_type": payload.switch_type,
            "interval_hours": payload.interval_hours,
            "next_deadline_at": rule.next_deadline_at.isoformat(),
            "message": f"Dead Man's Switch для {payload.switch_type} успешно настроен.",
        }
    )


@router.post("/evaluate")
async def evaluate_switches_endpoint(
    db: AsyncSession = Depends(get_db),
):
    """Background trigger to evaluate deadlines across all users and issue penalties."""
    results = await evaluate_all_dead_mans_switches(db)
    return JSONResponse({"status": "success", **results})


@page_router.get("/dms", response_class=HTMLResponse)
async def dms_dashboard_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Renders the Dead Man's Switch live monitor cockpit."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    stmt = (
        select(DeadMansSwitchRule)
        .where(DeadMansSwitchRule.user_id == user.id)
        .order_by(DeadMansSwitchRule.created_at.asc())
    )
    rules = (await db.execute(stmt)).scalars().all()
    now = datetime.now(UTC)

    items = []
    for r in rules:
        dl = r.next_deadline_at
        if dl.tzinfo is None:
            dl = dl.replace(tzinfo=UTC)
        rem = max(0, int((dl - now).total_seconds()))
        items.append(
            {
                "id": str(r.id),
                "switch_type": r.switch_type,
                "title": r.title,
                "interval_hours": r.interval_hours,
                "last_heartbeat_at": r.last_heartbeat_at,
                "next_deadline_at": dl,
                "remaining_seconds": rem,
                "status": r.status,
                "penalty_xp": r.penalty_xp,
                "miss_count": r.miss_count,
            }
        )

    return templates.TemplateResponse(
        "dms_dashboard.html",
        {
            "request": request,
            "user": user,
            "rules": items,
            "t": t,
            "theme": theme,
            "locale": locale,
        },
    )
