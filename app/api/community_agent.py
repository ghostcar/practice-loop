"""API Router for Autonomous Community Top Agent & Public Tournaments."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.community_agent import (
    create_community_tournament,
    get_or_create_community_top_agent,
    join_community_tournament,
    run_community_quest_generation,
)
from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.community_agent import (
    Community,
    CommunityMemberDelegation,
    CommunityPost,
    CommunityTournament,
)
from app.models.user import User
from app.templates_setup import templates
from app.tier_guard import require_feature

logger = logging.getLogger(__name__)

router = APIRouter(tags=["community_agent"])


@router.get("/communities/{community_id}/agent", response_class=HTMLResponse)
async def community_agent_dashboard_page(
    community_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _access: None = Depends(require_feature("community_agent")),
):
    """Community Top Agent Cockpit UI."""
    try:
        c_uuid = uuid.UUID(community_id)
    except ValueError as err:
        raise HTTPException(400, "Invalid community ID format") from err

    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise HTTPException(404, "Community not found")

    agent = await get_or_create_community_top_agent(db, c_uuid)

    tournaments_res = await db.execute(
        select(CommunityTournament)
        .where(CommunityTournament.community_id == c_uuid)
        .order_by(CommunityTournament.created_at.desc())
    )
    tournaments = tournaments_res.scalars().all()

    delegations_res = await db.execute(
        select(CommunityMemberDelegation).where(CommunityMemberDelegation.community_id == c_uuid)
    )
    delegations = delegations_res.scalars().all()

    user_delegation = next((d for d in delegations if d.user_id == user.id), None)

    posts_res = await db.execute(
        select(CommunityPost)
        .where(CommunityPost.community_id == c_uuid)
        .order_by(CommunityPost.created_at.desc())
        .limit(5)
    )
    recent_posts = posts_res.scalars().all()

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="community_agent.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "community",
            "community": community,
            "agent": agent,
            "tournaments": tournaments,
            "delegations": delegations,
            "user_delegation": user_delegation,
            "recent_posts": recent_posts,
        },
    )


@router.post("/communities/{community_id}/agent/configure")
async def configure_community_agent_endpoint(
    community_id: str,
    persona_name: str = Form("Domina Veritas"),
    strictness_level: int = Form(3),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Updates Community Top Agent persona settings."""
    c_uuid = uuid.UUID(community_id)
    agent = await get_or_create_community_top_agent(db, c_uuid)

    agent.persona_name = persona_name.strip()
    agent.strictness_level = max(1, min(5, strictness_level))

    return JSONResponse({"status": "ok", "persona_name": agent.persona_name, "strictness": agent.strictness_level})


@router.post("/communities/{community_id}/agent/quest/generate")
async def generate_community_quest_endpoint(
    community_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generates a group quest and posts feed announcement."""
    c_uuid = uuid.UUID(community_id)
    result = await run_community_quest_generation(db, c_uuid)
    return JSONResponse(result)


@router.post("/communities/{community_id}/agent/tournaments/create")
async def create_tournament_endpoint(
    community_id: str,
    title: str = Form(...),
    metric_type: str = Form("compliance"),
    days: int = Form(14),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates a public community tournament."""
    c_uuid = uuid.UUID(community_id)
    tournament = await create_community_tournament(db, c_uuid, title=title, metric_type=metric_type, days=days)
    return JSONResponse({"status": "ok", "tournament_id": str(tournament.id), "title": tournament.title})


@router.post("/communities/{community_id}/agent/tournaments/{tournament_id}/join")
async def join_tournament_endpoint(
    community_id: str,
    tournament_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Member joins a public tournament."""
    t_uuid = uuid.UUID(tournament_id)
    entry = await join_community_tournament(db, t_uuid, user.id)
    return JSONResponse({"status": "ok", "entry_id": str(entry.id), "rank": entry.rank})


@router.post("/communities/{community_id}/agent/delegate")
async def toggle_community_delegation_endpoint(
    community_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggles member profile delegation to the Community Top Agent."""
    c_uuid = uuid.UUID(community_id)
    existing = (
        await db.execute(
            select(CommunityMemberDelegation).where(
                CommunityMemberDelegation.community_id == c_uuid,
                CommunityMemberDelegation.user_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        await db.delete(existing)
        status = "revoked"
    else:
        delegation = CommunityMemberDelegation(
            community_id=c_uuid,
            user_id=user.id,
            delegate_tasks=True,
            delegate_training=True,
            delegate_care=True,
            delegate_timer=True,
            compliance_score=100.0,
        )
        db.add(delegation)
        status = "delegated"

    return JSONResponse({"status": status})
