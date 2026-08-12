"""Chart data endpoints — activity, points trend, XP, category breakdown, completion rate."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.entity import Entity
from app.models.user import User

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
        select(
            func.date(ActivityLog.created_at).label("day"),
            func.count(ActivityLog.id).label("total"),
            func.sum(case((ActivityLog.status == "completed", 1), else_=0)).label("completed"),
            func.sum(case((ActivityLog.status == "stopped", 1), else_=0)).label("stopped"),
        )
        .where(ActivityLog.user_id == user.id, ActivityLog.created_at >= cutoff)
        .group_by(func.date(ActivityLog.created_at))
        .order_by(func.date(ActivityLog.created_at))
    )
    rows = result.all()

    # Build daily arrays
    labels = []
    completed = []
    stopped = []
    planned = []
    for i in range(days):
        d = date.today() - timedelta(days=days - 1 - i)
        labels.append(d.strftime("%a %d"))
        match = next((r for r in rows if str(r.day) == d.isoformat()), None)
        c = int(match.completed or 0) if match else 0
        s_count = int(match.stopped or 0) if match else 0
        t = int(match.total or 0) if match else 0
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

    # Get daily net change
    result = await db.execute(
        select(
            func.date(PointsTransaction.created_at).label("day"),
            func.sum(PointsTransaction.amount).label("net"),
        )
        .where(PointsTransaction.user_id == user.id, PointsTransaction.created_at >= cutoff)
        .group_by(func.date(PointsTransaction.created_at))
        .order_by(func.date(PointsTransaction.created_at))
    )
    rows = {str(r.day): int(r.net or 0) for r in result.all()}

    # Build cumulative balance
    labels = []
    balance = []
    cumulative = 0
    for i in range(days):
        d = date.today() - timedelta(days=days - 1 - i)
        labels.append(d.strftime("%d %b"))
        cumulative += rows.get(d.isoformat(), 0)
        balance.append(cumulative)

    # Transaction type breakdown
    type_result = await db.execute(
        select(
            PointsTransaction.transaction_type,
            func.sum(PointsTransaction.amount).label("total"),
        )
        .where(PointsTransaction.user_id == user.id, PointsTransaction.created_at >= cutoff)
        .group_by(PointsTransaction.transaction_type)
    )
    breakdown = {r.transaction_type: abs(int(r.total or 0)) for r in type_result.all()}

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
        select(
            func.date(ActivityLog.created_at).label("day"),
            func.sum(ActivityLog.points_awarded).label("points"),
        )
        .where(
            ActivityLog.user_id == user.id,
            ActivityLog.created_at >= cutoff,
            ActivityLog.status == "completed",
        )
        .group_by(func.date(ActivityLog.created_at))
        .order_by(func.date(ActivityLog.created_at))
    )
    rows = {str(r.day): int(r.points or 0) for r in result.all()}

    labels = []
    values = []
    for i in range(days):
        d = date.today() - timedelta(days=days - 1 - i)
        labels.append(d.strftime("%a"))
        values.append(rows.get(d.isoformat(), 0))

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
        select(
            func.date(ActivityLog.created_at).label("day"),
            func.count(ActivityLog.id).label("total"),
            func.sum(case((ActivityLog.status == "completed", 1), else_=0)).label("completed"),
        )
        .where(ActivityLog.user_id == user.id, ActivityLog.created_at >= cutoff)
        .group_by(func.date(ActivityLog.created_at))
        .order_by(func.date(ActivityLog.created_at))
    )
    rows = {str(r.day): (int(r.completed or 0), int(r.total or 0)) for r in result.all()}

    labels = []
    rates = []
    overall_completed = 0
    overall_total = 0
    for i in range(days):
        d = date.today() - timedelta(days=days - 1 - i)
        labels.append(d.strftime("%a"))
        c, t = rows.get(d.isoformat(), (0, 0))
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
