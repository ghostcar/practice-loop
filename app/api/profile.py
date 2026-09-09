"""User Profile — dedicated profile page with stats and editable fields.

Separated from settings (app preferences) and account (read-only stub).
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.gamification.handler import get_or_create_progress
from app.gamification.xp import xp_progress
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.activity_log import ActivityLog
from app.models.session import ActivitySession
from app.models.user import User
from app.security import ensure_csrf_cookie
from app.services import telegram_link_service as tg_link_svc
from app.templates_setup import templates

router = APIRouter(tags=["profile"])

# Timezone presets for the picker
_TIMEZONE_PRESETS = [
    ("UTC", "UTC"),
    ("Europe/Moscow", "Москва (MSK)"),
    ("Europe/London", "London (GMT/BST)"),
    ("Europe/Berlin", "Berlin (CET/CEST)"),
    ("Europe/Paris", "Paris (CET/CEST)"),
    ("America/New_York", "New York (EST/EDT)"),
    ("America/Chicago", "Chicago (CST/CDT)"),
    ("America/Los_Angeles", "Los Angeles (PST/PDT)"),
    ("Asia/Dubai", "Dubai (GST)"),
    ("Asia/Tokyo", "Tokyo (JST)"),
    ("Asia/Shanghai", "Shanghai (CST)"),
    ("Australia/Sydney", "Sydney (AEST/AEDT)"),
]

# Locale display names
_LOCALE_LABELS = {
    "en": "English",
    "ru": "Русский",
}

# Subscription tier labels
_TIER_LABELS = {
    "free": "Free",
    "pro": "Pro",
    "premium": "Premium",
}


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full user profile page with stats and editable fields."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    # Gamification stats
    progress = await get_or_create_progress(db, user.id)
    level, xp_current, xp_next = xp_progress(progress.xp)

    # Total completed sessions
    sess_count_result = await db.execute(
        select(func.count(ActivitySession.id)).where(
            ActivitySession.owner_id == user.id,
            ActivitySession.status.in_(["completed", "active"]),
        )
    )
    total_sessions = sess_count_result.scalar() or 0

    # Total completed tasks
    completed_result = await db.execute(
        select(func.count(ActivityLog.id)).where(
            ActivityLog.user_id == user.id,
            ActivityLog.status == "completed",
        )
    )
    total_completed = completed_result.scalar() or 0

    # Total interrupted tasks
    interrupted_result = await db.execute(
        select(func.count(ActivityLog.id)).where(
            ActivityLog.user_id == user.id,
            ActivityLog.status == "interrupted",
        )
    )
    total_interrupted = interrupted_result.scalar() or 0

    # Account age
    account_age_days = (datetime.now(UTC) - user.created_at.replace(tzinfo=UTC)).days if user.created_at else 0

    # Last activity
    last_log_result = await db.execute(
        select(ActivityLog.created_at)
        .where(ActivityLog.user_id == user.id)
        .order_by(ActivityLog.created_at.desc())
        .limit(1)
    )
    last_activity = last_log_result.scalar_one_or_none()

    # Telegram status & linking
    tg_linked = user.telegram_chat_id is not None
    tg_bot_user = settings.tg_bot_username.lstrip("@")
    tg_link_code = ""
    tg_deep_link = ""
    if not tg_linked:
        tg_link_code, tg_deep_link = await tg_link_svc.ensure_active_link_code(db, user)

    # PIN status
    has_pin = user.pin_hash is not None

    # Enabled modules count
    from app.prefs import sanitize_prefs

    enabled_modules = sanitize_prefs(user.prefs).get("enabled_modules", [])

    response = templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "profile",
            "progress": progress,
            "level": level,
            "xp_current": xp_current,
            "xp_next": xp_next,
            "xp_percent": int(xp_current / max(xp_next, 1) * 100),
            "total_sessions": total_sessions,
            "total_completed": total_completed,
            "total_interrupted": total_interrupted,
            "account_age_days": account_age_days,
            "last_activity": last_activity,
            "tg_linked": tg_linked,
            "tg_bot_username": tg_bot_user,
            "tg_link_code": tg_link_code,
            "tg_deep_link": tg_deep_link,
            "has_pin": has_pin,
            "enabled_modules_count": len(enabled_modules),
            "timezone_presets": _TIMEZONE_PRESETS,
            "locale_labels": _LOCALE_LABELS,
            "tier_label": _TIER_LABELS.get(user.subscription_tier, user.subscription_tier),
        },
    )
    ensure_csrf_cookie(request, response)
    return response


@router.get("/profile/telegram-qr")
async def profile_telegram_qr(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Render QR-code SVG for Telegram 1-click deep linking."""
    _code, deep_link = await tg_link_svc.ensure_active_link_code(db, user)
    await db.flush()
    svg = tg_link_svc.generate_telegram_qr_svg(deep_link)
    return Response(
        content=svg,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store, max-age=0"},
    )


@router.post("/profile/telegram-link-by-otp")
async def profile_link_telegram_otp(
    otp_code: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Link Telegram account using 6-digit OTP generated by the bot (/connect)."""
    from urllib.parse import quote

    ok, msg, _chat_id = await tg_link_svc.link_user_by_bot_otp(db, user, otp_code)
    if not ok:
        return RedirectResponse(
            url=f"/profile?status=tg_otp_error&error_msg={quote(msg)}",
            status_code=303,
        )

    await db.flush()

    # Best-effort welcome notification
    from app.telegram.bot import send_telegram_notification

    await send_telegram_notification(
        user.id,
        "🎉 Аккаунт успешно привязан через портал! Главное меню активировано.",
    )

    return RedirectResponse(url="/profile?status=tg_linked", status_code=303)


@router.post("/profile/telegram-unlink")
async def profile_unlink_telegram(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unlink Telegram account."""
    old_chat = await tg_link_svc.unlink_user_telegram(db, user)
    await db.flush()

    if old_chat:
        import contextlib
        with contextlib.suppress(Exception):
            from app.telegram.bot import bot
            if bot:
                await bot.send_message(
                    chat_id=old_chat,
                    text="ℹ️ Ваш Telegram-аккаунт был отвязан от портала PracticeLoop.",
                )

    return RedirectResponse(url="/profile?status=tg_unlinked", status_code=303)


@router.post("/profile/update")
async def update_profile(
    request: Request,
    display_name: str = Form(default=""),
    locale: str = Form(default="en"),
    timezone: str = Form(default="UTC"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update profile fields (display_name, locale, timezone)."""
    # Validate locale
    if locale not in ("en", "ru"):
        locale = "en"

    # Validate timezone (accept freeform but warn if not in presets)
    user.display_name = display_name.strip()[:100] or None
    user.locale = locale
    user.timezone = timezone.strip()[:64] or "UTC"
    db.add(user)
    await db.flush()

    return RedirectResponse(url="/profile?status=updated", status_code=303)
