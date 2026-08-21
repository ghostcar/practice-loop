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
    get_community_membership,
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
    CommunityTournamentEntry,
)
from app.models.user import User
from app.templates_setup import templates
from app.tier_guard import require_feature

logger = logging.getLogger(__name__)

router = APIRouter(tags=["community_agent"])


async def _require_owner(
    db: AsyncSession,
    community_id: uuid.UUID,
    user: User,
) -> Community:
    """Fetches community and enforces that the current user is its active owner."""
    community = (await db.execute(select(Community).where(Community.id == community_id))).scalar_one_or_none()
    if not community:
        raise HTTPException(404, "Community not found")
    if community.owner_id == user.id:
        return community
    membership = await get_community_membership(db, community_id, user.id)
    if not membership or membership.role != "owner" or membership.status != "active":
        raise HTTPException(403, "Только владелец сообщества может выполнять это действие")
    return community


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

    # Public communities visible to anyone; private ones require active membership.
    membership = await get_community_membership(db, c_uuid, user.id)
    if community.visibility == "private" and (not membership or membership.status != "active"):
        raise HTTPException(403, "Вступите в приватное сообщество, чтобы увидеть агента")

    is_owner = bool(membership and membership.role == "owner" and membership.status == "active")

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
            "is_owner": is_owner,
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
    """Updates Community Top Agent persona settings (owner only)."""
    c_uuid = uuid.UUID(community_id)
    await _require_owner(db, c_uuid, user)
    agent = await get_or_create_community_top_agent(db, c_uuid)

    agent.persona_name = persona_name.strip()
    agent.strictness_level = max(1, min(5, strictness_level))
    await db.flush()

    return JSONResponse({"status": "ok", "persona_name": agent.persona_name, "strictness": agent.strictness_level})


@router.post("/communities/{community_id}/agent/quest/generate")
async def generate_community_quest_endpoint(
    community_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generates a group quest and posts feed announcement (owner only)."""
    c_uuid = uuid.UUID(community_id)
    await _require_owner(db, c_uuid, user)
    result = await run_community_quest_generation(db, c_uuid)
    await db.flush()
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
    """Creates a public community tournament (owner only)."""
    c_uuid = uuid.UUID(community_id)
    await _require_owner(db, c_uuid, user)
    tournament = await create_community_tournament(db, c_uuid, title=title, metric_type=metric_type, days=days)
    await db.flush()
    return JSONResponse({"status": "ok", "tournament_id": str(tournament.id), "title": tournament.title})


@router.post("/communities/{community_id}/agent/tournaments/{tournament_id}/join")
async def join_tournament_endpoint(
    community_id: str,
    tournament_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Member joins a public tournament (must be an active member)."""
    c_uuid = uuid.UUID(community_id)
    membership = await get_community_membership(db, c_uuid, user.id)
    if not membership or membership.status != "active":
        raise HTTPException(403, "Вступите в сообщество, чтобы участвовать в турнирах")
    t_uuid = uuid.UUID(tournament_id)
    entry = await join_community_tournament(db, t_uuid, user.id)
    await db.flush()
    return JSONResponse({"status": "ok", "entry_id": str(entry.id), "rank": entry.rank})


@router.post("/communities/{community_id}/agent/tournaments/{tournament_id}/points")
async def award_tournament_points_endpoint(
    community_id: str,
    tournament_id: str,
    user_id: str = Form(...),
    points: int = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner manually awards tournament points to a member."""
    c_uuid = uuid.UUID(community_id)
    await _require_owner(db, c_uuid, user)

    from app.agent.community_agent import recalculate_tournament_standings

    t_uuid = uuid.UUID(tournament_id)
    entry = (
        await db.execute(
            select(CommunityTournamentEntry).where(
                CommunityTournamentEntry.tournament_id == t_uuid,
                CommunityTournamentEntry.user_id == uuid.UUID(user_id),
            )
        )
    ).scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Участник не найден в турнире")

    entry.points = max(0, entry.points + int(points))
    await db.flush()
    await recalculate_tournament_standings(db, t_uuid)
    return JSONResponse({"status": "ok", "points": entry.points, "rank": entry.rank})


@router.post("/communities/{community_id}/agent/delegate")
async def toggle_community_delegation_endpoint(
    community_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggles member profile delegation to the Community Top Agent (active members)."""
    c_uuid = uuid.UUID(community_id)
    membership = await get_community_membership(db, c_uuid, user.id)
    if not membership or membership.status != "active":
        raise HTTPException(403, "Вступите в сообщество, чтобы делегировать профиль")

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

    await db.flush()
    return JSONResponse({"status": status})


@router.get("/communities/{community_id}/cockpit", response_class=HTMLResponse)
async def community_cockpit_page(
    community_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _access: None = Depends(require_feature("community_agent")),
):
    """Community Agent Cockpit Owner View."""
    c_uuid = uuid.UUID(community_id)
    community = await _require_owner(db, c_uuid, user)

    agent = await get_or_create_community_top_agent(db, c_uuid)

    delegations_res = await db.execute(
        select(CommunityMemberDelegation).where(CommunityMemberDelegation.community_id == c_uuid)
    )
    delegations = delegations_res.scalars().all()

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="community_cockpit.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "community": community,
            "agent": agent,
            "delegations": delegations,
            "active_nav": "community_cockpit",
        },
    )


@router.post("/communities/{community_id}/cockpit/update-persona")
async def update_community_agent_persona_endpoint(
    community_id: str,
    persona_name: str = Form(...),
    strictness_level: int = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Updates Community Agent Persona configuration (owner only)."""
    c_uuid = uuid.UUID(community_id)
    await _require_owner(db, c_uuid, user)
    agent = await get_or_create_community_top_agent(db, c_uuid)
    agent.persona_name = persona_name
    agent.strictness_level = max(1, min(5, strictness_level))

    await db.flush()
    return JSONResponse({"status": "success", "persona_name": agent.persona_name, "strictness": agent.strictness_level})
