"""Community Registry: creation, discovery, membership (join/leave/approval)."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.community_agent import (
    approve_community_member,
    assign_member_role,
    create_community,
    get_community_membership,
    is_valid_moderator_role,
    join_community,
    leave_community,
    list_member_roles,
    remove_member_role,
    rotate_community_invite_code,
    transfer_community_ownership,
)
from app.api.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.community_agent import (
    Community,
    CommunityMember,
    CommunityPost,
    CommunityTopAgent,
    CommunityTournament,
)
from app.models.community_roles import CommunityMemberRole
from app.models.user import User
from app.templates_setup import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["communities"])

VALID_SLUG_RE = r"^[a-z0-9][a-z0-9-]{2,63}$"


async def _owned_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    res = await db.execute(select(func.count()).select_from(Community).where(Community.owner_id == user_id))
    return int(res.scalar_one() or 0)


async def _load_membership(db: AsyncSession, community: Community, user: User) -> CommunityMember | None:
    return await get_community_membership(db, community.id, user.id)


@router.get("/communities", response_class=HTMLResponse)
async def community_list_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Community registry: my communities + public discovery list."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    mine_res = await db.execute(
        select(Community, CommunityMember)
        .join(CommunityMember, CommunityMember.community_id == Community.id)
        .where(CommunityMember.user_id == user.id)
        .order_by(Community.created_at.desc())
    )
    mine_rows = mine_res.all()
    my_communities = [c for c, _ in mine_rows]
    my_membership = {c.id: m for c, m in mine_rows}

    public_res = await db.execute(
        select(Community).where(Community.visibility == "public").order_by(Community.created_at.desc()).limit(50)
    )
    public_communities = public_res.scalars().all()

    member_counts: dict[uuid.UUID, int] = {}
    all_ids = {c.id for c in list(my_communities) + list(public_communities)}
    if all_ids:
        count_res = await db.execute(
            select(CommunityMember.community_id, func.count())
            .where(CommunityMember.community_id.in_(all_ids), CommunityMember.status == "active")
            .group_by(CommunityMember.community_id)
        )
        member_counts = {cid: int(n) for cid, n in count_res.all()}

    owned = await _owned_count(db, user.id)
    limit = getattr(settings, "community_creation_limit", 0)

    return templates.TemplateResponse(
        request=request,
        name="community_list.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "communities",
            "my_communities": my_communities,
            "my_membership": my_membership,
            "public_communities": public_communities,
            "member_counts": member_counts,
            "owned": owned,
            "creation_limit": limit,
        },
    )


@router.post("/communities/create")
async def create_community_endpoint(
    request: Request,
    name: str = Form(...),
    slug: str = Form(...),
    description: str = Form(""),
    visibility: str = Form("public"),
    require_approval: str = Form("off"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates a new community. Owner becomes the first member."""
    import re

    name = name.strip()
    slug = slug.strip().lower().lstrip("/")
    if not name or len(name) < 2:
        return RedirectResponse(url="/communities?error=Название слишком короткое", status_code=303)
    if not re.match(VALID_SLUG_RE, slug):
        return RedirectResponse(
            url="/communities?error=Некорректный slug (3-64 символа: буквы, цифры, дефисы)",
            status_code=303,
        )

    limit = getattr(settings, "community_creation_limit", 0)
    if limit and limit > 0:
        owned = await _owned_count(db, user.id)
        if owned >= limit:
            return RedirectResponse(
                url=f"/communities?error=Лимит созданных сообществ ({limit}) исчерпан", status_code=303
            )

    existing = (await db.execute(select(Community).where(Community.slug == slug))).scalar_one_or_none()
    if existing:
        return RedirectResponse(url="/communities?error=Сообщество с таким slug уже существует", status_code=303)

    community = await create_community(
        db,
        name=name,
        slug=slug,
        description=description,
        owner_id=user.id,
        visibility=visibility,
        require_approval=require_approval == "on",
    )
    await db.flush()
    return RedirectResponse(url=f"/communities/{community.id}", status_code=303)


@router.get("/communities/{community_id}", response_class=HTMLResponse)
async def community_detail_page(
    community_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Community detail page: info, membership actions, members, agent/cockpit links."""
    try:
        c_uuid = uuid.UUID(community_id)
    except ValueError as err:
        raise HTTPException(400, "Invalid community ID") from err

    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise HTTPException(404, "Community not found")

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    membership = await _load_membership(db, community, user)
    is_owner = membership is not None and membership.role == "owner" and membership.status == "active"

    members_res = await db.execute(
        select(CommunityMember).where(CommunityMember.community_id == c_uuid).order_by(CommunityMember.joined_at)
    )
    members = members_res.scalars().all()
    active_members = [m for m in members if m.status == "active"]
    pending_members = [m for m in members if m.status == "pending"]

    # Moderator role assignments (for the owner management panel).
    moderator_roles = await list_member_roles(db, c_uuid)
    user_moderator_roles = {r.role_type for r in moderator_roles if r.user_id == user.id}

    agent_res = await db.execute(select(CommunityTopAgent).where(CommunityTopAgent.community_id == c_uuid))
    agent = agent_res.scalar_one_or_none()

    posts_res = await db.execute(
        select(CommunityPost)
        .where(CommunityPost.community_id == c_uuid)
        .order_by(CommunityPost.created_at.desc())
        .limit(3)
    )
    recent_posts = posts_res.scalars().all()

    tourneys_res = await db.execute(
        select(CommunityTournament)
        .where(CommunityTournament.community_id == c_uuid, CommunityTournament.status == "active")
        .order_by(CommunityTournament.created_at.desc())
        .limit(3)
    )
    tournaments = tourneys_res.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="community_detail.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "communities",
            "community": community,
            "membership": membership,
            "is_owner": is_owner,
            "members": active_members,
            "pending_members": pending_members,
            "member_count": len(active_members),
            "moderator_roles": moderator_roles,
            "user_moderator_roles": user_moderator_roles,
            "agent": agent,
            "recent_posts": recent_posts,
            "tournaments": tournaments,
        },
    )


@router.post("/communities/{community_id}/join")
async def join_community_endpoint(
    community_id: str,
    request: Request,
    invite_code: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Joins a community (public: instant or pending approval; private: requires invite code)."""
    c_uuid = uuid.UUID(community_id)
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise HTTPException(404, "Community not found")

    status, _ = await join_community(db, community, user.id, invite_code=invite_code or None)
    await db.flush()

    if status == "invalid_code":
        return RedirectResponse(url=f"/communities/{c_uuid}?error=Неверный инвайт-код", status_code=303)
    if status == "already_member":
        return RedirectResponse(url=f"/communities/{c_uuid}", status_code=303)
    if status == "pending":
        return RedirectResponse(url=f"/communities/{c_uuid}?joined=pending", status_code=303)
    return RedirectResponse(url=f"/communities/{c_uuid}?joined=ok", status_code=303)


@router.post("/communities/{community_id}/leave")
async def leave_community_endpoint(
    community_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Leaves a community. Owners must transfer ownership or delete instead."""
    c_uuid = uuid.UUID(community_id)
    removed = await leave_community(db, c_uuid, user.id)
    await db.flush()
    if not removed:
        raise HTTPException(400, "Владелец не может покинуть сообщество (или вы не участник)")
    return RedirectResponse(url="/communities", status_code=303)


@router.post("/communities/{community_id}/approve")
async def approve_member_endpoint(
    community_id: str,
    member_id: str = Form(...),
    decision: str = Form("approve"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner approves or rejects a pending membership request."""
    c_uuid = uuid.UUID(community_id)
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise HTTPException(404, "Community not found")
    membership = await get_community_membership(db, c_uuid, user.id)
    if not membership or membership.role != "owner" or membership.status != "active":
        raise HTTPException(403, "Только владелец может одобрять заявки")

    await approve_community_member(db, c_uuid, uuid.UUID(member_id), approve=decision == "approve")
    await db.flush()
    return RedirectResponse(url=f"/communities/{c_uuid}", status_code=303)


@router.post("/communities/{community_id}/invite")
async def generate_invite_code_endpoint(
    community_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner (re)generates the private invite code."""
    c_uuid = uuid.UUID(community_id)
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise HTTPException(404, "Community not found")
    membership = await get_community_membership(db, c_uuid, user.id)
    if not membership or membership.role != "owner":
        raise HTTPException(403, "Только владелец может управлять инвайт-кодом")

    code = await rotate_community_invite_code(db, community)
    await db.flush()
    return RedirectResponse(url=f"/communities/{c_uuid}?invite={code}", status_code=303)


@router.post("/communities/{community_id}/delete")
async def delete_community_endpoint(
    community_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner deletes the community permanently."""
    c_uuid = uuid.UUID(community_id)
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise HTTPException(404, "Community not found")
    membership = await get_community_membership(db, c_uuid, user.id)
    if not membership or membership.role != "owner":
        raise HTTPException(403, "Только владелец может удалить сообщество")

    await db.delete(community)
    await db.flush()
    return RedirectResponse(url="/communities", status_code=303)


async def _require_owner(
    db: AsyncSession,
    community_id: uuid.UUID,
    user: User,
) -> Community:
    """Fetches community and enforces that the current user is its active owner."""
    community = (await db.execute(select(Community).where(Community.id == community_id))).scalar_one_or_none()
    if not community:
        raise HTTPException(404, "Community not found")
    membership = await get_community_membership(db, community_id, user.id)
    if not membership or membership.role != "owner" or membership.status != "active":
        raise HTTPException(403, "Только владелец сообщества может выполнять это действие")
    return community


@router.post("/communities/{community_id}/transfer")
async def transfer_ownership_endpoint(
    community_id: str,
    new_owner_id: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner transfers ownership to another active member."""
    c_uuid = uuid.UUID(community_id)
    community = await _require_owner(db, c_uuid, user)

    status, _ = await transfer_community_ownership(db, community, uuid.UUID(new_owner_id))
    await db.flush()

    if status == "not_member":
        raise HTTPException(400, "Новый владелец должен быть активным участником сообщества")
    if status == "already_owner":
        raise HTTPException(400, "Этот участник уже является владельцем")

    return RedirectResponse(url=f"/communities/{c_uuid}?transfer=ok", status_code=303)


@router.post("/communities/{community_id}/moderators/add")
async def add_moderator_endpoint(
    community_id: str,
    user_id: str = Form(...),
    role_type: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner assigns a moderator role to an active member."""
    c_uuid = uuid.UUID(community_id)
    await _require_owner(db, c_uuid, user)

    status, _ = await assign_member_role(db, c_uuid, uuid.UUID(user_id), role_type)
    await db.flush()

    if status == "invalid_role":
        raise HTTPException(400, "Неизвестная роль модератора")
    if status == "not_member":
        raise HTTPException(400, "Участник должен быть активным членом сообщества")
    if status == "already_assigned":
        raise HTTPException(400, "Роль уже назначена этому участнику")

    return RedirectResponse(url=f"/communities/{c_uuid}?moderator=added", status_code=303)


@router.post("/communities/{community_id}/moderators/remove")
async def remove_moderator_endpoint(
    community_id: str,
    user_id: str = Form(...),
    role_type: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Owner removes a moderator role from a member."""
    c_uuid = uuid.UUID(community_id)
    await _require_owner(db, c_uuid, user)

    removed = await remove_member_role(db, c_uuid, uuid.UUID(user_id), role_type)
    await db.flush()
    if not removed:
        raise HTTPException(400, "Роль не была назначена")

    return RedirectResponse(url=f"/communities/{c_uuid}?moderator=removed", status_code=303)
