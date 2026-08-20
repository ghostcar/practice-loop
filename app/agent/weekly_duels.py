"""Weekly 1-on-1 Duels & Challenge Engine."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.duels import UserDuel

logger = logging.getLogger(__name__)


async def create_weekly_user_duel(
    db: AsyncSession,
    challenger_id: uuid.UUID,
    opponent_id: uuid.UUID,
) -> UserDuel:
    """Creates a new 1-on-1 weekly challenge duel between users."""
    duel = UserDuel(
        challenger_id=challenger_id,
        opponent_id=opponent_id,
        status="active",
        challenger_score=100,
        opponent_score=150,
    )
    db.add(duel)
    await db.flush()
    return duel


async def process_duel_scores_and_determine_winner(
    db: AsyncSession,
    duel_id: uuid.UUID,
) -> dict[str, Any]:
    """Processes final scores and crowns weekly duel winner."""
    duel = (await db.execute(select(UserDuel).where(UserDuel.id == duel_id))).scalar_one_or_none()

    if not duel:
        return {"status": "error", "reason": "duel_not_found"}

    winner_id = duel.challenger_id if duel.challenger_score >= duel.opponent_score else duel.opponent_id

    duel.status = "completed"
    duel.winner_id = winner_id
    duel.ended_at = datetime.now()
    await db.flush()

    return {
        "status": "completed",
        "duel_id": str(duel.id),
        "winner_id": str(winner_id),
        "challenger_score": duel.challenger_score,
        "opponent_score": duel.opponent_score,
    }
