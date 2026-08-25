"""User Availability Calendar API: templates, windows, overrides, availability check.

Thin HTTP wrappers — business logic lives in app/services/calendar_service.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.auth import get_optional_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.schemas.calendar import (
    AvailabilityWindowCreate,
    CalendarOverrideCreate,
    CalendarOverrideOut,
    CalendarTemplateCreate,
    CalendarTemplateOut,
)
from app.services.calendar_service import (
    add_window,
    create_override,
    create_template,
    delete_override,
    delete_template,
    delete_window,
    get_day_schedule,
    is_available,
    list_overrides,
    list_templates,
)
from app.templates_setup import templates
from app.timeutils import local_today

router = APIRouter(prefix="/calendar", tags=["calendar"])

# Re-export utilities used by other services/LLM (kept for backward compatibility).
__all__ = ["router", "is_available", "get_day_schedule"]


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
async def list_templates_api(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await list_templates(db, user.id)


@router.post("/templates", response_model=CalendarTemplateOut)
async def create_template_api(
    data: CalendarTemplateCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await create_template(db, user.id, data)


@router.delete("/templates/{template_id}")
async def delete_template_api(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await delete_template(db, user.id, template_id)
    except ValueError:
        raise HTTPException(404, "Template not found")
    return {"status": "deleted"}


# ═══════════════════════════════════════════════
# Availability Windows CRUD
# ═══════════════════════════════════════════════


@router.post("/templates/{template_id}/windows")
async def add_window_api(
    template_id: uuid.UUID,
    data: AvailabilityWindowCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await add_window(db, user.id, template_id, data)
    except ValueError:
        raise HTTPException(404, "Template not found")


@router.delete("/templates/{template_id}/windows/{window_id}")
async def delete_window_api(
    template_id: uuid.UUID,
    window_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await delete_window(db, user.id, template_id, window_id)
    except ValueError:
        raise HTTPException(404, "Window not found")
    return {"status": "deleted"}


# ═══════════════════════════════════════════════
# Calendar Overrides CRUD
# ═══════════════════════════════════════════════


@router.get("/overrides", response_model=list[CalendarOverrideOut])
async def list_overrides_api(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await list_overrides(db, user.id)


@router.post("/overrides", response_model=CalendarOverrideOut)
async def create_override_api(
    data: CalendarOverrideCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await create_override(db, user.id, data)
    except ValueError:
        raise HTTPException(404, "Template not found")


@router.delete("/overrides/{override_id}")
async def delete_override_api(
    override_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await delete_override(db, user.id, override_id)
    except ValueError:
        raise HTTPException(404, "Override not found")
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
        return RedirectResponse(url="/auth/login", status_code=303)
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    today_schedule = await get_day_schedule(db, user.id, local_today())

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
