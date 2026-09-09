"""Platform Social Pillory Mode & Community Vote Wheel API (Step 88 / ADR-113).

Routes:
- GET  /social/pillory        — View community Pillory board
- POST /social/pillory/vote   — Cast a community vote (+time / -time / task)
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.platform.social.models import SocialPublication
from app.platform.social.repositories import create_encouragement, get_profile, list_feed
from app.templates_setup import templates

router = APIRouter(tags=["social-pillory"])


@router.get("/pillory", response_class=HTMLResponse)
async def social_pillory_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """GET /social/pillory — Community Pillory Board & Vote Wheel."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    profile = await get_profile(db, user.id)

    # Pillory reads only explicit, immutable Social publications.  It must not
    # project private operational D/s rows directly into a community surface.
    publications = await list_feed(db, user.id, namespace="tracker.pillory", limit=100)

    return templates.TemplateResponse(
        request=request,
        name="social/pillory.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "social",
            "profile": profile,
            "publications": publications,
        },
    )


@router.post("/pillory/vote")
async def vote_pillory_endpoint(
    publication_id: str = Form(...),
    vote_type: str = Form(...),  # add_15m, add_1h, sub_15m, assign_task
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """POST /social/pillory/vote — Cast community vote on Pillory item (Audit A-05/A-07 fix)."""
    reasons_map = {
        "add_15m": ("lock_extension", "+15 мин ношения по результатам голоса сообщества"),
        "add_1h": ("lock_extension", "+1 час ношения по результатам голоса сообщества"),
        "sub_15m": ("key_reward", "-15 мин время уменьшено голосами сообщества"),
        "assign_task": ("tag_check", "Сообщество назначило инспекционную задачу"),
    }

    if vote_type not in reasons_map:
        raise HTTPException(400, "Invalid vote_type parameter")

    try:
        publication_uuid = uuid.UUID(publication_id)
    except ValueError:
        raise HTTPException(400, "Invalid UUID format") from None

    publication = (
        await db.execute(
            select(SocialPublication).where(
                SocialPublication.id == publication_uuid,
                SocialPublication.is_active,
                SocialPublication.visibility == "public",
                SocialPublication.subject_namespace == "tracker.pillory",
            )
        )
    ).scalar_one_or_none()
    if publication is None:
        raise HTTPException(404, "Pillory publication not found")
    if publication.owner_id == user.id:
        raise HTTPException(400, "Cannot vote on your own publication")

    vote = await create_encouragement(db, user.id, "pillory_publication", publication.id, vote_type)

    if vote is not None:
        # Auto-extend lock session timer if enabled on target session (ADR-197)
        session_id_str = publication.snapshot.get("session_id") if isinstance(publication.snapshot, dict) else None
        if session_id_str:
            try:
                from app.locktimer.repositories import get_session
                from app.locktimer.services.discipline_service import apply_pillory_vote_to_session

                target_session = await get_session(db, uuid.UUID(session_id_str), publication.owner_id)
                if target_session is not None and target_session.pillory_auto_extend:
                    await apply_pillory_vote_to_session(db, target_session, vote_type)
            except Exception:
                pass

        # Award Social XP to voter
        from app.gamification.handler import get_or_create_progress

        prog = await get_or_create_progress(db, user.id)
        prog.xp += 15

    return RedirectResponse(url="/social/pillory", status_code=303)
