"""Points balance — view balance, spend points."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.points.helpers import _get_progress
from app.database import get_db
from app.models.entity import Entity
from app.models.points import PointsTransaction
from app.models.user import User
from app.schemas.points_v2 import PointsBalanceOut, PointsTransactionOut

router = APIRouter(tags=["v2"])


@router.get("/points/balance", response_model=PointsBalanceOut)
async def get_points_balance(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get user's points balance and recent transactions."""
    progress = await _get_progress(db, user.id)
    result = await db.execute(
        select(PointsTransaction)
        .where(PointsTransaction.user_id == user.id)
        .order_by(PointsTransaction.created_at.desc())
        .limit(20)
    )
    txns = [PointsTransactionOut.model_validate(t) for t in result.scalars().all()]

    # Get thresholds only from entities the user can see (own or public) —
    # never from another user's private entity (audit: cross-user leak).
    thresholds = None
    result_e = await db.execute(
        select(Entity.gamification_config)
        .where(
            Entity.gamification_config.is_not(None),
            (Entity.owner_id == user.id) | Entity.is_public.is_(True),
        )
        .limit(1)
    )
    cfg = result_e.scalar_one_or_none()
    if cfg and isinstance(cfg, dict) and "thresholds" in cfg:
        from app.schemas.points_v2 import ThresholdConfig

        thresholds = ThresholdConfig(**cfg["thresholds"])

    return PointsBalanceOut(
        points_balance=progress.points_balance,
        xp=progress.xp,
        level=progress.level,
        thresholds=thresholds,
        recent_transactions=txns,
    )


@router.post("/points/spend")
async def spend_points(
    amount: int = Query(gt=0),
    reason: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Spend points on a reward."""
    progress = await _get_progress(db, user.id)
    if progress.points_balance < amount:
        raise HTTPException(400, f"Not enough points. Balance: {progress.points_balance}")

    progress.points_balance -= amount
    txn = PointsTransaction(
        user_id=user.id,
        amount=-amount,
        transaction_type="spend",
        reason=reason or "Points spent",
    )
    db.add(progress)
    db.add(txn)
    await db.commit()
    return {"new_balance": progress.points_balance}
