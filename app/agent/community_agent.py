"""Core Engine for Autonomous Community Top Agent & Public Tournament System."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.community_agent import (
    Community,
    CommunityMember,
    CommunityMemberDelegation,
    CommunityPost,
    CommunityTopAgent,
    CommunityTournament,
    CommunityTournamentEntry,
)

logger = logging.getLogger(__name__)


async def get_or_create_community_top_agent(
    db: AsyncSession,
    community_id: uuid.UUID,
) -> CommunityTopAgent:
    """Fetches or initializes the CommunityTopAgent for a community."""
    agent = (
        await db.execute(select(CommunityTopAgent).where(CommunityTopAgent.community_id == community_id))
    ).scalar_one_or_none()

    if not agent:
        agent = CommunityTopAgent(
            community_id=community_id,
            persona_name="Domina Veritas",
            strictness_level=3,
            auto_quests_enabled=True,
            lock_challenges_enabled=True,
        )
        db.add(agent)
        await db.flush()

    return agent


async def run_community_quest_generation(
    db: AsyncSession,
    community_id: uuid.UUID,
) -> dict[str, str]:
    """Generates a group quest and posts announcement to Community Feed."""
    agent = await get_or_create_community_top_agent(db, community_id)
    now = datetime.now()

    post = CommunityPost(
        community_id=community_id,
        user_id=None,  # System/Agent post
        author_name=agent.persona_name,
        post_type="announcement",
        title=f"🎯 Челлендж от {agent.persona_name}",
        content=(
            f"ИИ-Верхний {agent.persona_name} (Строгость {agent.strictness_level}/5) "
            "объявил новый групповой квест дня! Приглашаем к выполнению."
        ),
        created_at=now,
    )
    db.add(post)
    await db.flush()

    return {
        "status": "success",
        "post_id": str(post.id),
        "persona_name": agent.persona_name,
        "title": post.title,
    }


async def create_community_tournament(
    db: AsyncSession,
    community_id: uuid.UUID,
    title: str,
    metric_type: str = "compliance",
    days: int = 14,
) -> CommunityTournament:
    """Creates a public community tournament and posts announcement."""
    agent = await get_or_create_community_top_agent(db, community_id)
    now = datetime.now()
    ends_at = now + timedelta(days=days)

    tournament = CommunityTournament(
        community_id=community_id,
        title=title,
        description=f"Публичный турнир сообщества под управлением {agent.persona_name}.",
        metric_type=metric_type,
        status="active",
        starts_at=now,
        ends_at=ends_at,
    )
    db.add(tournament)
    await db.flush()

    # Feed announcement
    post = CommunityPost(
        community_id=community_id,
        user_id=None,
        author_name=agent.persona_name,
        post_type="announcement",
        title=f"🏆 Объявлен Турнир: {title}",
        content=f"Открыта регистрация в турнир «{title}» ({days} дн., метрика {metric_type}). Присоединяйтесь!",
        created_at=now,
    )
    db.add(post)
    await db.flush()

    return tournament


async def join_community_tournament(
    db: AsyncSession,
    tournament_id: uuid.UUID,
    user_id: uuid.UUID,
) -> CommunityTournamentEntry:
    """Registers a member into a public community tournament."""
    existing = (
        await db.execute(
            select(CommunityTournamentEntry).where(
                CommunityTournamentEntry.tournament_id == tournament_id,
                CommunityTournamentEntry.user_id == user_id,
            )
        )
    ).scalar_one_or_none()

    if existing:
        return existing

    entry = CommunityTournamentEntry(
        tournament_id=tournament_id,
        user_id=user_id,
        points=100.0,
        rank=1,
    )
    db.add(entry)
    await db.flush()

    await recalculate_tournament_standings(db, tournament_id)
    return entry


async def recalculate_tournament_standings(
    db: AsyncSession,
    tournament_id: uuid.UUID,
) -> list[dict[str, float | int | str]]:
    """Recalculates entries standings and assigns ranks (#1, #2, #3...)."""
    entries_res = await db.execute(
        select(CommunityTournamentEntry).where(CommunityTournamentEntry.tournament_id == tournament_id)
    )
    entries = entries_res.scalars().all()

    sorted_entries = sorted(entries, key=lambda e: e.points, reverse=True)
    standings = []
    for rank, entry in enumerate(sorted_entries, start=1):
        entry.rank = rank
        standings.append(
            {
                "entry_id": str(entry.id),
                "user_id": str(entry.user_id),
                "points": entry.points,
                "rank": rank,
            }
        )

    await db.flush()
    return standings


async def create_community(
    db: AsyncSession,
    name: str,
    slug: str,
    owner_id: uuid.UUID,
    description: str | None = None,
    visibility: str = "public",
    require_approval: bool = False,
) -> Community:
    """Creates a community and registers the owner as its first member."""
    community = Community(
        name=name.strip(),
        slug=slug.strip().lower(),
        description=description.strip() if description else None,
        owner_id=owner_id,
        visibility=visibility if visibility in ("public", "private") else "public",
        require_approval=require_approval,
        invite_code=None,
    )
    db.add(community)
    await db.flush()

    db.add(
        CommunityMember(
            community_id=community.id,
            user_id=owner_id,
            role="owner",
            status="active",
        )
    )
    await db.flush()

    # The community always has a Top Agent persona.
    await get_or_create_community_top_agent(db, community.id)
    return community


async def get_community_membership(
    db: AsyncSession,
    community_id: uuid.UUID,
    user_id: uuid.UUID,
) -> CommunityMember | None:
    """Returns the user's membership record for a community, if any."""
    return (
        await db.execute(
            select(CommunityMember).where(
                CommunityMember.community_id == community_id,
                CommunityMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def join_community(
    db: AsyncSession,
    community: Community,
    user_id: uuid.UUID,
    invite_code: str | None = None,
) -> tuple[str, CommunityMember]:
    """Joins a community. Returns (status, membership).

    status: "joined" | "pending" | "already_member" | "already_pending" | "invalid_code"
    """
    existing = await get_community_membership(db, community.id, user_id)
    if existing:
        if existing.status == "active":
            return "already_member", existing
        return "already_pending", existing

    if community.visibility == "private" and (
        not invite_code or not community.invite_code or invite_code.strip() != community.invite_code
    ):
        return "invalid_code", None  # type: ignore[return-value]

    needs_approval = community.require_approval
    member = CommunityMember(
        community_id=community.id,
        user_id=user_id,
        role="member",
        status="pending" if needs_approval else "active",
    )
    db.add(member)
    await db.flush()
    return ("pending" if needs_approval else "joined"), member


async def leave_community(
    db: AsyncSession,
    community_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Removes the user from a community. Owners cannot leave (must delete/transfer)."""
    member = await get_community_membership(db, community_id, user_id)
    if not member:
        return False
    if member.role == "owner":
        return False
    await db.delete(member)
    await db.flush()
    return True


async def approve_community_member(
    db: AsyncSession,
    community_id: uuid.UUID,
    member_id: uuid.UUID,
    approve: bool,
) -> str:
    """Approves or rejects a pending membership. Returns "approved" | "rejected" | "not_found"."""
    member = (
        await db.execute(
            select(CommunityMember).where(
                CommunityMember.id == member_id,
                CommunityMember.community_id == community_id,
            )
        )
    ).scalar_one_or_none()
    if not member:
        return "not_found"
    if approve:
        member.status = "active"
        return "approved"
    await db.delete(member)
    await db.flush()
    return "rejected"


async def rotate_community_invite_code(
    db: AsyncSession,
    community: Community,
) -> str:
    """Generates a fresh invite code for a community."""
    code = uuid.uuid4().hex[:12].upper()
    community.invite_code = code
    await db.flush()
    return code


async def run_community_delegated_governance(
    db: AsyncSession,
    community_id: uuid.UUID,
) -> dict[str, int]:
    """Audits all delegated community submissives and updates their compliance scores."""
    delegations_res = await db.execute(
        select(CommunityMemberDelegation).where(CommunityMemberDelegation.community_id == community_id)
    )
    delegations = delegations_res.scalars().all()

    audited_count = len(delegations)
    for d in delegations:
        d.compliance_score = min(100.0, d.compliance_score + 1.0)

    return {"status": "success", "audited_submissives": audited_count}
