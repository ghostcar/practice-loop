"""Interactive Gamification & Quests Master Router (Step 43 / ADR-120)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.progress import UserProgress
from app.models.quest import Quest, UserQuest
from app.models.user import User
from app.seed_quests import seed_quests
from app.templates_setup import templates

router = APIRouter(tags=["quests"])


@router.get("/achievements/quests", response_class=HTMLResponse)
async def quests_hub_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Interactive Quests & Gamification Hub."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    # Ensure quests exist
    await seed_quests(db)

    # Fetch all catalog quests
    catalog_quests = (await db.execute(select(Quest))).scalars().all()

    # Assign missing quests to user
    existing_uq = (
        await db.execute(select(UserQuest).where(UserQuest.user_id == user.id))
    ).scalars().all()
    assigned_quest_ids = {uq.quest_id for uq in existing_uq}

    for q in catalog_quests:
        if q.id not in assigned_quest_ids:
            new_uq = UserQuest(user_id=user.id, quest_id=q.id, current_progress=0, status="active")
            db.add(new_uq)

    await db.commit()

    # Refetch updated user quests with loaded relationships
    user_quests = (
        (
            await db.execute(
                select(UserQuest)
                .where(UserQuest.user_id == user.id)
                .order_by(UserQuest.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        request=request,
        name="quests.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "achievements",
            "user_quests": user_quests,
        },
    )


@router.post("/achievements/quests/{user_quest_id}/claim")
async def claim_quest_reward(
    user_quest_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Claims reward XP for a completed quest."""
    import uuid

    uq_uuid = uuid.UUID(user_quest_id)
    uq = (
        await db.execute(
            select(UserQuest).where(UserQuest.id == uq_uuid, UserQuest.user_id == user.id)
        )
    ).scalar_one_or_none()

    if not uq:
        raise HTTPException(404, "User quest not found")

    quest = (await db.execute(select(Quest).where(Quest.id == uq.quest_id))).scalar_one_or_none()
    if not quest:
        raise HTTPException(404, "Quest definition missing")

    if uq.status == "claimed":
        return RedirectResponse(url="/achievements/quests", status_code=303)

    uq.status = "claimed"
    uq.obtained_at = datetime.now(UTC)

    # Award XP to UserProgress
    progress = (
        await db.execute(select(UserProgress).where(UserProgress.user_id == user.id))
    ).scalar_one_or_none()

    if not progress:
        progress = UserProgress(user_id=user.id, xp=0, level=1)
        db.add(progress)

    progress.xp += quest.reward_xp
    await db.commit()

    return RedirectResponse(url="/achievements/quests", status_code=303)


@router.get("/quests/challenges", response_class=HTMLResponse)
async def quests_challenges_alias(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Alias route for Quests & Weekly Challenges Hub."""
    return await quests_hub_page(request=request, user=user, db=db)

