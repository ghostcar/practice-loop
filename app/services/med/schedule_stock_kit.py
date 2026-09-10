"""CRUD: schedules, stocks, kits."""

from __future__ import annotations

import contextlib
import uuid
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medication import (
    FOOD_RELATIONS,
    FREQUENCY_TYPES,
    Medication,
    MedKit,
    MedSchedule,
    MedStock,
)
from app.services.med.graph import get_kit, get_med, get_schedule, get_stock


async def _resolve_kit_location(
    db: AsyncSession, user_id: uuid.UUID, location_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Валидация локации аптечки: системная или собственная пользователя."""
    if location_id is None:
        return None
    from app.models.task_location import TaskLocation

    loc = (
        await db.execute(
            select(TaskLocation).where(
                TaskLocation.id == location_id,
                TaskLocation.is_active.is_(True),
                or_(TaskLocation.owner_id.is_(None), TaskLocation.owner_id == user_id),
            )
        )
    ).scalar_one_or_none()
    if loc is None:
        raise ValueError("Invalid location")
    return location_id


# ─────────────────────────────────────────────────────────────────────────────
# Stocks
# ─────────────────────────────────────────────────────────────────────────────


async def create_stock(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    medication_id: uuid.UUID,
    quantity: str,
    unit: str,
    kit_id: str,
    lot_number: str,
    expiry_date: str,
    low_stock_threshold: str,
    notes: str,
) -> MedStock:
    m = await get_med(db, user_id, medication_id)
    try:
        qty = float(quantity or 0)
    except ValueError:
        qty = 0.0
    kit = None
    if kit_id and kit_id not in ("", "__none__"):
        kit = await get_kit(db, user_id, uuid.UUID(kit_id))
    expiry = None
    if expiry_date.strip():
        try:
            expiry = date.fromisoformat(expiry_date.strip())
        except ValueError:
            raise ValueError("Invalid expiry_date format (ISO 8601)") from None
    threshold = None
    if low_stock_threshold.strip():
        try:
            threshold = float(low_stock_threshold)
        except ValueError:
            threshold = None
    st = MedStock(
        user_id=user_id,
        medication_id=m.id,
        kit_id=kit.id if kit else None,
        quantity=qty,
        unit=(unit or "").strip()[:20] or m.unit,
        lot_number=(lot_number or "").strip()[:100] or None,
        expiry_date=expiry,
        low_stock_threshold=threshold,
        notes=(notes or "").strip() or None,
    )
    db.add(st)
    await db.flush()
    return st


async def delete_stock(db: AsyncSession, user_id: uuid.UUID, stock_id: uuid.UUID) -> None:
    st = await get_stock(db, user_id, stock_id)
    await db.delete(st)
    await db.flush()


async def update_stock(
    db: AsyncSession,
    user_id: uuid.UUID,
    stock_id: uuid.UUID,
    *,
    quantity: float | str,
    unit: str = "",
    lot_number: str = "",
    expiry_date: str = "",
    low_stock_threshold: str = "",
    notes: str = "",
    kit_id: str = "",
) -> MedStock:
    st = await get_stock(db, user_id, stock_id)
    try:
        qty = float(quantity)
    except (TypeError, ValueError):
        qty = st.quantity
    st.quantity = qty
    if unit.strip():
        st.unit = unit.strip()[:20]
    if lot_number is not None and lot_number.strip():
        st.lot_number = lot_number.strip()[:100]
    if expiry_date.strip():
        with contextlib.suppress(ValueError):
            st.expiry_date = date.fromisoformat(expiry_date.strip())
    if low_stock_threshold.strip():
        with contextlib.suppress(ValueError):
            st.low_stock_threshold = float(low_stock_threshold)
    if notes is not None:
        st.notes = notes.strip() or None
    if kit_id:
        if kit_id in ("__none__", "none"):
            st.kit_id = None
        else:
            kit = await get_kit(db, user_id, uuid.UUID(kit_id))
            st.kit_id = kit.id
    await db.flush()
    return st


# ─────────────────────────────────────────────────────────────────────────────
# Schedules
# ─────────────────────────────────────────────────────────────────────────────


async def create_schedule(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    medication_id: uuid.UUID,
    dose_quantity: str = "1",
    dose_unit: str = "",
    frequency_type: str = "daily",
    times_per_day: str = "",
    times_of_day: str = "",
    interval_hours: str = "",
    days_of_week: str = "",
    start_date: str = "",
    end_date: str = "",
    instructions: str = "",
    food_relation: str = "",
    duration_days: str = "",
    meal_offset_min: str = "",
    course_id: str = "",
    preferred_kit_id: str | uuid.UUID | None = None,
) -> MedSchedule:
    m = await get_med(db, user_id, medication_id)
    try:
        dose = float(dose_quantity or 1)
    except ValueError:
        dose = 1.0
    if frequency_type not in FREQUENCY_TYPES:
        frequency_type = "daily"
    times_list = None
    if times_of_day.strip():
        times_list = [x.strip()[:5] for x in times_of_day.split(",") if x.strip()]
    dow = None
    if days_of_week.strip():
        dow = [int(x) for x in days_of_week.split(",") if x.strip().isdigit()]
    sd = ed = None
    if start_date.strip():
        sd = date.fromisoformat(start_date.strip())
    if end_date.strip():
        ed = date.fromisoformat(end_date.strip())
    relation = food_relation.strip() if food_relation.strip() in FOOD_RELATIONS else None
    duration = int(duration_days) if duration_days.strip().isdigit() else None
    offset = int(meal_offset_min) if meal_offset_min.strip().lstrip("-").isdigit() else None
    if not ed and duration and sd:
        ed = sd + timedelta(days=duration - 1)
    cid = None
    if course_id and course_id not in ("", "__none__"):
        cid = course_id if isinstance(course_id, uuid.UUID) else uuid.UUID(str(course_id))
    pkid = None
    if preferred_kit_id and preferred_kit_id not in ("", "__none__", "none"):
        p_kid = preferred_kit_id if isinstance(preferred_kit_id, uuid.UUID) else uuid.UUID(str(preferred_kit_id))
        kit = await get_kit(db, user_id, p_kid)
        pkid = kit.id
    s = MedSchedule(
        user_id=user_id,
        medication_id=m.id,
        dose_quantity=dose,
        dose_unit=(dose_unit or "").strip()[:20] or m.unit,
        frequency_type=frequency_type,
        times_per_day=int(times_per_day) if times_per_day.strip().isdigit() else None,
        times_of_day=times_list,
        interval_hours=float(interval_hours) if interval_hours.strip() else None,
        days_of_week=dow,
        start_date=sd,
        end_date=ed,
        food_relation=relation,
        duration_days=duration,
        meal_offset_min=offset,
        course_id=cid,
        preferred_kit_id=pkid,
        instructions=(instructions or "").strip() or None,
    )
    db.add(s)
    await db.flush()
    return s


async def delete_schedule(db: AsyncSession, user_id: uuid.UUID, schedule_id: uuid.UUID) -> None:
    s = await get_schedule(db, user_id, schedule_id)
    await db.delete(s)
    await db.flush()


async def update_schedule(
    db: AsyncSession,
    user_id: uuid.UUID,
    schedule_id: uuid.UUID,
    *,
    dose_quantity: float | str = "1",
    dose_unit: str = "",
    frequency_type: str = "daily",
    times_per_day: str = "",
    times_of_day: str = "",
    interval_hours: str = "",
    days_of_week: str = "",
    start_date: str = "",
    end_date: str = "",
    instructions: str = "",
    food_relation: str = "",
    duration_days: str = "",
    meal_offset_min: str = "",
    preferred_kit_id: str | uuid.UUID | None = None,
) -> MedSchedule:
    s = await get_schedule(db, user_id, schedule_id)
    try:
        dose = float(dose_quantity)
    except (TypeError, ValueError):
        dose = s.dose_quantity
    s.dose_quantity = dose
    if preferred_kit_id is not None:
        if preferred_kit_id in ("", "__none__", "none"):
            s.preferred_kit_id = None
        else:
            p_kid = preferred_kit_id if isinstance(preferred_kit_id, uuid.UUID) else uuid.UUID(str(preferred_kit_id))
            kit = await get_kit(db, user_id, p_kid)
            s.preferred_kit_id = kit.id
    if dose_unit.strip():
        s.dose_unit = dose_unit.strip()[:20]
    if frequency_type in FREQUENCY_TYPES:
        s.frequency_type = frequency_type
    if times_of_day.strip():
        s.times_of_day = [x.strip()[:5] for x in times_of_day.split(",") if x.strip()]
    elif times_of_day == "":
        s.times_of_day = None
    if times_per_day.strip().isdigit():
        s.times_per_day = int(times_per_day.strip())
    elif times_per_day == "":
        s.times_per_day = None
    if interval_hours.strip():
        with contextlib.suppress(ValueError):
            s.interval_hours = float(interval_hours.strip())
    if days_of_week.strip():
        s.days_of_week = [int(x) for x in days_of_week.split(",") if x.strip().isdigit()]
    if start_date.strip():
        with contextlib.suppress(ValueError):
            s.start_date = date.fromisoformat(start_date.strip())
    if end_date.strip():
        with contextlib.suppress(ValueError):
            s.end_date = date.fromisoformat(end_date.strip())
    if food_relation.strip() in FOOD_RELATIONS:
        s.food_relation = food_relation.strip()
    elif food_relation == "":
        s.food_relation = None
    if duration_days.strip().isdigit():
        s.duration_days = int(duration_days.strip())
        if s.start_date and not end_date.strip():
            s.end_date = s.start_date + timedelta(days=s.duration_days - 1)
    if meal_offset_min.strip().lstrip("-").isdigit():
        s.meal_offset_min = int(meal_offset_min.strip())
    if instructions is not None:
        s.instructions = instructions.strip() or None
    await db.flush()
    return s


# ─────────────────────────────────────────────────────────────────────────────
# Kits
# ─────────────────────────────────────────────────────────────────────────────


async def create_kit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    location: str,
    notes: str,
    location_id: uuid.UUID | None = None,
) -> MedKit:
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    loc_id = await _resolve_kit_location(db, user_id, location_id)
    k = MedKit(
        user_id=user_id,
        name=name,
        location=(location or "").strip()[:200] or None,
        location_id=loc_id,
        notes=(notes or "").strip() or None,
    )
    db.add(k)
    await db.flush()
    return k


async def delete_kit(db: AsyncSession, user_id: uuid.UUID, kit_id: uuid.UUID) -> None:
    k = await get_kit(db, user_id, kit_id)
    await db.delete(k)
    await db.flush()


async def update_kit(
    db: AsyncSession,
    user_id: uuid.UUID,
    kit_id: uuid.UUID,
    *,
    name: str,
    location: str = "",
    location_id: uuid.UUID | None = None,
    notes: str = "",
) -> MedKit:
    k = await get_kit(db, user_id, kit_id)
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    loc_id = await _resolve_kit_location(db, user_id, location_id)
    k.name = name
    k.location = (location or "").strip()[:200] or None
    k.location_id = loc_id
    k.notes = (notes or "").strip() or None
    await db.flush()
    return k


async def add_stock_to_kit(
    db: AsyncSession,
    user_id: uuid.UUID,
    kit_id: uuid.UUID,
    *,
    medication_id: uuid.UUID,
    quantity: float,
    unit: str | None = None,
    expiry_date: str = "",
    lot_number: str = "",
    notes: str = "",
) -> MedStock:
    await get_kit(db, user_id, kit_id)
    med = await get_med(db, user_id, medication_id)
    try:
        qty = float(quantity or 0)
    except (TypeError, ValueError):
        qty = 0.0

    if qty <= 0:
        # Check if already registered in kit composition with zero stock
        stmt = select(MedStock).where(
            MedStock.user_id == user_id,
            MedStock.kit_id == kit_id,
            MedStock.medication_id == med.id,
            MedStock.quantity <= 0,
        )
        existing_zero = (await db.execute(stmt)).scalars().first()
        if existing_zero:
            if unit and unit.strip():
                existing_zero.unit = unit.strip()[:20]
            if notes and notes.strip():
                existing_zero.notes = notes.strip()
            await db.flush()
            return existing_zero

        st = MedStock(
            user_id=user_id,
            medication_id=med.id,
            kit_id=kit_id,
            quantity=0.0,
            unit=(unit or "").strip()[:20] or med.unit,
            lot_number=None,
            expiry_date=None,
            low_stock_threshold=None,
            notes=(notes or "").strip() or None,
        )
        db.add(st)
        await db.flush()
        return st

    # If replenishing (qty > 0) and an unstocked placeholder exists in this kit, update it
    stmt = select(MedStock).where(
        MedStock.user_id == user_id,
        MedStock.kit_id == kit_id,
        MedStock.medication_id == med.id,
        MedStock.quantity <= 0,
        MedStock.expiry_date.is_(None),
        MedStock.lot_number.is_(None),
    )
    placeholder = (await db.execute(stmt)).scalars().first()
    if placeholder:
        expiry = None
        if expiry_date.strip():
            try:
                expiry = date.fromisoformat(expiry_date.strip())
            except ValueError:
                raise ValueError("Invalid expiry_date format (ISO 8601)") from None
        placeholder.quantity = qty
        placeholder.unit = (unit or "").strip()[:20] or med.unit or placeholder.unit
        placeholder.expiry_date = expiry
        placeholder.lot_number = (lot_number or "").strip()[:100] or None
        if notes and notes.strip():
            placeholder.notes = notes.strip()
        await db.flush()
        return placeholder

    return await create_stock(
        db,
        user_id=user_id,
        medication_id=med.id,
        kit_id=str(kit_id),
        quantity=str(qty),
        unit=unit or med.unit or "",
        expiry_date=expiry_date,
        lot_number=lot_number,
        low_stock_threshold="",
        notes=notes,
    )


async def find_medication_by_barcode(
    db: AsyncSession,
    user_id: uuid.UUID,
    gtin: str | None = None,
    ean13: str | None = None,
) -> Medication | None:
    """Find a medication by matching GTIN/EAN-13 in name or notes."""
    candidates = [c for c in (gtin, ean13) if c]
    if not candidates:
        return None
    meds = (
        await db.execute(
            select(Medication).where(Medication.user_id == user_id, Medication.is_active == True)  # noqa: E712
        )
    ).scalars().all()
    for m in meds:
        for c in candidates:
            if m.notes and c in m.notes:
                return m
            if c in m.name:
                return m
    return None
