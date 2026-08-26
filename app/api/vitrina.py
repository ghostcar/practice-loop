"""Public Vitrina (Showcase) — anonymized community board, no auth required (ADR-183).

The vitrina exposes ONLY aggregated / anonymized data:
- top participants by real gamification metrics (XP, streak, compliance) from UserProgress,
- recent community achievements (UserAchievement, not hidden),
- community-wide counters (profiles, publications, kudos).

No emails, no user ids, no private domain data. Respects SocialProfile.discoverable.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale
from app.models.achievement import Achievement, UserAchievement
from app.models.progress import UserProgress
from app.platform.social.models import SocialEncouragement, SocialProfile, SocialPublication
from app.templates_setup import templates

public_router = APIRouter(tags=["vitrina-public"])


@public_router.get("/vitrina", response_class=HTMLResponse)
async def public_vitrina(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Public anonymized showcase page (no auth)."""
    locale = detect_locale(request, "ru")
    t = get_translations(locale)

    # ── Top participants: discoverable profiles joined with real gamification state ──
    top_result = await db.execute(
        select(SocialProfile, UserProgress)
        .join(UserProgress, UserProgress.user_id == SocialProfile.user_id, isouter=True)
        .where(SocialProfile.discoverable.is_(True))
        .order_by(
            func.coalesce(UserProgress.xp, 0).desc(),
            func.coalesce(UserProgress.current_streak, 0).desc(),
        )
        .limit(10)
    )
    top_participants = []
    for prof, progress in top_result:
        completed = progress.total_completed if progress else 0
        interrupted = progress.total_interrupted if progress else 0
        denominator = completed + interrupted
        compliance = round(completed / denominator * 100) if denominator else 0
        top_participants.append(
            {
                "alias": prof.alias,
                "bio": prof.bio,
                "xp": progress.xp if progress else 0,
                "level": progress.level if progress else 1,
                "streak": progress.current_streak if progress else 0,
                "compliance": compliance,
            }
        )

    # ── Recent community achievements (anonymized, hidden excluded) ──
    ach_result = await db.execute(
        select(UserAchievement, Achievement)
        .join(Achievement, UserAchievement.achievement_id == Achievement.id)
        .where(not UserAchievement.is_hidden)
        .order_by(UserAchievement.obtained_at.desc())
        .limit(12)
    )
    recent_achievements = [
        {
            "name": ach.name,
            "description": ach.description,
            "color": ach.color,
            "obtained_at": ua.obtained_at,
        }
        for ua, ach in ach_result
    ]

    # ── Community counters ──
    profiles_count = (await db.execute(select(func.count()).select_from(SocialProfile))).scalar_one()
    publications_count = (
        await db.execute(
            select(func.count()).select_from(SocialPublication).where(SocialPublication.is_active.is_(True))
        )
    ).scalar_one()
    kudos_count = (await db.execute(select(func.count()).select_from(SocialEncouragement))).scalar_one()

    return templates.TemplateResponse(
        request=request,
        name="vitrina.html",
        context={
            "request": request,
            "t": t,
            "locale": locale,
            "theme": "dark",
            "top_participants": top_participants,
            "recent_achievements": recent_achievements,
            "profiles_count": profiles_count,
            "publications_count": publications_count,
            "kudos_count": kudos_count,
        },
    )
