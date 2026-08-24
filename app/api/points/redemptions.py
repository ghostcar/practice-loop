"""Penalty redemptions — list, complete (recover points), skip."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.points.helpers import _get_progress
from app.database import get_db
from app.models.points import PenaltyRedemption, PointsTransaction
from app.models.user import User

router = APIRouter(tags=["v2"])


@router.get("/points/redemptions")
async def list_redemptions(
    status: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List penalty redemptions for the user."""
    query = (
        select(PenaltyRedemption)
        .where(PenaltyRedemption.user_id == user.id)
        .order_by(PenaltyRedemption.status.asc(), PenaltyRedemption.created_at.desc())
    )
    if status:
        query = query.where(PenaltyRedemption.status == status)
    result = await db.execute(query)
    redemptions = result.scalars().all()
    return [
        {
            "id": str(r.id),
            "redemption_type": r.redemption_type,
            "duration_min": r.duration_min,
            "count": r.count,
            "description": r.description,
            "status": r.status,
            "escalation_level": r.escalation_level,
            "points_value": r.points_value,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        }
        for r in redemptions
    ]


@router.post("/points/redemptions/{redemption_id}/complete")
async def complete_redemption(
    redemption_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark a redemption as completed and award points."""
    result = await db.execute(
        select(PenaltyRedemption).where(
            PenaltyRedemption.id == redemption_id,
            PenaltyRedemption.user_id == user.id,
        )
    )
    redemption = result.scalar_one_or_none()
    if not redemption:
        raise HTTPException(404, "Redemption not found")
    if redemption.status != "pending":
        raise HTTPException(400, f"Redemption already {redemption.status}")

    redemption.status = "completed"
    redemption.completed_at = datetime.now(UTC)
    db.add(redemption)

    # Award back the points value
    if redemption.points_value > 0:
        progress = await _get_progress(db, user.id)
        progress.points_balance += redemption.points_value
        db.add(progress)

        txn = PointsTransaction(
            user_id=user.id,
            amount=redemption.points_value,
            transaction_type="redeem",
            reason=f"Redemption completed: {redemption.redemption_type} ({redemption.duration_min}m)",
            entity_id=redemption.entity_id,
            activity_log_id=redemption.activity_log_id,
        )
        db.add(txn)
    return {"status": "completed", "points_recovered": redemption.points_value}


@router.post("/points/redemptions/{redemption_id}/skip")
async def skip_redemption(
    redemption_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Skip a redemption without recovering points."""
    result = await db.execute(
        select(PenaltyRedemption).where(
            PenaltyRedemption.id == redemption_id,
            PenaltyRedemption.user_id == user.id,
        )
    )
    redemption = result.scalar_one_or_none()
    if not redemption:
        raise HTTPException(404, "Redemption not found")

    redemption.status = "skipped"
    db.add(redemption)
    return {"status": "skipped"}
