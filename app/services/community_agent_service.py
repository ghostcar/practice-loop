"""Community Agent Service — business logic from app.api.community_agent."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.community_agent import (
    create_community_tournament,
    get_community_membership,
    get_member_roles,
    get_or_create_community_top_agent,
    join_community_tournament,
    run_community_quest_generation,
)
from app.models.community_agent import (
    Community,
    CommunityMemberDelegation,
    CommunityPost,
    CommunityTournament,
    CommunityTournamentEntry,
)

_MANAGE_ROLES = frozenset({"co_top", "tournament_organizer"})


async def require_manager(
    db: AsyncSession,
    community_id: uuid.UUID,
    user,
    *,
    allow_tournament_organizer: bool = True,
) -> Community:
    community = (await db.execute(select(Community).where(Community.id == community_id))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")
    if community.owner_id == user.id:
        return community
    membership = await get_community_membership(db, community_id, user.id)
    if not membership or membership.status != "active":
        raise ValueError("Not an active member")
    roles = await get_member_roles(db, community_id, user.id)
    user_roles = {r.role_type for r in roles}
    allowed = user_roles & _MANAGE_ROLES
    if allowed and (allow_tournament_organizer or allowed != {"tournament_organizer"}):
        return community
    raise ValueError("Not authorized")


async def get_agent_page_context(db: AsyncSession, c_uuid: uuid.UUID) -> dict:
    community = (await db.execute(select(Community).where(Community.id == c_uuid))).scalar_one_or_none()
    if not community:
        raise ValueError("Community not found")
    agent = await get_or_create_community_top_agent(db, c_uuid)
    posts = (
        (
            await db.execute(
                select(CommunityPost)
                .where(CommunityPost.community_id == c_uuid)
                .order_by(CommunityPost.created_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    tourneys = (
        (
            await db.execute(
                select(CommunityTournament)
                .where(CommunityTournament.community_id == c_uuid)
                .order_by(CommunityTournament.created_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )
    delegations = (
        (await db.execute(select(CommunityMemberDelegation).where(CommunityMemberDelegation.community_id == c_uuid)))
        .scalars()
        .all()
    )
    return {
        "community": community,
        "agent": agent,
        "recent_posts": posts,
        "tournaments": tourneys,
        "delegations": delegations,
    }


async def do_create_tournament(
    db: AsyncSession,
    c_uuid: uuid.UUID,
    user,
    *,
    name: str,
    description: str = "",
    tournament_type: str = "points_race",
    start_date=None,
    end_date=None,
) -> CommunityTournament:
    await require_manager(db, c_uuid, user)
    return await create_community_tournament(
        db,
        c_uuid,
        name=name,
        description=description,
        tournament_type=tournament_type,
        created_by=user.id,
        start_date=start_date,
        end_date=end_date,
    )


async def do_join_tournament(
    db: AsyncSession,
    c_uuid: uuid.UUID,
    t_uuid: uuid.UUID,
    user,
) -> CommunityTournamentEntry:
    membership = await get_community_membership(db, c_uuid, user.id)
    if not membership or membership.status != "active":
        raise ValueError("Must be an active member to join")
    return await join_community_tournament(db, t_uuid, user.id)


async def do_run_quest_generation(
    db: AsyncSession,
    c_uuid: uuid.UUID,
    user,
) -> list:
    await require_manager(db, c_uuid, user)
    return await run_community_quest_generation(db, c_uuid, user.id)
