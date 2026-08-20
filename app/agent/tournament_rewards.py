"""Tournament Rewards & Badges Awarding Engine."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.achievement import Achievement, UserAchievement
from app.models.community_agent import CommunityTournament, CommunityTournamentEntry

logger = logging.getLogger(__name__)

TOURNAMENT_BADGES = {
    1: {
        "code": "tournament_gold_champion",
        "name": "🥇 Чемпион Турнира Сообщества",
        "description": "Завоевал 1-е место в публичном турнире ИИ-Верхнего Сообщества.",
        "color": "amber",
    },
    2: {
        "code": "tournament_silver_runner_up",
        "name": "🥈 Серебряный Призер Турнира",
        "description": "Занял 2-е место в публичном турнире ИИ-Верхнего Сообщества.",
        "color": "archive-300",
    },
    3: {
        "code": "tournament_bronze_podium",
        "name": "🥉 Бронзовый Подиум Турнира",
        "description": "Занял 3-е место в публичном турнире ИИ-Верхнего Сообщества.",
        "color": "amber-700",
    },
}


async def get_or_create_tournament_badge(
    db: AsyncSession,
    rank: int,
) -> Achievement:
    """Gets or creates the tournament badge achievement definition for rank 1, 2, or 3."""
    info = TOURNAMENT_BADGES.get(rank, TOURNAMENT_BADGES[3])
    ach_res = await db.execute(select(Achievement).where(Achievement.code == info["code"]))
    badge = ach_res.scalar_one_or_none()

    if not badge:
        badge = Achievement(
            code=info["code"],
            name=info["name"],
            description=info["description"],
            condition_type="tournament_winner",
            condition_value=rank,
            color=info["color"],
        )
        db.add(badge)
        await db.flush()

    return badge


async def award_tournament_prizes(
    db: AsyncSession,
    tournament_id: uuid.UUID,
) -> dict[str, Any]:
    """Recalculates standings and awards exclusive badges & achievements to top 3 winners."""
    t_res = await db.execute(select(CommunityTournament).where(CommunityTournament.id == tournament_id))
    tournament = t_res.scalar_one_or_none()

    if not tournament:
        return {"status": "error", "reason": "tournament_not_found"}

    entries_res = await db.execute(
        select(CommunityTournamentEntry)
        .where(CommunityTournamentEntry.tournament_id == tournament_id)
        .order_by(CommunityTournamentEntry.points.desc())
    )
    entries = entries_res.scalars().all()

    awarded = []
    for rank_idx, entry in enumerate(entries[:3], start=1):
        entry.rank = rank_idx
        badge = await get_or_create_tournament_badge(db, rank_idx)

        # Check if already awarded
        ua_res = await db.execute(
            select(UserAchievement).where(
                UserAchievement.user_id == entry.user_id,
                UserAchievement.achievement_id == badge.id,
            )
        )
        if not ua_res.scalar_one_or_none():
            ua = UserAchievement(
                user_id=entry.user_id,
                achievement_id=badge.id,
                context=f"Турнир #{tournament_id} | Ранг #{rank_idx} | Очки: {entry.points}",
            )
            db.add(ua)

        awarded.append({"user_id": str(entry.user_id), "rank": rank_idx, "badge_code": badge.code})

    tournament.status = "completed"
    await db.flush()

    return {
        "status": "success",
        "tournament_id": str(tournament_id),
        "awarded_winners_count": len(awarded),
        "winners": awarded,
    }
