"""API v2: points economy, schedule, measurements, inventory, gamification config."""

import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.entity import Entity
from app.models.life import BodyMeasurement, InventoryItem, ScheduleRule
from app.models.points import PenaltyRedemption, PointsProfile, PointsTransaction
from app.models.progress import UserProgress
from app.models.user import User
from app.schemas.points_v2 import (
    BodyMeasurementChart,
    BodyMeasurementCreate,
    BodyMeasurementOut,
    GamificationConfig,
    InventoryItemCreate,
    InventoryItemOut,
    InventoryItemUpdate,
    PointsBalanceOut,
    PointsProfileCreate,
    PointsProfileOut,
    PointsTransactionOut,
    ScheduleRuleCreate,
    ScheduleRuleOut,
)
from app.security import require_entity_owner
from app.services.uploads import delete_upload, save_image
from app.templates_setup import templates

router = APIRouter(prefix="/api/v2", tags=["v2"])


# ── Helper ──


async def _get_progress(db: AsyncSession, user_id: uuid.UUID) -> UserProgress:
    result = await db.execute(select(UserProgress).where(UserProgress.user_id == user_id))
    p = result.scalar_one_or_none()
    if p is None:
        p = UserProgress(user_id=user_id)
        db.add(p)
        await db.flush()
    return p


# ── Gamification Config ──


@router.get("/entities/{entity_id}/gamification")
async def get_gamification_config(
    entity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get gamification config for an entity (public or owned)."""
    result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user.id),
        )
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(404, "Entity not found")
    return {
        "entity_id": str(entity.id),
        "gamification_config": entity.gamification_config or {},
    }


@router.put("/entities/{entity_id}/gamification")
async def update_gamification_config(
    entity_id: uuid.UUID,
    config: GamificationConfig,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update gamification config for an entity (owner only)."""
    entity = await require_entity_owner(entity_id, user, db)
    entity.gamification_config = config.model_dump()
    db.add(entity)
    await db.commit()
    return {"status": "ok"}


# ── Points Balance ──


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


# ── Points Profiles ──


@router.get("/points/profiles", response_model=list[PointsProfileOut])
async def list_points_profiles(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(PointsProfile).where(PointsProfile.user_id == user.id))
    return [PointsProfileOut.model_validate(p) for p in result.scalars().all()]


@router.post("/points/profiles", response_model=PointsProfileOut)
async def create_points_profile(
    data: PointsProfileCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    profile = PointsProfile(
        user_id=user.id,
        name=data.name,
        config=data.config.model_dump(),
        is_default=data.is_default,
    )
    db.add(profile)
    await db.commit()
    await db.refresh(profile)
    return PointsProfileOut.model_validate(profile)


@router.delete("/points/profiles/{profile_id}")
async def delete_points_profile(
    profile_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(PointsProfile).where(PointsProfile.id == profile_id, PointsProfile.user_id == user.id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile not found")
    await db.delete(profile)
    await db.commit()
    return {"status": "deleted"}


@router.post("/entities/{entity_id}/assign-profile")
async def assign_profile_to_entity(
    entity_id: uuid.UUID,
    profile_id: uuid.UUID = Query(),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Assign a PointsProfile to an entity (owner only)."""
    entity = await require_entity_owner(entity_id, user, db)

    profile_result = await db.execute(
        select(PointsProfile).where(PointsProfile.id == profile_id, PointsProfile.user_id == user.id)
    )
    profile = profile_result.scalar_one_or_none()
    if not profile:
        raise HTTPException(404, "Profile not found")

    # Copy profile config to entity
    entity.gamification_config = profile.config
    if entity.gamification_config and isinstance(entity.gamification_config, dict):
        entity.gamification_config["points"]["profile_id"] = str(profile_id)
    db.add(entity)
    await db.commit()
    return {"status": "assigned", "profile_name": profile.name}


# ── Redemptions ──


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

    await db.commit()
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
    await db.commit()
    return {"status": "skipped"}


# ── Schedule ──


@router.get("/schedule/today")
async def get_today_schedule(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get schedule for today (returns rules for this day of week)."""
    today = datetime.now()
    dow = today.weekday()  # 0=Mon
    result = await db.execute(
        select(ScheduleRule)
        .where(
            ScheduleRule.user_id == user.id,
            ScheduleRule.is_active.is_(True),
            (ScheduleRule.day_of_week == dow) | (ScheduleRule.day_of_week == 7),
        )
        .order_by(ScheduleRule.start_time)
    )
    rules = result.scalars().all()
    out = []
    for r in rules:
        d = ScheduleRuleOut.model_validate(r).model_dump()
        d["day_of_week"] = r.day_of_week
        d["start_time"] = r.start_time.strftime("%H:%M") if r.start_time else None
        d["end_time"] = r.end_time.strftime("%H:%M") if r.end_time else None
        if r.entity:
            d["entity_name"] = r.entity.real_name
        out.append(d)
    return out


@router.post("/schedule/rules", response_model=ScheduleRuleOut)
async def create_schedule_rule(
    data: ScheduleRuleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rule = ScheduleRule(user_id=user.id, **data.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return ScheduleRuleOut.model_validate(rule)


@router.delete("/schedule/rules/{rule_id}")
async def delete_schedule_rule(
    rule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(select(ScheduleRule).where(ScheduleRule.id == rule_id, ScheduleRule.user_id == user.id))
    rule = result.scalar_one_or_none()
    if not rule:
        raise HTTPException(404, "Rule not found")
    await db.delete(rule)
    await db.commit()
    return {"status": "deleted"}


# ── Body Measurements ──


@router.get("/measurements", response_model=list[BodyMeasurementOut])
async def get_measurements(
    limit: int = Query(default=90, le=365),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(BodyMeasurement)
        .where(BodyMeasurement.user_id == user.id)
        .order_by(BodyMeasurement.measured_date.desc())
        .limit(limit)
    )
    return [BodyMeasurementOut.model_validate(m) for m in result.scalars().all()]


@router.get("/measurements/charts")
async def get_measurement_charts(
    metric: str = Query(default="weight"),
    limit: int = Query(default=90),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get chart data for a specific metric."""
    result = await db.execute(
        select(BodyMeasurement)
        .where(BodyMeasurement.user_id == user.id)
        .order_by(BodyMeasurement.measured_date.asc())
        .limit(limit * 2)  # 2 per day (morning + evening)
    )
    all_measurements = result.scalars().all()

    # Build chart data: one label per date, morning/evening values
    dates: dict[str, dict[str, float | None]] = {}
    for m in all_measurements:
        ds = m.measured_date.isoformat()
        if ds not in dates:
            dates[ds] = {"morning": None, "evening": None}
        val = getattr(m, metric, None)
        dates[ds][m.time_of_day] = val

    sorted_dates = sorted(dates.keys())[-limit:]
    return BodyMeasurementChart(
        metric=metric,
        labels=sorted_dates,
        morning=[dates[d]["morning"] for d in sorted_dates],
        evening=[dates[d]["evening"] for d in sorted_dates],
    )


@router.post("/measurements", response_model=BodyMeasurementOut)
async def create_measurement(
    data: BodyMeasurementCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Upsert: if same date + time_of_day exists, update
    result = await db.execute(
        select(BodyMeasurement).where(
            BodyMeasurement.user_id == user.id,
            BodyMeasurement.measured_date == data.measured_date,
            BodyMeasurement.time_of_day == data.time_of_day,
        )
    )
    existing = result.scalar_one_or_none()
    if existing:
        for k, v in data.model_dump(exclude={"measured_date", "time_of_day"}).items():
            setattr(existing, k, v)
        db.add(existing)
        await db.commit()
        await db.refresh(existing)
        return BodyMeasurementOut.model_validate(existing)

    m = BodyMeasurement(user_id=user.id, **data.model_dump())
    db.add(m)
    await db.commit()
    await db.refresh(m)
    return BodyMeasurementOut.model_validate(m)


# ── Inventory ──


class _ReorderPayload(BaseModel):
    ids: list[uuid.UUID]


@router.post("/inventory/reorder")
async def reorder_inventory(
    payload: _ReorderPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Persist drag&drop ordering of inventory items.

    Accepts a *subset* of items (the currently rendered, possibly filtered
    list) and re-ranks only those relative to each other; items not mentioned
    keep their original order. This makes drag&drop work with filters active.
    """
    result = await db.execute(select(InventoryItem).where(InventoryItem.user_id == user.id))
    items = list(result.scalars().all())
    by_id = {i.id: i for i in items}
    unknown = [iid for iid in payload.ids if iid not in by_id]
    if unknown:
        raise HTTPException(400, "Unknown item ids in payload")

    # Anchor: the smallest sort_order among the moved items determines where
    # the re-ranked block starts, so unmentioned items stay in place.
    moved = [by_id[iid] for iid in payload.ids]
    anchor = min((i.sort_order for i in moved), default=0)
    for pos, iid in enumerate(payload.ids):
        by_id[iid].sort_order = anchor + pos
        db.add(by_id[iid])

    # Re-normalize all items to dense ranks in the new relative order.
    ordered = sorted(items, key=lambda i: (i.sort_order, i.created_at))
    for pos, i in enumerate(ordered):
        i.sort_order = pos
        db.add(i)
    await db.flush()
    return {"status": "ok"}


@router.post("/inventory/{item_id}/image")
async def upload_inventory_image(
    item_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Upload (or replace) a photo for an inventory item."""
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.user_id == user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    url = await save_image(file, subdir="inventory")
    old = item.image_path
    item.image_path = url
    db.add(item)
    await db.commit()
    if old:
        delete_upload(old)
    return {"status": "ok", "image_path": url}


@router.delete("/inventory/{item_id}/image")
async def delete_inventory_image(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Remove the photo from an inventory item."""
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.user_id == user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    old = item.image_path
    item.image_path = None
    db.add(item)
    await db.commit()
    if old:
        delete_upload(old)
    return {"status": "ok"}


@router.get("/inventory", response_model=list[InventoryItemOut])
async def get_inventory(
    category: str | None = None,
    status: str | None = None,
    shopping_list: bool | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(InventoryItem).where(InventoryItem.user_id == user.id)
    if category:
        query = query.where(InventoryItem.category == category)
    if status:
        query = query.where(InventoryItem.status == status)
    if shopping_list is not None:
        query = query.where(InventoryItem.is_shopping_list == shopping_list)
    query = query.order_by(InventoryItem.sort_order.asc(), InventoryItem.priority.desc(), InventoryItem.name)
    result = await db.execute(query)
    return [InventoryItemOut.model_validate(i) for i in result.scalars().all()]


@router.get("/inventory/shopping-list", response_model=list[InventoryItemOut])
async def get_shopping_list(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(InventoryItem)
        .where(InventoryItem.user_id == user.id, InventoryItem.is_shopping_list.is_(True))
        .order_by(InventoryItem.priority.desc())
    )
    return [InventoryItemOut.model_validate(i) for i in result.scalars().all()]


@router.post("/inventory", response_model=InventoryItemOut)
async def create_inventory_item(
    data: InventoryItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    item = InventoryItem(user_id=user.id, **data.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return InventoryItemOut.model_validate(item)


@router.put("/inventory/{item_id}", response_model=InventoryItemOut)
async def update_inventory_item(
    item_id: uuid.UUID,
    data: InventoryItemUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.user_id == user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    for k, v in data.model_dump(exclude_none=True).items():
        setattr(item, k, v)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return InventoryItemOut.model_validate(item)


@router.delete("/inventory/{item_id}")
async def delete_inventory_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(InventoryItem).where(InventoryItem.id == item_id, InventoryItem.user_id == user.id)
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(404, "Item not found")
    await db.delete(item)
    await db.commit()
    return {"status": "deleted"}


# ── Chart Data ──


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
            func.sum(case((ActivityLog.status == "interrupted", 1), else_=0)).label("interrupted"),
        )
        .where(ActivityLog.user_id == user.id, ActivityLog.created_at >= cutoff)
        .group_by(func.date(ActivityLog.created_at))
        .order_by(func.date(ActivityLog.created_at))
    )
    rows = result.all()

    # Build daily arrays
    labels = []
    completed = []
    interrupted = []
    pending = []
    for i in range(days):
        d = date.today() - timedelta(days=days - 1 - i)
        labels.append(d.strftime("%a %d"))
        match = next((r for r in rows if str(r.day) == d.isoformat()), None)
        c = int(match.completed or 0) if match else 0
        i_count = int(match.interrupted or 0) if match else 0
        t = int(match.total or 0) if match else 0
        completed.append(c)
        interrupted.append(i_count)
        pending.append(max(0, t - c - i_count))

    return {
        "labels": labels,
        "completed": completed,
        "interrupted": interrupted,
        "pending": pending,
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


# ── HTML Pages ──


@router.get("/measurements/page", response_class=HTMLResponse)
async def measurements_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="measurements.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, "active_nav": "points"},
    )


@router.get("/inventory/page", response_class=HTMLResponse)
async def inventory_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="inventory.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme},
    )


@router.get("/schedule/page", response_class=HTMLResponse)
async def schedule_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="schedule.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme},
    )


@router.get("/points/page", response_class=HTMLResponse)
async def points_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="points.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme},
    )
