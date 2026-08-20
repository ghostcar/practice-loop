"""Community Seasons & Tiered Leagues Promotion Engine."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.community_leagues import UserLeagueTier

logger = logging.getLogger(__name__)

LEAGUE_HIERARCHY = ["bronze", "silver", "gold", "master"]


async def get_or_create_user_league_tier(
    db: AsyncSession,
    community_id: uuid.UUID,
    user_id: uuid.UUID,
) -> UserLeagueTier:
    """Gets or initializes user league tier in a community."""
    tier_entry = (
        await db.execute(
            select(UserLeagueTier).where(
                UserLeagueTier.community_id == community_id,
                UserLeagueTier.user_id == user_id,
            )
        )
    ).scalar_one_or_none()

    if not tier_entry:
        tier_entry = UserLeagueTier(
            community_id=community_id,
            user_id=user_id,
            league_tier="bronze",
        )
        db.add(tier_entry)
        await db.flush()

    return tier_entry


async def promote_user_league_tier(
    db: AsyncSession,
    community_id: uuid.UUID,
    user_id: uuid.UUID,
) -> dict[str, Any]:
    """Promotes user to the next league division."""
    tier_entry = await get_or_create_user_league_tier(db, community_id, user_id)
    current = tier_entry.league_tier

    idx = LEAGUE_HIERARCHY.index(current) if current in LEAGUE_HIERARCHY else 0
    next_idx = min(len(LEAGUE_HIERARCHY) - 1, idx + 1)
    new_tier = LEAGUE_HIERARCHY[next_idx]

    tier_entry.league_tier = new_tier
    await db.flush()

    return {
        "status": "promoted",
        "previous_tier": current,
        "new_tier": new_tier,
        "community_id": str(community_id),
        "user_id": str(user_id),
    }
