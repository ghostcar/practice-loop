"""Communities Service — business logic extracted from app.api.communities.

Covers: page contexts (list + detail), creation, join/leave, approval,
invite codes, ownership transfer, moderator management, slug validation.
"""

from __future__ import annotations

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.community_agent import (
    approve_community_member,
    assign_member_role,
    ban_community_member,
    create_community,
    create_community_post,
    get_community_membership,
    join_community,
    leave_community,
    list_member_roles,
    remove_member_role,
    rotate_community_invite_code,
    transfer_community_ownership,
    unban_community_member,
)
from app.models.community_agent import (
    Community,
    CommunityMember,
    CommunityPost,
    CommunityTopAgent,
    CommunityTournament,
)

VALID_SLUG_RE = r"^[a-z0-9][a-z0-9-]{2,63}$"


async def _owned_count(db: AsyncSession, user_id: uuid.UUID) -> int:
    res = await db.execute(select(func.count()).select_from(Community).where(Community.owner_id == user_id))
    return int(res.scalar_one() or 0)


# ════════════════════════════════════════════════════════════
# Page contexts
# ════════════════════════════════════════════════════════════


async def get_community_list_context(db: AsyncSession, user) -> dict:
    """Build context for /communities list page."""
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
    return {
        "my_communities": my_communities,
        "my_membership": my_membership,
        "public_communities": public_communities,
        "member_counts": member_counts,
        "owned": owned,
    }


async def get_community_feed_context(
    db: AsyncSession,
    c_uuid: uuid.UUID,
    user,
    *,
    limit: int = 30,
) -> dict:
    """Build context for the community feed page (G.3)."""
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")

    membership = await get_community_membership(db, c_uuid, user.id)
    is_member = membership is not None and membership.status == "active"
    is_owner = membership is not None and membership.role == "owner" and membership.status == "active"

    posts_res = await db.execute(
        select(CommunityPost)
        .where(CommunityPost.community_id == c_uuid)
        .order_by(CommunityPost.created_at.desc())
        .limit(min(limit, 100))
    )
    posts = posts_res.scalars().all()

    # Resolve author aliases (social profile alias when available)
    from app.platform.social.repositories.profile import get_profile

    post_data = []
    for p in posts:
        author_label = p.author_name
        if p.user_id:
            profile = await get_profile(db, p.user_id)
            if profile and profile.alias:
                author_label = f"@{profile.alias}"
        post_data.append({"post": p, "author_label": author_label})

    return {
        "community": community,
        "membership": membership,
        "is_member": is_member,
        "is_owner": is_owner,
        "posts": post_data,
    }


async def do_create_post(
    db: AsyncSession,
    c_uuid: uuid.UUID,
    user,
    *,
    title: str,
    content: str,
) -> CommunityPost:
    """Create a community feed post (member only)."""
    return await create_community_post(db, c_uuid, user.id, title=title, content=content)


async def do_ban_member(
    db: AsyncSession,
    c_uuid: uuid.UUID,
    target_user_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> str:
    """Ban a member — owner or moderator only."""
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")
    if not await _can_moderate(db, c_uuid, actor_user_id, community):
        raise PermissionError("Только владелец или модератор может банить участников")
    return await ban_community_member(db, c_uuid, target_user_id)


async def do_unban_member(
    db: AsyncSession,
    c_uuid: uuid.UUID,
    target_user_id: uuid.UUID,
    actor_user_id: uuid.UUID,
) -> str:
    """Unban a member — owner or moderator only."""
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")
    if not await _can_moderate(db, c_uuid, actor_user_id, community):
        raise PermissionError("Только владелец или модератор может разбанивать участников")
    return await unban_community_member(db, c_uuid, target_user_id)


async def _can_moderate(db: AsyncSession, c_uuid: uuid.UUID, user_id: uuid.UUID, community: Community) -> bool:
    """Owner or any assigned moderator role can moderate."""
    if community.owner_id == user_id:
        return True
    membership = await get_community_membership(db, c_uuid, user_id)
    if not membership or membership.status != "active":
        return False
    roles = await list_member_roles(db, c_uuid)
    return any(r.user_id == user_id for r in roles)


async def get_community_detail_context(db: AsyncSession, c_uuid: uuid.UUID, user) -> dict:
    """Build context for /communities/{id} detail page."""
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")

    membership = await get_community_membership(db, c_uuid, user.id)
    is_owner = membership is not None and membership.role == "owner" and membership.status == "active"

    members_res = await db.execute(
        select(CommunityMember).where(CommunityMember.community_id == c_uuid).order_by(CommunityMember.joined_at)
    )
    members = members_res.scalars().all()
    active_members = [m for m in members if m.status == "active"]
    pending_members = [m for m in members if m.status == "pending"]
    banned_members = [m for m in members if m.status == "revoked"]

    moderator_roles = await list_member_roles(db, c_uuid)
    user_moderator_roles = {r.role_type for r in moderator_roles if r.user_id == user.id}
    can_moderate = is_owner or bool(user_moderator_roles)

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

    return {
        "community": community,
        "membership": membership,
        "is_owner": is_owner,
        "members": active_members,
        "pending_members": pending_members,
        "banned_members": banned_members,
        "member_count": len(active_members),
        "moderator_roles": moderator_roles,
        "user_moderator_roles": user_moderator_roles,
        "can_moderate": can_moderate,
        "agent": agent,
        "recent_posts": recent_posts,
        "tournaments": tournaments,
    }


# ════════════════════════════════════════════════════════
# Mutations
# ════════════════════════════════════════════════════════


async def create_community_from_form(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    name: str,
    slug: str,
    description: str = "",
    visibility: str = "public",
    require_approval: bool = False,
    creation_limit: int = 0,
) -> tuple[Community | None, str | None]:
    """Create a community. Returns (community, error_url) — one is None."""
    name = name.strip()
    slug = slug.strip().lower().lstrip("/")
    if not name or len(name) < 2:
        return None, "/communities?error=Название слишком короткое"
    if not re.match(VALID_SLUG_RE, slug):
        return None, "/communities?error=Некорректный slug (3-64 символа: буквы, цифры, дефисы)"

    if creation_limit > 0:
        owned = await _owned_count(db, user_id)
        if owned >= creation_limit:
            return None, f"/communities?error=Лимит созданных сообществ ({creation_limit}) исчерпан"

    existing = (await db.execute(select(Community).where(Community.slug == slug))).scalar_one_or_none()
    if existing:
        return None, "/communities?error=Сообщество с таким slug уже существует"

    community = await create_community(
        db,
        name=name,
        slug=slug,
        description=description,
        owner_id=user_id,
        visibility=visibility,
        require_approval=require_approval,
    )
    await db.flush()
    return community, None


async def do_join_community(db: AsyncSession, c_uuid: uuid.UUID, user_id: uuid.UUID, invite_code: str = "") -> str:
    """Join a community. Returns redirect suffix."""
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")

    status, _ = await join_community(db, community, user_id, invite_code=invite_code or None)
    await db.flush()

    if status == "invalid_code":
        return f"/communities/{c_uuid}?error=Неверный инвайт-код"
    if status == "already_member":
        return f"/communities/{c_uuid}"
    if status == "pending":
        return f"/communities/{c_uuid}?joined=pending"
    return f"/communities/{c_uuid}?joined=ok"


async def do_leave_community(db: AsyncSession, c_uuid: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Leave a community. Returns True if successful."""
    removed = await leave_community(db, c_uuid, user_id)
    await db.flush()
    return removed


async def do_approve_member(
    db: AsyncSession,
    c_uuid: uuid.UUID,
    member_id: uuid.UUID,
    user_id: uuid.UUID,
    approve: bool,
) -> None:
    """Owner approves/rejects a pending member."""
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")
    membership = await get_community_membership(db, c_uuid, user_id)
    if not membership or membership.role != "owner" or membership.status != "active":
        raise ValueError("Только владелец может одобрять заявки")
    await approve_community_member(db, c_uuid, member_id, approve=approve)


async def do_rotate_invite(db: AsyncSession, c_uuid: uuid.UUID, user_id: uuid.UUID) -> str:
    """Owner rotates invite code. Returns the new code."""
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")
    membership = await get_community_membership(db, c_uuid, user_id)
    if not membership or membership.role != "owner":
        raise ValueError("Только владелец может управлять инвайт-кодом")
    code = await rotate_community_invite_code(db, community)
    await db.flush()
    return code


async def do_delete_community(db: AsyncSession, c_uuid: uuid.UUID, user_id: uuid.UUID) -> None:
    """Owner deletes the community."""
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")
    membership = await get_community_membership(db, c_uuid, user_id)
    if not membership or membership.role != "owner":
        raise ValueError("Только владелец может удалить сообщество")
    await db.delete(community)


async def do_transfer_ownership(
    db: AsyncSession,
    c_uuid: uuid.UUID,
    new_owner_id: uuid.UUID,
    user_id: uuid.UUID,
) -> str:
    """Transfer ownership. Returns status string."""
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")
    membership = await get_community_membership(db, c_uuid, user_id)
    if not membership or membership.role != "owner" or membership.status != "active":
        raise ValueError("Только владелец сообщества может выполнять это действие")

    status, _ = await transfer_community_ownership(db, community, new_owner_id)
    await db.flush()
    return status


async def do_add_moderator(
    db: AsyncSession,
    c_uuid: uuid.UUID,
    target_user_id: uuid.UUID,
    role_type: str,
    user_id: uuid.UUID,
) -> str:
    """Assign a moderator role. Returns status."""
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")
    membership = await get_community_membership(db, c_uuid, user_id)
    if not membership or membership.role != "owner" or membership.status != "active":
        raise ValueError("Только владелец может назначать модераторов")

    status, _ = await assign_member_role(db, c_uuid, target_user_id, role_type)
    await db.flush()
    return status


async def do_remove_moderator(
    db: AsyncSession,
    c_uuid: uuid.UUID,
    target_user_id: uuid.UUID,
    role_type: str,
    user_id: uuid.UUID,
) -> bool:
    """Remove a moderator role. Returns True if removed."""
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")
    membership = await get_community_membership(db, c_uuid, user_id)
    if not membership or membership.role != "owner" or membership.status != "active":
        raise ValueError("Только владелец может снимать модераторов")

    removed = await remove_member_role(db, c_uuid, target_user_id, role_type)
    await db.flush()
    return removed
