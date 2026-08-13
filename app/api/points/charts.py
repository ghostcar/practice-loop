"""Chart data endpoints — activity, points trend, XP, category breakdown, completion rate.

Daily series are bucketed in Python by ``local_date(created_at)`` so each bar
falls on the device's local calendar day (matching the ``local_today()`` axis
labels) rather than the database's UTC date. The per-endpoint ``cutoff`` remains
a UTC instant; bucketing only affects which *day* a point is attributed to.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.entity import Entity
from app.models.user import User
from app.timeutils import local_date, local_today

router = APIRouter(tags=["v2"])


@router.get("/charts/activity")
async def get_activity_chart(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Daily activity counts for bar chart."""
    from app.models.activity_log import ActivityLog

    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(ActivityLog.created_at, ActivityLog.status).where(
            ActivityLog.user_id == user.id, ActivityLog.created_at >= cutoff
        )
    )

    today = local_today()
    buckets = {today - timedelta(days=days - 1 - i): [0, 0, 0] for i in range(days)}  # [total, completed, stopped]
    for created_at, status in result.all():
        d = local_date(created_at)
        if d in buckets:
            buckets[d][0] += 1
            if status == "completed":
                buckets[d][1] += 1
            elif status == "stopped":
                buckets[d][2] += 1

    labels = []
    completed = []
    stopped = []
    planned = []
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        labels.append(d.strftime("%a %d"))
        t, c, s_count = buckets[d]
        completed.append(c)
        stopped.append(s_count)
        planned.append(max(0, t - c - s_count))

    return {
        "labels": labels,
        "completed": completed,
        "stopped": stopped,
        "planned": planned,
    }


@router.get("/charts/points-trend")
async def get_points_trend(
    days: int = Query(default=30, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Daily points balance trend for line chart."""
    from app.models.points import PointsTransaction

    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(
            PointsTransaction.created_at,
            PointsTransaction.amount,
            PointsTransaction.transaction_type,
        ).where(PointsTransaction.user_id == user.id, PointsTransaction.created_at >= cutoff)
    )

    today = local_today()
    buckets = {today - timedelta(days=days - 1 - i): 0 for i in range(days)}
    type_sums: dict[str, int] = {}
    for created_at, amount, txn_type in result.all():
        amt = int(amount or 0)
        d = local_date(created_at)
        if d in buckets:
            buckets[d] += amt
        type_sums[txn_type or "other"] = type_sums.get(txn_type or "other", 0) + amt
    breakdown = {k: abs(v) for k, v in type_sums.items()}

    # Build cumulative balance
    labels = []
    balance = []
    cumulative = 0
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        labels.append(d.strftime("%d %b"))
        cumulative += buckets[d]
        balance.append(cumulative)

    return {
        "labels": labels,
        "balance": balance,
        "breakdown": breakdown,
    }


@router.get("/charts/xp-history")
async def get_xp_history(
    days: int = Query(default=7, ge=1, le=30),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Daily XP earned for sparkline chart."""
    from app.models.activity_log import ActivityLog

    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(ActivityLog.created_at, ActivityLog.points_awarded).where(
            ActivityLog.user_id == user.id,
            ActivityLog.created_at >= cutoff,
            ActivityLog.status == "completed",
        )
    )

    today = local_today()
    buckets = {today - timedelta(days=days - 1 - i): 0 for i in range(days)}
    for created_at, points in result.all():
        d = local_date(created_at)
        if d in buckets:
            buckets[d] += int(points or 0)

    labels = []
    values = []
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        labels.append(d.strftime("%a"))
        values.append(buckets[d])

    return {"labels": labels, "values": values}


@router.get("/charts/category-breakdown")
async def get_category_breakdown(
    days: int = Query(default=30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Task category distribution for donut/pie chart."""
    from app.models.activity_log import ActivityLog

    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(
            Entity.category,
            func.count(ActivityLog.id).label("cnt"),
        )
        .join(Entity, ActivityLog.entity_id == Entity.id)
        .where(
            ActivityLog.user_id == user.id,
            ActivityLog.created_at >= cutoff,
        )
        .group_by(Entity.category)
        .order_by(func.count(ActivityLog.id).desc())
    )
    categories = {}
    total = 0
    for row in result.all():
        cat = row.category or "other"
        cnt = int(row.cnt or 0)
        categories[cat] = cnt
        total += cnt

    return {
        "labels": list(categories.keys()),
        "values": list(categories.values()),
        "total": total,
    }


@router.get("/charts/completion-rate")
async def get_completion_rate(
    days: int = Query(default=7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Completion rate over time for gauge/sparkline."""
    from app.models.activity_log import ActivityLog

    cutoff = datetime.now(UTC) - timedelta(days=days)
    result = await db.execute(
        select(ActivityLog.created_at, ActivityLog.status).where(
            ActivityLog.user_id == user.id, ActivityLog.created_at >= cutoff
        )
    )

    today = local_today()
    buckets = {today - timedelta(days=days - 1 - i): [0, 0] for i in range(days)}  # [completed, total]
    for created_at, status in result.all():
        d = local_date(created_at)
        if d in buckets:
            buckets[d][1] += 1
            if status == "completed":
                buckets[d][0] += 1

    labels = []
    rates = []
    overall_completed = 0
    overall_total = 0
    for i in range(days):
        d = today - timedelta(days=days - 1 - i)
        labels.append(d.strftime("%a"))
        c, t = buckets[d]
        rate = round(c / max(t, 1) * 100)
        rates.append(rate)
        overall_completed += c
        overall_total += t

    overall_rate = round(overall_completed / max(overall_total, 1) * 100)

    return {
        "labels": labels,
        "rates": rates,
        "overall_rate": overall_rate,
        "total_tasks": overall_total,
        "completed_tasks": overall_completed,
    }
