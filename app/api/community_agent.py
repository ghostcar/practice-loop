"""Community Agent Router — thin HTTP wrappers over community_agent_service."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.community_agent import (
    create_community_tournament,
    get_community_membership,
    get_or_create_community_top_agent,
    recalculate_tournament_standings,
)
from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.community_agent import (
    CommunityMemberDelegation,
    CommunityTournamentEntry,
)
from app.models.user import User
from app.services.community_agent_service import (
    do_join_tournament,
    do_run_quest_generation,
    get_agent_page_context,
    require_manager,
)
from app.templates_setup import templates
from app.tier_guard import require_feature

router = APIRouter(tags=["community_agent"])


async def _is_manager(db: AsyncSession, community_id: uuid.UUID, user: User) -> bool:
    try:
        await require_manager(db, community_id, user)
        return True
    except ValueError:
        return False


@router.get("/communities/{community_id}/agent", response_class=HTMLResponse)
async def community_agent_dashboard_page(
    community_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _access: None = Depends(require_feature("community_agent")),
):
    c_uuid = uuid.UUID(community_id)
    try:
        ctx = await get_agent_page_context(db, c_uuid)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    community = ctx["community"]

    membership = await get_community_membership(db, c_uuid, user.id)
    if community.visibility == "private" and (not membership or membership.status != "active"):
        raise HTTPException(403, "Вступите в приватное сообщество, чтобы увидеть агента")
    is_owner = community.owner_id == user.id
    can_manage = is_owner or await _is_manager(db, c_uuid, user)
    delegations = ctx["delegations"]
    user_delegation = next((d for d in delegations if d.user_id == user.id), None)

    locale = detect_locale(request, user.locale)
    return templates.TemplateResponse(
        request=request,
        name="community_agent.html",
        context={
            "request": request,
            "t": get_translations(locale),
            "user": user,
            "locale": locale,
            "theme": detect_theme(user.theme),
            "active_nav": "community",
            "is_owner": is_owner,
            "can_manage": can_manage,
            "user_delegation": user_delegation,
            **{k: v for k, v in ctx.items() if k != "delegations"},
            "delegations": delegations,
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
    c_uuid = uuid.UUID(community_id)
    await require_manager(db, c_uuid, user)
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
    c_uuid = uuid.UUID(community_id)
    result = await do_run_quest_generation(db, c_uuid, user)
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
    c_uuid = uuid.UUID(community_id)
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
    c_uuid = uuid.UUID(community_id)
    t_uuid = uuid.UUID(tournament_id)
    entry = await do_join_tournament(db, c_uuid, t_uuid, user)
    return JSONResponse({"status": "ok", "entry_id": str(entry.id), "rank": entry.rank})


@router.post("/communities/{community_id}/agent/tournaments/{tournament_id}/points")
async def award_tournament_points_endpoint(
    community_id: str,
    tournament_id: str,
    user_id_: str = Form(..., alias="user_id"),
    points: int = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    c_uuid = uuid.UUID(community_id)
    await require_manager(db, c_uuid, user)
    t_uuid = uuid.UUID(tournament_id)
    entry = (
        await db.execute(
            select(CommunityTournamentEntry).where(
                CommunityTournamentEntry.tournament_id == t_uuid,
                CommunityTournamentEntry.user_id == uuid.UUID(user_id_),
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
        db.add(
            CommunityMemberDelegation(
                community_id=c_uuid,
                user_id=user.id,
                delegate_tasks=True,
                delegate_training=True,
                delegate_care=True,
                delegate_timer=True,
                compliance_score=100.0,
            )
        )
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
    c_uuid = uuid.UUID(community_id)
    community = await require_manager(db, c_uuid, user)
    agent = await get_or_create_community_top_agent(db, c_uuid)
    delegations = (
        (await db.execute(select(CommunityMemberDelegation).where(CommunityMemberDelegation.community_id == c_uuid)))
        .scalars()
        .all()
    )
    locale = detect_locale(request, user.locale)
    return templates.TemplateResponse(
        request=request,
        name="community_cockpit.html",
        context={
            "request": request,
            "t": get_translations(locale),
            "user": user,
            "locale": locale,
            "theme": detect_theme(user.theme),
            "community": community,
            "agent": agent,
            "delegations": delegations,
            "is_owner": community.owner_id == user.id,
            "can_manage": True,
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
    c_uuid = uuid.UUID(community_id)
    await require_manager(db, c_uuid, user)
    agent = await get_or_create_community_top_agent(db, c_uuid)
    agent.persona_name = persona_name
    agent.strictness_level = max(1, min(5, strictness_level))
    await db.flush()
    return JSONResponse({"status": "success", "persona_name": agent.persona_name, "strictness": agent.strictness_level})
