"""User Availability Calendar API: templates, windows, overrides, availability check."""

import uuid
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.auth import get_optional_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.calendar import AvailabilityWindow, CalendarOverride, CalendarTemplate
from app.models.user import User
from app.schemas.calendar import (
    AvailabilityWindowCreate,
    CalendarOverrideCreate,
    CalendarOverrideOut,
    CalendarTemplateCreate,
    CalendarTemplateOut,
    DaySchedule,
)
from app.templates_setup import templates

router = APIRouter(prefix="/calendar", tags=["calendar"])


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
# Availability check endpoint
# ═══════════════════════════════════════════════


@router.get("/check")
async def check_availability(
    target_time: str = Query(description="ISO datetime"),
    duration: int = Query(default=60, ge=1, le=1440),
    intensity: str = Query(default="active"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Check if the user is available for an activity at the specified time."""
    try:
        dt = datetime.fromisoformat(target_time)
    except ValueError:
        raise HTTPException(400, "Invalid datetime format. Use ISO format.") from None

    available, policy, window_label, reason = await is_available(db, user.id, dt, duration, intensity)
    return {
        "available": available,
        "policy": policy,
        "window_label": window_label,
        "reason": reason,
    }


# ═══════════════════════════════════════════════
# Calendar Templates CRUD
# ═══════════════════════════════════════════════


@router.get("/templates", response_model=list[CalendarTemplateOut])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CalendarTemplate)
        .where(CalendarTemplate.user_id == user.id)
        .order_by(CalendarTemplate.is_default.desc(), CalendarTemplate.created_at)
    )
    return [CalendarTemplateOut.model_validate(t) for t in result.scalars().all()]


@router.post("/templates", response_model=CalendarTemplateOut)
async def create_template(
    data: CalendarTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # If setting as default, unset others
    if data.is_default:
        await db.execute(
            select(CalendarTemplate).where(
                CalendarTemplate.user_id == user.id,
                CalendarTemplate.is_default.is_(True),
            )
        )
        existing_defaults = (
            (
                await db.execute(
                    select(CalendarTemplate).where(
                        CalendarTemplate.user_id == user.id,
                        CalendarTemplate.is_default.is_(True),
                    )
                )
            )
            .scalars()
            .all()
        )
        for t in existing_defaults:
            t.is_default = False

    tpl = CalendarTemplate(user_id=user.id, name=data.name, is_default=data.is_default)
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

    await db.commit()
    await db.refresh(tpl)
    return CalendarTemplateOut.model_validate(tpl)


@router.delete("/templates/{template_id}")
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CalendarTemplate).where(
            CalendarTemplate.id == template_id,
            CalendarTemplate.user_id == user.id,
        )
    )
    tpl = result.scalar_one_or_none()
    if not tpl:
        raise HTTPException(404, "Template not found")
    await db.delete(tpl)
    await db.commit()
    return {"status": "deleted"}


# ═══════════════════════════════════════════════
# Availability Windows CRUD
# ═══════════════════════════════════════════════


@router.post("/templates/{template_id}/windows")
async def add_window(
    template_id: uuid.UUID,
    data: AvailabilityWindowCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify ownership
    tpl_result = await db.execute(
        select(CalendarTemplate).where(
            CalendarTemplate.id == template_id,
            CalendarTemplate.user_id == user.id,
        )
    )
    if not tpl_result.scalar_one_or_none():
        raise HTTPException(404, "Template not found")

    window = AvailabilityWindow(template_id=template_id, **data.model_dump())
    db.add(window)
    await db.commit()
    await db.refresh(window)
    return {"status": "created", "id": str(window.id)}


@router.delete("/templates/{template_id}/windows/{window_id}")
async def delete_window(
    template_id: uuid.UUID,
    window_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(AvailabilityWindow)
        .join(CalendarTemplate)
        .where(
            AvailabilityWindow.id == window_id,
            AvailabilityWindow.template_id == template_id,
            CalendarTemplate.user_id == user.id,
        )
    )
    w = result.scalar_one_or_none()
    if not w:
        raise HTTPException(404, "Window not found")
    await db.delete(w)
    await db.commit()
    return {"status": "deleted"}


# ═══════════════════════════════════════════════
# Calendar Overrides CRUD
# ═══════════════════════════════════════════════


@router.get("/overrides", response_model=list[CalendarOverrideOut])
async def list_overrides(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CalendarOverride).where(CalendarOverride.user_id == user.id).order_by(CalendarOverride.start_date.desc())
    )
    out = []
    for o in result.scalars().all():
        d = CalendarOverrideOut.model_validate(o)
        if o.template:
            d.template_name = o.template.name
        out.append(d)
    return out


@router.post("/overrides", response_model=CalendarOverrideOut)
async def create_override(
    data: CalendarOverrideCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Verify template exists and user owns it
    tpl = await db.get(CalendarTemplate, data.template_id)
    if not tpl:
        raise HTTPException(404, "Template not found")
    if tpl.user_id != user.id:
        raise HTTPException(404, "Template not found")

    override = CalendarOverride(
        user_id=user.id,
        template_id=data.template_id,
        start_date=data.start_date,
        end_date=data.end_date,
        label=data.label,
    )
    db.add(override)
    await db.commit()
    await db.refresh(override)
    out = CalendarOverrideOut.model_validate(override)
    out.template_name = tpl.name
    return out


@router.delete("/overrides/{override_id}")
async def delete_override(
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(CalendarOverride).where(
            CalendarOverride.id == override_id,
            CalendarOverride.user_id == user.id,
        )
    )
    o = result.scalar_one_or_none()
    if not o:
        raise HTTPException(404, "Override not found")
    await db.delete(o)
    await db.commit()
    return {"status": "deleted"}


# ═══════════════════════════════════════════════
# Web UI
# ═══════════════════════════════════════════════


@router.get("", response_class=HTMLResponse)
async def calendar_page(
    request: Request,
    user: User | None = Depends(get_optional_user),
    db: AsyncSession = Depends(get_db),
):
    if not user:
        from fastapi.responses import RedirectResponse

        return RedirectResponse(url="/auth/login", status_code=303)
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    # Get today's schedule
    today_schedule = await get_day_schedule(db, user.id, date.today())

    return templates.TemplateResponse(
        request=request,
        name="calendar.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "today_schedule": today_schedule,
        },
    )
