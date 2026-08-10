"""Dashboard, achievements, notifications, sessions, privacy."""

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.gamification.handler import get_or_create_progress
from app.gamification.xp import xp_progress
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.achievement import Achievement, UserAchievement
from app.models.activity_log import ActivityLog
from app.models.notification import Notification
from app.models.session import ActivitySession
from app.models.user import User
from app.security import ensure_csrf_cookie
from app.templates_setup import templates

router = APIRouter(tags=["dashboard-v2"])


# --- Dashboard ---


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

    progress = await get_or_create_progress(db, user.id)
    level, xp_current, xp_next = xp_progress(progress.xp)

    # Recent logs
    result = await db.execute(
        select(ActivityLog).where(ActivityLog.user_id == user.id).order_by(ActivityLog.created_at.desc()).limit(5)
    )
    recent_logs = result.scalars().all()

    # Active session
    sess_result = await db.execute(
        select(ActivitySession).where(
            ActivitySession.owner_id == user.id,
            ActivitySession.status.in_(["created", "active"]),
        )
    )
    active_session = sess_result.scalar_one_or_none()

    # Notifications count
    notif_count_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            not Notification.is_read,
        )
    )
    unread_notifs = notif_count_result.scalar() or 0

    response = templates.TemplateResponse(
        request=request,
        name="dashboard_v2.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "progress": progress,
            "level": level,
            "xp_current": xp_current,
            "xp_next": xp_next,
            "xp_percent": int(xp_current / max(xp_next, 1) * 100),
            "recent_logs": recent_logs,
            "active_session": active_session,
            "unread_notifs": unread_notifs,
            "tg_bot_username": settings.tg_bot_username,
            "active_nav": "dashboard",
        },
    )
    # Set CSRF cookie ONLY if absent — re-issuing it here after render used to
    # desync the HTML meta token from the browser cookie (audit: P0 login→dashboard 403).
    ensure_csrf_cookie(request, response)
    return response


# --- Achievements ---


@router.get("/achievements", response_class=HTMLResponse)
async def achievements_board(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Achievement board: all (anonymized) + my."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    # All user achievements (anonymized)
    all_result = await db.execute(
        select(UserAchievement, Achievement)
        .join(Achievement, UserAchievement.achievement_id == Achievement.id)
        .where(not UserAchievement.is_hidden)
        .order_by(UserAchievement.obtained_at.desc())
        .limit(30)
    )
    all_achievements = []
    for ua, ach in all_result:
        all_achievements.append(
            {
                "code": ach.code,
                "name": ach.name,
                "description": ach.description,
                "color": ach.color,
                "obtained_at": ua.obtained_at.strftime("%Y-%m-%d") if ua.obtained_at else "",
                "display_name": "Anonymous" if ua.user_id != user.id else "You",
            }
        )

    # My achievements
    my_result = await db.execute(
        select(UserAchievement, Achievement)
        .join(Achievement, UserAchievement.achievement_id == Achievement.id)
        .where(UserAchievement.user_id == user.id)
        .order_by(UserAchievement.obtained_at.desc())
    )
    my_achievements = []
    for ua, ach in my_result:
        my_achievements.append(
            {
                "id": ua.id,
                "code": ach.code,
                "name": ach.name,
                "description": ach.description,
                "color": ach.color,
                "context": ua.context,
                "obtained_at": ua.obtained_at.strftime("%Y-%m-%d") if ua.obtained_at else "",
                "is_hidden": ua.is_hidden,
            }
        )

    return templates.TemplateResponse(
        request=request,
        name="achievements.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "all_achievements": all_achievements,
            "my_achievements": my_achievements,
            "active_nav": "dashboard",
        },
    )


@router.post("/achievements/{ua_id}/hide")
async def hide_achievement(
    request: Request,
    ua_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle achievement visibility on public board."""
    result = await db.execute(select(UserAchievement).where(UserAchievement.id == ua_id))
    ua = result.scalar_one_or_none()
    if ua and ua.user_id != user.id:
        ua = None
    if ua:
        ua.is_hidden = not ua.is_hidden
        db.add(ua)
        await db.flush()
    return RedirectResponse(url="/achievements", status_code=303)


# --- Notifications ---


@router.get("/notifications", response_class=HTMLResponse)
async def notifications_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """In-app notifications list."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    result = await db.execute(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50)
    )
    notifications = result.scalars().all()

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
    """Mark a notification as read."""
    result = await db.execute(select(Notification).where(Notification.id == n_id))
    n = result.scalar_one_or_none()
    if n and n.user_id != user.id:
        n = None
    if n:
        n.is_read = True
        db.add(n)
        await db.flush()
    return RedirectResponse(url="/notifications", status_code=303)


# --- Sessions ---


@router.get("/sessions", response_class=HTMLResponse)
async def sessions_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Session management page."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    result = await db.execute(
        select(ActivitySession)
        .where(ActivitySession.owner_id == user.id)
        .order_by(ActivitySession.created_at.desc())
        .limit(20)
    )
    sessions = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="sessions.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "sessions": sessions,
            "active_nav": "dashboard",
        },
    )


@router.post("/sessions")
async def create_session(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new session."""
    session = ActivitySession(owner_id=user.id, status="created")
    db.add(session)
    await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/start")
async def start_session(
    request: Request,
    s_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a session."""
    result = await db.execute(select(ActivitySession).where(ActivitySession.id == s_id))
    s = result.scalar_one_or_none()
    if s and s.owner_id == user.id:
        s.status = "active"
        s.started_at = datetime.now(UTC)
        db.add(s)
        await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/end")
async def end_session(
    request: Request,
    s_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """End a session."""
    result = await db.execute(select(ActivitySession).where(ActivitySession.id == s_id))
    s = result.scalar_one_or_none()
    if s and s.owner_id == user.id:
        s.status = "ended"
        s.ended_at = datetime.now(UTC)
        db.add(s)
        await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


# --- Privacy ---


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Privacy settings page."""
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
    """Export all user data as JSON."""
    # Gather all data
    progress = await get_or_create_progress(db, user.id)

    logs_result = await db.execute(
        select(ActivityLog).where(ActivityLog.user_id == user.id).order_by(ActivityLog.created_at.desc())
    )
    logs = logs_result.scalars().all()

    user_achs_result = await db.execute(
        select(UserAchievement, Achievement).join(Achievement).where(UserAchievement.user_id == user.id)
    )
    achievements_list = [
        {
            "code": ach.code,
            "name": ach.name,
            "obtained_at": ua.obtained_at.isoformat() if ua.obtained_at else None,
        }
        for ua, ach in user_achs_result
    ]

    data = {
        "exported_at": datetime.now(UTC).isoformat(),
        "user": {
            "email": user.email,
            "locale": user.locale,
            "theme": user.theme,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        },
        "progress": {
            "xp": progress.xp,
            "level": progress.level,
            "streak": progress.current_streak,
            "longest_streak": progress.longest_streak,
            "total_completed": progress.total_completed,
            "total_interrupted": progress.total_interrupted,
        },
        "activities": [
            {
                "id": str(log.id),
                "status": log.status,
                "entity_name": log.selected_entity_name,
                "params": log.selected_params,
                "raw_llm_response": log.raw_llm_response,
                "tokens": log.total_tokens,
                "cost": log.cost,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs[:200]
        ],
        "achievements": achievements_list,
    }

    return PlainTextResponse(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        headers={"Content-Disposition": "attachment; filename=tracker-export.json"},
    )


@router.post("/privacy/delete")
async def delete_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete account and all data. Returns logout redirect."""
    await db.delete(user)
    await db.flush()

    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token")
    return response


# --- Telegram linking ---


@router.post("/profile/telegram-link-code")
async def generate_telegram_link_code(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a 6-character code for linking Telegram. Expires in 30 minutes."""
    code = secrets.token_hex(3).upper()  # 6 hex chars
    user.telegram_link_code = code
    user.telegram_link_code_expires = datetime.now(UTC) + timedelta(minutes=30)
    db.add(user)
    await db.flush()
    return JSONResponse({"code": code, "expires_in_minutes": 30})


@router.get("/profile/telegram-status")
async def telegram_status(
    user: User = Depends(get_current_user),
):
    """Check if Telegram is linked."""
    return JSONResponse(
        {
            "linked": user.telegram_chat_id is not None,
            "code": user.telegram_link_code if not user.telegram_chat_id else None,
        }
    )
