"""Dashboard, achievements, notifications, privacy (ADR-156/167).

All business logic lives in app.services.dashboard_service (ADR-167).
This file contains only HTTP parsing, response building, and dependency injection.
"""

from __future__ import annotations

import json
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.security import ensure_csrf_cookie
from app.services import dashboard_service as svc
from app.templates_setup import templates

router = APIRouter(tags=["dashboard-v2"])
session_json_router = APIRouter(prefix="/api/v2/sessions", tags=["sessions"])


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard with real stats."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    ctx = await svc.get_dashboard_context(db, user, locale)

    response = templates.TemplateResponse(
        request=request,
        name="dashboard_v2.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "dashboard",
            **ctx,
        },
    )
    ensure_csrf_cookie(request, response)
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Achievements
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/achievements", response_class=HTMLResponse)
async def achievements_board(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    ctx = await svc.get_achievements_context(db, user.id)

    return templates.TemplateResponse(
        request=request,
        name="achievements.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "dashboard",
            **ctx,
        },
    )


@router.post("/achievements/{ua_id}/hide")
async def hide_achievement(
    request: Request,
    ua_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.toggle_achievement_visibility(db, ua_id, user.id)
    return RedirectResponse(url="/achievements", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/notifications", response_class=HTMLResponse)
async def notifications_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    notifications = await svc.get_notifications(db, user.id)

    return templates.TemplateResponse(
        request=request,
        name="notifications.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "notifications": notifications,
            "active_nav": "dashboard",
        },
    )


@router.post("/notifications/{n_id}/read")
async def mark_read(
    request: Request,
    n_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.mark_notification_read(db, n_id, user.id)
    return RedirectResponse(url="/notifications", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# Privacy
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="privacy.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "dashboard",
        },
    )


@router.get("/privacy/export")
async def export_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.personal_export import build_personal_export

    data = await build_personal_export(db, user)
    return PlainTextResponse(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        headers={"Content-Disposition": "attachment; filename=tracker-export.json"},
    )


@router.post("/privacy/delete")
async def delete_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await db.delete(user)
    await db.flush()

    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token")
    return response


# ─────────────────────────────────────────────────────────────────────────────
# Telegram linking
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/profile/telegram-link-code")
async def generate_telegram_link_code(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await svc.generate_tg_link_code(db, user)
    return JSONResponse(result)


@router.get("/profile/telegram-status")
async def telegram_status(
    user: User = Depends(get_current_user),
):
    return JSONResponse(svc.get_tg_link_status(user))
