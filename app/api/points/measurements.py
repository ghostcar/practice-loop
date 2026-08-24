"""Body measurements — CRUD, charts data."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.models.life import BodyMeasurement
from app.models.user import User
from app.schemas.points_v2 import BodyMeasurementChart, BodyMeasurementCreate, BodyMeasurementOut

router = APIRouter(tags=["v2"])


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
        await db.refresh(existing)
        return BodyMeasurementOut.model_validate(existing)

    m = BodyMeasurement(user_id=user.id, **data.model_dump())
    db.add(m)
    await db.refresh(m)
    return BodyMeasurementOut.model_validate(m)
