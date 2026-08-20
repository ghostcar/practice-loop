"""API Router for Health & Organic Cycle Analytics Dashboard."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.body_cycle import BodyCycleLog
from app.models.care import CareEntry
from app.models.user import User
from app.templates_setup import templates

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/health", tags=["health_dashboard"])


@router.get("/dashboard", response_class=HTMLResponse)
async def health_dashboard_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Health & Organic Cycle Analytics Dashboard UI Page."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    cycles_res = await db.execute(
        select(BodyCycleLog).where(BodyCycleLog.user_id == user.id).order_by(BodyCycleLog.logged_at.desc()).limit(10)
    )
    cycle_logs = cycles_res.scalars().all()

    care_res = await db.execute(
        select(CareEntry).where(CareEntry.user_id == user.id).order_by(CareEntry.created_at.desc()).limit(5)
    )
    care_entries = care_res.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="health_dashboard.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "health_dashboard",
            "cycle_logs": cycle_logs,
            "care_entries": care_entries,
        },
    )
