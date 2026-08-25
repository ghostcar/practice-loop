"""Calendar Service — business logic extracted from app.api.calendar.

Covers: availability check (used by LLM + tasks), day schedule resolution,
calendar template / availability window / override CRUD.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.calendar import AvailabilityWindow, CalendarOverride, CalendarTemplate
from app.schemas.calendar import (
    CalendarOverrideOut,
    CalendarTemplateOut,
    DaySchedule,
)

# ═══════════════════════════════════════════════
# Availability check utility (also used by LLM)
# ═══════════════════════════════════════════════


async def is_available(
    db: AsyncSession,
    user_id: uuid.UUID,
    target_time: datetime,
    duration_minutes: int = 60,
    intensity: str = "active",
) -> tuple[bool, str | None, str | None, str | None]:
    """Check if user is available for an activity at the given time.

    Returns: (available, policy, window_label, template_name)
    """
    target_date = target_time.date()
    end_time = (target_time + timedelta(minutes=duration_minutes)).time()

    # 1. Check for CalendarOverride covering this date
    override_result = await db.execute(
        select(CalendarOverride).where(
            CalendarOverride.user_id == user_id,
            CalendarOverride.start_date <= target_date,
            CalendarOverride.end_date >= target_date,
        )
    )
    override = override_result.scalar_one_or_none()

    if override:
        template_id = override.template_id
    else:
        # 2. Default template
        tpl_result = await db.execute(
            select(CalendarTemplate).where(
                CalendarTemplate.user_id == user_id,
                CalendarTemplate.is_default.is_(True),
            )
        )
        default_tpl = tpl_result.scalar_one_or_none()
        if not default_tpl:
            return True, "allowed", "free", None  # No template = always available
        template_id = default_tpl.id

    # 3. Find matching windows
    dow = target_time.weekday()
    window_result = await db.execute(
        select(AvailabilityWindow).where(
            AvailabilityWindow.template_id == template_id,
            or_(
                AvailabilityWindow.day_of_week == dow,
                AvailabilityWindow.day_of_week == 7,  # Every day
            ),
            AvailabilityWindow.start_time <= end_time,
            AvailabilityWindow.end_time >= target_time.time(),
        )
    )
    window = window_result.scalar_one_or_none()

    if not window:
        # No matching window = default to disallowed
        return False, "disallowed", None, None

    # 4. Evaluate policy
    if window.policy == "disallowed":
        return False, window.policy, window.label, None
    elif window.policy == "passive_only":
        ok = intensity == "passive"
        reason = None if ok else "Activity requires 'active' intensity but window is passive_only"
        return ok, window.policy, window.label, reason
    else:  # allowed
        return True, window.policy, window.label, None


async def get_day_schedule(db: AsyncSession, user_id: uuid.UUID, target_date: date) -> DaySchedule:
    """Get the full resolved schedule for a day (for LLM context injection)."""
    override_result = await db.execute(
        select(CalendarOverride).where(
            CalendarOverride.user_id == user_id,
            CalendarOverride.start_date <= target_date,
            CalendarOverride.end_date >= target_date,
        )
    )
    override = override_result.scalar_one_or_none()

    if override:
        template_id = override.template_id
        tpl_name = override.label or "Override"
    else:
        tpl_result = await db.execute(
            select(CalendarTemplate).where(
                CalendarTemplate.user_id == user_id,
                CalendarTemplate.is_default.is_(True),
            )
        )
        default_tpl = tpl_result.scalar_one_or_none()
        if not default_tpl:
            return DaySchedule(date=target_date, template_name="none", windows=[])
        template_id = default_tpl.id
        tpl_name = default_tpl.name

    dow = target_date.weekday()
    window_result = await db.execute(
        select(AvailabilityWindow)
        .where(
            AvailabilityWindow.template_id == template_id,
            or_(AvailabilityWindow.day_of_week == dow, AvailabilityWindow.day_of_week == 7),
        )
        .order_by(AvailabilityWindow.start_time)
    )
    windows = window_result.scalars().all()

    return DaySchedule(
        date=target_date,
        template_name=tpl_name,
        windows=[
            {
                "start": w.start_time.strftime("%H:%M"),
                "end": w.end_time.strftime("%H:%M"),
                "label": w.label,
                "policy": w.policy,
            }
            for w in windows
        ],
    )


# ═══════════════════════════════════════════════
# Calendar Templates CRUD
# ═══════════════════════════════════════════════


async def list_templates(db: AsyncSession, user_id: uuid.UUID) -> list[CalendarTemplateOut]:
    result = await db.execute(
        select(CalendarTemplate)
        .where(CalendarTemplate.user_id == user_id)
        .order_by(CalendarTemplate.is_default.desc(), CalendarTemplate.created_at)
    )
    return [CalendarTemplateOut.model_validate(t) for t in result.scalars().all()]


async def create_template(
    db: AsyncSession,
    user_id: uuid.UUID,
    data,
) -> CalendarTemplateOut:
    """Create a calendar template with its availability windows."""
    # If setting as default, unset others
    if data.is_default:
        existing_defaults = (
            (
                await db.execute(
                    select(CalendarTemplate).where(
                        CalendarTemplate.user_id == user_id,
                        CalendarTemplate.is_default.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        for t in existing_defaults:
            t.is_default = False

    tpl = CalendarTemplate(user_id=user_id, name=data.name, is_default=data.is_default)
    db.add(tpl)
    await db.flush()

    for w in data.windows:
        window = AvailabilityWindow(
            template_id=tpl.id,
            day_of_week=w.day_of_week,
            start_time=w.start_time,
            end_time=w.end_time,
            label=w.label,
            policy=w.policy,
        )
        db.add(window)
        await db.flush()
    await db.refresh(tpl)
    return CalendarTemplateOut.model_validate(tpl)


async def delete_template(db: AsyncSession, user_id: uuid.UUID, template_id: uuid.UUID) -> None:
    result = await db.execute(
        select(CalendarTemplate).where(
            CalendarTemplate.id == template_id,
            CalendarTemplate.user_id == user_id,
        )
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise ValueError("Template not found")
    await db.delete(tpl)


# ═══════════════════════════════════════════════
# Availability Windows CRUD
# ═══════════════════════════════════════════════


async def add_window(
    db: AsyncSession,
    user_id: uuid.UUID,
    template_id: uuid.UUID,
    data,
) -> dict:
    """Add an availability window to a template (ownership-checked)."""
    tpl_result = await db.execute(
        select(CalendarTemplate).where(
            CalendarTemplate.id == template_id,
            CalendarTemplate.user_id == user_id,
        )
    )
    if not tpl_result.scalar_one_or_none():
        raise ValueError("Template not found")

    window = AvailabilityWindow(template_id=template_id, **data.model_dump())
    db.add(window)
    await db.flush()
    await db.refresh(window)
    return {"status": "created", "id": str(window.id)}


async def delete_window(
    db: AsyncSession,
    user_id: uuid.UUID,
    template_id: uuid.UUID,
    window_id: uuid.UUID,
) -> None:
    result = await db.execute(
        select(AvailabilityWindow)
        .join(CalendarTemplate)
        .where(
            AvailabilityWindow.id == window_id,
            AvailabilityWindow.template_id == template_id,
            CalendarTemplate.user_id == user_id,
        )
    )
    w = result.scalar_one_or_none()
    if not w:
        raise ValueError("Window not found")
    await db.delete(w)


# ═══════════════════════════════════════════════
# Calendar Overrides CRUD
# ═══════════════════════════════════════════════


async def list_overrides(db: AsyncSession, user_id: uuid.UUID) -> list[CalendarOverrideOut]:
    result = await db.execute(
        select(CalendarOverride).where(CalendarOverride.user_id == user_id).order_by(CalendarOverride.start_date.desc())
    )
    out = []
    for o in result.scalars().all():
        d = CalendarOverrideOut.model_validate(o)
        if o.template:
            d.template_name = o.template.name
        out.append(d)
    return out


async def create_override(
    db: AsyncSession,
    user_id: uuid.UUID,
    data,
) -> CalendarOverrideOut:
    """Create a calendar override (template ownership-checked)."""
    tpl = await db.get(CalendarTemplate, data.template_id)
    if not tpl or tpl.user_id != user_id:
        raise ValueError("Template not found")

    override = CalendarOverride(
        user_id=user_id,
        template_id=data.template_id,
        start_date=data.start_date,
        end_date=data.end_date,
        label=data.label,
    )
    db.add(override)
    await db.flush()
    await db.refresh(override)
    out = CalendarOverrideOut.model_validate(override)
    out.template_name = tpl.name
    return out


async def delete_override(db: AsyncSession, user_id: uuid.UUID, override_id: uuid.UUID) -> None:
    result = await db.execute(
        select(CalendarOverride).where(
            CalendarOverride.id == override_id,
            CalendarOverride.user_id == user_id,
        )
    )
    o = result.scalar_one_or_none()
    if not o:
        raise ValueError("Override not found")
    await db.delete(o)
