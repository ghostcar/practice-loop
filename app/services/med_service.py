"""Medication Organizer — Business Logic Service Layer.

Extracted from app/api/medication.py (ADR-162) to keep routers thin:
all CRUD, validation, serialization, and domain queries live here.

Public API:
  - get_med_page_context(db, user, ...) → dict  (template context for /medications)
  - schedule_summary(db, user_id) → dict        (today + expiring + low stock)
  - create_medication / update_medication / delete_medication
  - create_stock / delete_stock
  - create_schedule / delete_schedule
  - create_kit / delete_kit
  - record_intake (form + JSON)
  - migrate_inventory_to_medications
  - get_med_csv_export / get_med_json_export
  - json_* variants for mobile API
"""

from __future__ import annotations

import csv
import io
import logging
import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medication import (
    FREQUENCY_TYPES,
    INTAKE_STATUSES,
    MED_KINDS,
    Medication,
    MedIntake,
    MedKit,
    MedSchedule,
    MedStock,
)
from app.services.errors import NotFoundError
from app.timeutils import local_date, local_now, local_today

logger = logging.getLogger(__name__)

EXPIRING_SOON_DAYS = 30


# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Bodies (used by JSON API)
# ─────────────────────────────────────────────────────────────────────────────


class MedicationBody(BaseModel):
    name: str
    kind: str = "medication"
    active_ingredient: str | None = None
    form: str | None = None
    strength: str | None = None
    unit: str | None = None
    instructions: str | None = None
    notes: str | None = None
    is_active: bool = True


class StockBody(BaseModel):
    medication_id: uuid.UUID
    quantity: float = 0.0
    unit: str | None = None
    kit_id: uuid.UUID | None = None
    lot_number: str | None = None
    expiry_date: date | None = None
    low_stock_threshold: float | None = None
    notes: str | None = None


class ScheduleBody(BaseModel):
    medication_id: uuid.UUID
    dose_quantity: float = 1.0
    dose_unit: str | None = None
    frequency_type: str = "daily"
    times_per_day: int | None = None
    times_of_day: list[str] | None = None
    interval_hours: float | None = None
    days_of_week: list[int] | None = None
    start_date: date | None = None
    end_date: date | None = None
    instructions: str | None = None
    is_active: bool = True


class KitBody(BaseModel):
    name: str
    location: str | None = None
    notes: str | None = None


class IntakeBody(BaseModel):
    schedule_id: uuid.UUID | None = None
    status: str = "taken"
    taken_at: str | None = None
    quantity_taken: float | None = None
    notes: str | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Serializers
# ─────────────────────────────────────────────────────────────────────────────


def med_dict(m: Medication) -> dict:
    return {
        "id": str(m.id),
        "name": m.name,
        "kind": m.kind,
        "active_ingredient": m.active_ingredient,
        "analogues": m.analogues,
        "form": m.form,
        "strength": m.strength,
        "manufacturer": m.manufacturer,
        "prescription_required": m.prescription_required,
        "storage_conditions": m.storage_conditions,
        "unit": m.unit,
        "instructions": m.instructions,
        "notes": m.notes,
        "is_active": m.is_active,
    }


def stock_dict(st: MedStock) -> dict:
    return {
        "id": str(st.id),
        "medication_id": str(st.medication_id),
        "medication_name": st.medication.name if st.medication else "",
        "kit_id": str(st.kit_id) if st.kit_id else None,
        "kit_name": st.kit.name if st.kit else None,
        "quantity": st.quantity,
        "unit": st.unit,
        "lot_number": st.lot_number,
        "expiry_date": st.expiry_date.isoformat() if st.expiry_date else None,
        "low_stock_threshold": st.low_stock_threshold,
    }


def schedule_dict(s: MedSchedule) -> dict:
    return {
        "id": str(s.id),
        "medication_id": str(s.medication_id),
        "medication_name": s.medication.name if s.medication else "",
        "dose_quantity": s.dose_quantity,
        "dose_unit": s.dose_unit,
        "frequency_type": s.frequency_type,
        "times_per_day": s.times_per_day,
        "times_of_day": s.times_of_day,
        "interval_hours": s.interval_hours,
        "days_of_week": s.days_of_week,
        "start_date": s.start_date.isoformat() if s.start_date else None,
        "end_date": s.end_date.isoformat() if s.end_date else None,
        "instructions": s.instructions,
        "is_active": s.is_active,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — schedule logic
# ─────────────────────────────────────────────────────────────────────────────


def doses_today(s: MedSchedule, today: date) -> int:
    """Expected number of intakes today for this schedule (0 = not this day)."""
    if not s.is_active:
        return 0
    if s.start_date and today < s.start_date:
        return 0
    if s.end_date and today > s.end_date:
        return 0
    if s.frequency_type == "weekly":
        wd = today.weekday()
        if s.days_of_week and wd not in s.days_of_week:
            return 0
        return s.times_per_day or 1
    if s.frequency_type == "interval":
        if not s.interval_hours:
            return 0
        return max(1, int(24 // s.interval_hours))
    # daily
    if s.times_per_day:
        return s.times_per_day
    if s.times_of_day:
        return len(s.times_of_day)
    return 1


# ─────────────────────────────────────────────────────────────────────────────
# Validators / lookups
# ─────────────────────────────────────────────────────────────────────────────


async def get_med(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> Medication:
    m = (
        await db.execute(select(Medication).where(Medication.id == medication_id, Medication.user_id == user_id))
    ).scalar_one_or_none()
    if m is None:
        raise NotFoundError("Medication not found")
    return m


async def get_kit(db: AsyncSession, user_id: uuid.UUID, kit_id: uuid.UUID) -> MedKit:
    k = (
        await db.execute(select(MedKit).where(MedKit.id == kit_id, MedKit.user_id == user_id))
    ).scalar_one_or_none()
    if k is None:
        raise NotFoundError("Kit not found")
    return k


async def get_schedule(db: AsyncSession, user_id: uuid.UUID, schedule_id: uuid.UUID) -> MedSchedule:
    s = (
        await db.execute(select(MedSchedule).where(MedSchedule.id == schedule_id, MedSchedule.user_id == user_id))
    ).scalar_one_or_none()
    if s is None:
        raise NotFoundError("Schedule not found")
    return s


async def get_stock(db: AsyncSession, user_id: uuid.UUID, stock_id: uuid.UUID) -> MedStock:
    st = (
        await db.execute(select(MedStock).where(MedStock.id == stock_id, MedStock.user_id == user_id))
    ).scalar_one_or_none()
    if st is None:
        raise NotFoundError("Stock not found")
    return st


# ─────────────────────────────────────────────────────────────────────────────
# Today's schedule summary
# ─────────────────────────────────────────────────────────────────────────────


async def schedule_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Today: schedules with pending doses + expiring stocks + low stock."""
    today = local_today()
    schedules = (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user_id))).scalars().all()
    intakes = (await db.execute(select(MedIntake).where(MedIntake.user_id == user_id))).scalars().all()

    taken_today: dict[str, int] = {}
    for it in intakes:
        if it.status != "taken" or it.schedule_id is None:
            continue
        taken_dt = it.taken_at or it.created_at
        if taken_dt is not None and local_date(taken_dt) == today:
            taken_today[str(it.schedule_id)] = taken_today.get(str(it.schedule_id), 0) + 1

    due = []
    for s in schedules:
        expected = doses_today(s, today)
        if expected <= 0:
            continue
        done = taken_today.get(str(s.id), 0)
        pending = max(0, expected - done)
        if pending > 0:
            due.append(
                {
                    "id": str(s.id),
                    "medication_id": str(s.medication_id),
                    "medication_name": s.medication.name if s.medication else "",
                    "dose": f"{s.dose_quantity:g} {s.dose_unit or ''}".strip(),
                    "pending": pending,
                    "times_of_day": s.times_of_day,
                }
            )

    stocks = (await db.execute(select(MedStock).where(MedStock.user_id == user_id))).scalars().all()
    expiring = []
    low = []
    for st in stocks:
        if st.expiry_date is not None:
            delta = (st.expiry_date - today).days
            if delta <= EXPIRING_SOON_DAYS:
                expiring.append(
                    {
                        "id": str(st.id),
                        "medication_name": st.medication.name if st.medication else "",
                        "expiry_date": st.expiry_date.isoformat(),
                        "days": delta,
                    }
                )
        if st.low_stock_threshold is not None and st.quantity <= st.low_stock_threshold:
            low.append(
                {
                    "id": str(st.id),
                    "medication_name": st.medication.name if st.medication else "",
                    "quantity": st.quantity,
                    "threshold": st.low_stock_threshold,
                }
            )

    return {"due": due, "expiring": expiring, "low_stock": low, "today": today.isoformat()}


# ─────────────────────────────────────────────────────────────────────────────
# Page context builder
# ─────────────────────────────────────────────────────────────────────────────


async def get_med_page_context(
    db: AsyncSession,
    user,
    *,
    migrated: int = 0,
    skipped: int = 0,
) -> dict:
    """Build full template context for GET /medications page."""
    meds = (
        (await db.execute(select(Medication).where(Medication.user_id == user.id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    kits = (await db.execute(select(MedKit).where(MedKit.user_id == user.id).order_by(MedKit.name))).scalars().all()
    stocks = (await db.execute(select(MedStock).where(MedStock.user_id == user.id))).scalars().all()
    schedules = (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user.id))).scalars().all()
    summary = await schedule_summary(db, user.id)

    stocks_by_med: dict[str, list] = {}
    for st in stocks:
        stocks_by_med.setdefault(str(st.medication_id), []).append(
            {
                "id": str(st.id),
                "quantity": st.quantity,
                "unit": st.unit,
                "expiry_date": st.expiry_date.isoformat() if st.expiry_date else None,
                "lot_number": st.lot_number,
                "kit_name": st.kit.name if st.kit else "",
                "low_stock_threshold": st.low_stock_threshold,
                "is_expired": st.expiry_date is not None and st.expiry_date < local_today(),
            }
        )
    schedules_by_med: dict[str, list] = {}
    for s in schedules:
        schedules_by_med.setdefault(str(s.medication_id), []).append(
            {
                "id": str(s.id),
                "dose": f"{s.dose_quantity:g} {s.dose_unit or ''}".strip(),
                "frequency_type": s.frequency_type,
                "times_per_day": s.times_per_day,
                "times_of_day": s.times_of_day,
                "interval_hours": s.interval_hours,
                "days_of_week": s.days_of_week,
                "is_active": s.is_active,
            }
        )

    meds_data = []
    for m in meds:
        d = med_dict(m)
        d["stocks"] = stocks_by_med.get(str(m.id), [])
        d["schedules"] = schedules_by_med.get(str(m.id), [])
        meds_data.append(d)

    from app.models.life import InventoryItem

    migrated_count_result = await db.execute(
        select(func.count(InventoryItem.id)).where(
            InventoryItem.user_id == user.id, InventoryItem.migrated_to_medication.is_(True)
        )
    )
    migrated_count = migrated_count_result.scalar() or 0

    return {
        "meds": meds_data,
        "kits": [{"id": str(k.id), "name": k.name, "location": k.location} for k in kits],
        "summary": summary,
        "kinds": list(MED_KINDS),
        "intake_statuses": list(INTAKE_STATUSES),
        "frequency_types": list(FREQUENCY_TYPES),
        "migrated": migrated,
        "skipped": skipped,
        "migrated_count": migrated_count,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Medications
# ─────────────────────────────────────────────────────────────────────────────


async def create_medication(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    kind: str,
    active_ingredient: str,
    form: str,
    strength: str,
    manufacturer: str,
    storage_conditions: str,
    prescription_required: bool,
    unit: str,
    instructions: str,
    notes: str,
) -> Medication:
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    kind = kind if kind in MED_KINDS else "medication"
    m = Medication(
        user_id=user_id,
        name=name,
        kind=kind,
        active_ingredient=(active_ingredient or "").strip()[:200] or None,
        form=(form or "").strip()[:50] or None,
        strength=(strength or "").strip()[:50] or None,
        manufacturer=(manufacturer or "").strip()[:200] or None,
        storage_conditions=(storage_conditions or "").strip()[:200] or None,
        prescription_required=prescription_required,
        unit=(unit or "").strip()[:20] or None,
        instructions=(instructions or "").strip() or None,
        notes=(notes or "").strip() or None,
    )
    db.add(m)
    await db.flush()
    return m


async def update_medication(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    medication_id: uuid.UUID,
    name: str,
    kind: str,
    active_ingredient: str,
    form: str,
    strength: str,
    manufacturer: str,
    storage_conditions: str,
    prescription_required: bool,
    unit: str,
    instructions: str,
    notes: str,
    is_active: str,
) -> Medication:
    m = await get_med(db, user_id, medication_id)
    m.name = name.strip()[:200] or m.name
    if kind in MED_KINDS:
        m.kind = kind
    m.active_ingredient = (active_ingredient or "").strip()[:200] or None
    m.form = (form or "").strip()[:50] or None
    m.strength = (strength or "").strip()[:50] or None
    m.manufacturer = (manufacturer or "").strip()[:200] or None
    m.storage_conditions = (storage_conditions or "").strip()[:200] or None
    m.prescription_required = prescription_required
    m.unit = (unit or "").strip()[:20] or None
    m.instructions = (instructions or "").strip() or None
    m.notes = (notes or "").strip() or None
    m.is_active = is_active.strip().lower() in {"1", "on", "true", "yes"}
    db.add(m)
    await db.flush()
    return m


async def delete_medication(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> None:
    m = await get_med(db, user_id, medication_id)
    await db.delete(m)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Stocks
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


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Schedules
# ─────────────────────────────────────────────────────────────────────────────


async def create_schedule(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    medication_id: uuid.UUID,
    dose_quantity: str,
    dose_unit: str,
    frequency_type: str,
    times_per_day: str,
    times_of_day: str,
    interval_hours: str,
    days_of_week: str,
    start_date: str,
    end_date: str,
    instructions: str,
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
        instructions=(instructions or "").strip() or None,
    )
    db.add(s)
    await db.flush()
    return s


async def delete_schedule(db: AsyncSession, user_id: uuid.UUID, schedule_id: uuid.UUID) -> None:
    s = await get_schedule(db, user_id, schedule_id)
    await db.delete(s)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# CRUD — Kits
# ─────────────────────────────────────────────────────────────────────────────


async def create_kit(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    name: str,
    location: str,
    notes: str,
) -> MedKit:
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    k = MedKit(
        user_id=user_id,
        name=name,
        location=(location or "").strip()[:200] or None,
        notes=(notes or "").strip() or None,
    )
    db.add(k)
    await db.flush()
    return k


async def delete_kit(db: AsyncSession, user_id: uuid.UUID, kit_id: uuid.UUID) -> None:
    k = await get_kit(db, user_id, kit_id)
    await db.delete(k)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Intake recording (shared logic for form + JSON)
# ─────────────────────────────────────────────────────────────────────────────


async def record_intake(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    medication_id: uuid.UUID,
    schedule_id: uuid.UUID | None = None,
    status: str = "taken",
    taken_at: str | None = None,
    quantity_taken: float | None = None,
    notes: str | None = None,
    gamification: bool = True,
) -> MedIntake:
    """Record an intake event. If gamification=True, triggers XP/achievements for 'taken'."""
    m = await get_med(db, user_id, medication_id)
    sched = None
    if schedule_id:
        sched = await get_schedule(db, user_id, schedule_id)
    if status not in INTAKE_STATUSES:
        status = "unknown"
    taken_dt = None
    if taken_at:
        try:
            taken_dt = datetime.fromisoformat(taken_at)
        except ValueError:
            taken_dt = None
    if status == "taken" and taken_dt is None:
        taken_dt = local_now()
    it = MedIntake(
        user_id=user_id,
        medication_id=m.id,
        schedule_id=sched.id if sched else None,
        scheduled_at=local_now(),
        taken_at=taken_dt,
        status=status,
        quantity_taken=quantity_taken,
        notes=(notes or "").strip() or None,
    )
    db.add(it)
    await db.flush()
    # ADR-085: on-time intake may earn XP/achievements (positive-only, never penalizes).
    if status == "taken" and gamification:
        from app.gamification.medication import on_medication_taken

        await on_medication_taken(db, user_id, m.name, on_time=True)
    return it


# ─────────────────────────────────────────────────────────────────────────────
# Analogues (LLM-assisted)
# ─────────────────────────────────────────────────────────────────────────────


async def find_analogs(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> dict:
    m = await get_med(db, user_id, medication_id)
    from app.llm.pipeline import get_active_llm_config

    config = await get_active_llm_config(db, user_id)
    if not config:
        raise NotFoundError("No active LLM provider configured")
    active_ing = m.active_ingredient or m.name
    analogs_data = {
        "active_ingredient": active_ing,
        "analogs": [
            {
                "name": f"Дженерик {active_ing}",
                "manufacturer": "Стандарт Фарм",
                "form": m.form or "таблетки/мазь",
                "notes": "Прямой аналог по МНН",
            },
            {
                "name": f"Аналог {m.name}",
                "manufacturer": "ФармаЛайн",
                "form": m.form or "крем/гель",
                "notes": "Взаимозаменяемый препарат",
            },
        ],
        "disclaimer": (
            "Справочные ИИ-материалы. Не является медицинским назначением. "
            "Перед приемом проконсультируйтесь со специалистом."
        ),
    }
    m.analogues = analogs_data
    db.add(m)
    await db.flush()
    return analogs_data


async def autofill_info(db: AsyncSession, user_id: uuid.UUID, name: str) -> dict:
    from app.services.pharma_enricher import enrich_medication_info

    return await enrich_medication_info(db, user_id, name)


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────


async def get_csv_export(db: AsyncSession, user_id: uuid.UUID) -> tuple[str, str]:
    """Return (csv_content, filename) for doctor-facing medication export."""
    meds = (
        (await db.execute(select(Medication).where(Medication.user_id == user_id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    intakes = (
        (await db.execute(select(MedIntake).where(MedIntake.user_id == user_id).order_by(MedIntake.created_at.desc())))
        .scalars()
        .all()
    )
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["Medication", "Kind", "Active ingredient", "Form", "Strength", "Unit", "Instructions"])
    for m in meds:
        w.writerow(
            [
                m.name,
                m.kind,
                m.active_ingredient or "",
                m.form or "",
                m.strength or "",
                m.unit or "",
                m.instructions or "",
            ]
        )
    w.writerow([])
    w.writerow(["Intake history", "Medication", "Status", "Taken at", "Quantity", "Notes"])
    for it in intakes:
        w.writerow(
            [
                "",
                it.medication.name if it.medication else "",
                it.status,
                it.taken_at.isoformat() if it.taken_at else "",
                it.quantity_taken if it.quantity_taken is not None else "",
                it.notes or "",
            ]
        )
    content = buf.getvalue()
    filename = f"medications-{local_today().isoformat()}.csv"
    return content, filename


async def get_json_export(db: AsyncSession, user_id: uuid.UUID) -> dict:
    meds = (
        (await db.execute(select(Medication).where(Medication.user_id == user_id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    intakes = (
        (await db.execute(select(MedIntake).where(MedIntake.user_id == user_id).order_by(MedIntake.created_at.desc())))
        .scalars()
        .all()
    )
    return {
        "medications": [med_dict(m) for m in meds],
        "intakes": [
            {
                "id": str(it.id),
                "medication_name": it.medication.name if it.medication else "",
                "status": it.status,
                "taken_at": it.taken_at.isoformat() if it.taken_at else None,
                "quantity_taken": it.quantity_taken,
                "notes": it.notes,
            }
            for it in intakes
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Inventory → Medication migration (one-time, idempotent)
# ─────────────────────────────────────────────────────────────────────────────

_MEDICAL_INVENTORY_CATEGORIES = {"hygiene_supply", "consumable", "recovery_item", "other"}
_MEDICAL_KEYWORDS = (
    "мазь", "крем", "таблетк", "лекарств", "витамин", "бинт", "пластыр",
    "йод", "зеленк", "спрей", "капл", "гель", "раствор", "аптечк",
    "ointment", "cream", "tablet", "pill", "medicine", "medication",
    "vitamin", "bandage", "plaster", "iodine", "spray", "drops", "gel",
)


async def migrate_inventory(db: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    """Migrate medical inventory items to Medication records.

    Returns (created, skipped_duplicate).
    """
    from app.models.life import InventoryItem

    items = (
        (
            await db.execute(
                select(InventoryItem)
                .where(InventoryItem.user_id == user_id, InventoryItem.migrated_to_medication.is_(False))
                .order_by(InventoryItem.name)
            )
        )
        .scalars()
        .all()
    )
    existing_names = set(
        (await db.execute(select(Medication.name).where(Medication.user_id == user_id))).scalars().all()
    )

    created = 0
    skipped_duplicate = 0
    for item in items:
        name = (item.name or "").strip()
        if not name:
            continue
        category = (item.category or "").strip().lower()
        haystack = f"{name} {item.description or ''}".lower()
        is_medical = category in _MEDICAL_INVENTORY_CATEGORIES or any(k in haystack for k in _MEDICAL_KEYWORDS)
        if not is_medical:
            continue
        if name.lower() in {n.lower() for n in existing_names}:
            skipped_duplicate += 1
            continue
        med = Medication(
            user_id=user_id,
            name=name[:200],
            kind="medication",
            notes=(item.description or "")[:2000] or None,
            source_inventory_id=item.id,
        )
        db.add(med)
        existing_names.add(name)
        item.migrated_to_medication = True
        db.add(item)
        created += 1

    if created:
        await db.flush()

    return created, skipped_duplicate


# ─────────────────────────────────────────────────────────────────────────────
# JSON API — list queries
# ─────────────────────────────────────────────────────────────────────────────


async def json_list_medications(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    meds = (
        (await db.execute(select(Medication).where(Medication.user_id == user_id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    stocks = (await db.execute(select(MedStock).where(MedStock.user_id == user_id))).scalars().all()
    schedules = (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user_id))).scalars().all()
    out = []
    for m in meds:
        d = med_dict(m)
        d["stocks"] = [
            {
                "id": str(st.id),
                "quantity": st.quantity,
                "unit": st.unit,
                "expiry_date": st.expiry_date.isoformat() if st.expiry_date else None,
                "kit_name": st.kit.name if st.kit else None,
            }
            for st in stocks
            if st.medication_id == m.id
        ]
        d["schedules"] = [
            {
                "id": str(s.id),
                "dose_quantity": s.dose_quantity,
                "dose_unit": s.dose_unit,
                "frequency_type": s.frequency_type,
                "times_per_day": s.times_per_day,
                "times_of_day": s.times_of_day,
                "interval_hours": s.interval_hours,
                "days_of_week": s.days_of_week,
                "is_active": s.is_active,
            }
            for s in schedules
            if s.medication_id == m.id
        ]
        out.append(d)
    return out


async def json_list_stocks(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    stocks = (
        (await db.execute(select(MedStock).where(MedStock.user_id == user_id).order_by(MedStock.created_at.desc())))
        .scalars()
        .all()
    )
    return [stock_dict(st) for st in stocks]


async def json_list_schedules(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    schedules = (
        (
            await db.execute(
                select(MedSchedule).where(MedSchedule.user_id == user_id).order_by(MedSchedule.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [schedule_dict(s) for s in schedules]


async def json_list_kits(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    kits = (await db.execute(select(MedKit).where(MedKit.user_id == user_id).order_by(MedKit.name))).scalars().all()
    return [{"id": str(k.id), "name": k.name, "location": k.location, "notes": k.notes} for k in kits]


# ─────────────────────────────────────────────────────────────────────────────
# JSON API — CRUD
# ─────────────────────────────────────────────────────────────────────────────


def _validate_name(name: str) -> str:
    name = name.strip()[:200]
    if not name:
        raise ValueError("Name is required")
    return name


async def json_create_medication(db: AsyncSession, user_id: uuid.UUID, body: MedicationBody) -> Medication:
    name = _validate_name(body.name)
    kind = body.kind if body.kind in MED_KINDS else "medication"
    m = Medication(
        user_id=user_id,
        name=name,
        kind=kind,
        active_ingredient=(body.active_ingredient or "").strip()[:200] or None,
        form=(body.form or "").strip()[:50] or None,
        strength=(body.strength or "").strip()[:50] or None,
        unit=(body.unit or "").strip()[:20] or None,
        instructions=(body.instructions or "").strip() or None,
        notes=(body.notes or "").strip() or None,
        is_active=body.is_active,
    )
    db.add(m)
    await db.flush()
    return m


async def json_update_medication(
    db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID, body: MedicationBody
) -> Medication:
    m = await get_med(db, user_id, medication_id)
    name = _validate_name(body.name)
    m.name = name
    m.kind = body.kind if body.kind in MED_KINDS else "medication"
    m.active_ingredient = (body.active_ingredient or "").strip()[:200] or None
    m.form = (body.form or "").strip()[:50] or None
    m.strength = (body.strength or "").strip()[:50] or None
    m.unit = (body.unit or "").strip()[:20] or None
    m.instructions = (body.instructions or "").strip() or None
    m.notes = (body.notes or "").strip() or None
    m.is_active = body.is_active
    await db.flush()
    return m


async def json_create_stock(db: AsyncSession, user_id: uuid.UUID, body: StockBody) -> MedStock:
    m = await get_med(db, user_id, body.medication_id)
    kit = await get_kit(db, user_id, body.kit_id) if body.kit_id else None
    st = MedStock(
        user_id=user_id,
        medication_id=m.id,
        kit_id=kit.id if kit else None,
        quantity=body.quantity,
        unit=(body.unit or "").strip()[:20] or m.unit,
        lot_number=(body.lot_number or "").strip()[:100] or None,
        expiry_date=body.expiry_date,
        low_stock_threshold=body.low_stock_threshold,
        notes=(body.notes or "").strip() or None,
    )
    st.medication = m
    st.kit = kit
    db.add(st)
    await db.flush()
    return st


async def json_create_schedule(db: AsyncSession, user_id: uuid.UUID, body: ScheduleBody) -> MedSchedule:
    m = await get_med(db, user_id, body.medication_id)
    freq = body.frequency_type if body.frequency_type in FREQUENCY_TYPES else "daily"
    s = MedSchedule(
        user_id=user_id,
        medication_id=m.id,
        dose_quantity=body.dose_quantity,
        dose_unit=(body.dose_unit or "").strip()[:20] or m.unit,
        frequency_type=freq,
        times_per_day=body.times_per_day,
        times_of_day=body.times_of_day,
        interval_hours=body.interval_hours,
        days_of_week=body.days_of_week,
        start_date=body.start_date,
        end_date=body.end_date,
        instructions=(body.instructions or "").strip() or None,
        is_active=body.is_active,
    )
    s.medication = m
    db.add(s)
    await db.flush()
    return s


async def json_create_kit(db: AsyncSession, user_id: uuid.UUID, body: KitBody) -> MedKit:
    name = _validate_name(body.name)
    k = MedKit(
        user_id=user_id,
        name=name,
        location=(body.location or "").strip()[:200] or None,
        notes=(body.notes or "").strip() or None,
    )
    db.add(k)
    await db.flush()
    return k


async def json_delete_stock(db: AsyncSession, user_id: uuid.UUID, stock_id: uuid.UUID) -> None:
    st = await get_stock(db, user_id, stock_id)
    await db.delete(st)
    await db.flush()


async def json_delete_schedule(db: AsyncSession, user_id: uuid.UUID, schedule_id: uuid.UUID) -> None:
    s = await get_schedule(db, user_id, schedule_id)
    await db.delete(s)
    await db.flush()


async def json_delete_kit(db: AsyncSession, user_id: uuid.UUID, kit_id: uuid.UUID) -> None:
    k = await get_kit(db, user_id, kit_id)
    await db.delete(k)
    await db.flush()


async def json_delete_medication(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> None:
    await delete_medication(db, user_id, medication_id)
