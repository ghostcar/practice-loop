"""Platform Social Leaderboard & Kudos API (Step 90 / ADR-113).

Routes:
- GET  /social/leaderboard — Anonymized Community Leaderboard & Hall of Fame
- POST /social/kudos       — Send encouragement reaction (Kudos)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.platform.social.models import SocialProfile
from app.platform.social.repositories import get_profile
from app.templates_setup import templates

router = APIRouter(tags=["social-leaderboard"])


@router.get("/leaderboard", response_class=HTMLResponse)
async def social_leaderboard_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GET /social/leaderboard — Anonymized Leaderboard & Hall of Fame."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    profile = await get_profile(db, user.id)

    # Fetch top discoverable social profiles
    result = await db.execute(
        select(SocialProfile)
        .where(SocialProfile.discoverable.is_(True))
        .order_by(SocialProfile.created_at.desc())
        .limit(20)
    )
    top_profiles = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="social/leaderboard.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "social",
            "profile": profile,
            "top_profiles": top_profiles,
        },
    )


@router.post("/kudos")
async def send_kudos_endpoint(
    target_alias: str = Form(...),
    reaction: str = Form(default="fire"),  # fire, shield, crown
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """POST /social/kudos — Send Kudos reaction to a community member (Audit A-07 fix)."""
    from app.gamification.handler import get_or_create_progress
    from app.platform.social.models import SocialProfile
    from app.platform.social.repositories import create_encouragement

    reaction_map = {"fire": "motivate", "shield": "support", "crown": "celebrate"}
    if reaction not in reaction_map:
        raise HTTPException(400, "Invalid reaction")

    target_profile = (
        (await db.execute(select(SocialProfile).where(SocialProfile.alias == target_alias.strip()))).scalars().first()
    )

    if target_profile is None:
        raise HTTPException(404, "Social profile not found")
    if target_profile.user_id == user.id:
        raise HTTPException(400, "Cannot send kudos to yourself")

    encouragement = await create_encouragement(
        db,
        user.id,
        "profile",
        target_profile.id,
        reaction_map[reaction],
    )
    if encouragement is not None:
        target_prog = await get_or_create_progress(db, target_profile.user_id)
        target_prog.xp += 10

    return RedirectResponse(url="/social/leaderboard", status_code=303)
