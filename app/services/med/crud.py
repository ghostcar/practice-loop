"""Medication CRUD and JSON API wrappers."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.medication import (
    MED_KINDS,
    Medication,
    MedIntake,
    MedKit,
    MedSchedule,
    MedStock,
)
from app.services.med.graph import _reload_med_graph, get_kit, get_med, get_stock
from app.services.med.regimen import parse_regimen_text
from app.services.med.schedule_stock_kit import (
    _resolve_kit_location,
    create_schedule,
)
from app.services.med.schemas import (
    KitBody,
    MedicationBody,
    ScheduleBody,
    StockBody,
)
from app.services.med.serializers import med_dict, schedule_dict, stock_dict
from app.services.med.substances import sync_med_components
from app.timeutils import local_today

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
    kit_id: str = "",
    stock_quantity: str = "",
    components: str | list | None = None,
    allow_ul_override: bool = False,
    auto_schedule: bool = False,
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
        allow_ul_override=allow_ul_override,
    )
    db.add(m)
    await db.flush()
    if components:
        await sync_med_components(db, m, components)
    elif (active_ingredient or "").strip():
        await sync_med_components(
            db, m, [{"substance": active_ingredient.strip(), "inn": None, "amount": None, "unit": None}]
        )
    if auto_schedule and instructions:
        await maybe_schedule_from_instructions(db, user_id, m, instructions)
    if kit_id and kit_id not in ("", "__none__"):
        kit = await get_kit(db, user_id, uuid.UUID(kit_id))
        try:
            qty = float(stock_quantity or 0)
        except ValueError:
            qty = 0.0
        db.add(
            MedStock(
                user_id=user_id,
                medication_id=m.id,
                kit_id=kit.id,
                quantity=qty,
                unit=(unit or "").strip()[:20] or None,
            )
        )
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
    components: str | list | None = None,
    allow_ul_override: bool = False,
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
    m.allow_ul_override = allow_ul_override
    m.is_active = is_active.strip().lower() in {"1", "on", "true", "yes"}
    db.add(m)
    await db.flush()
    if components:
        await sync_med_components(db, m, components)
    await maybe_schedule_from_instructions(db, user_id, m, instructions)
    return m


async def delete_medication(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> None:
    m = await get_med(db, user_id, medication_id)
    await db.delete(m)
    await db.flush()


async def maybe_schedule_from_instructions(
    db: AsyncSession,
    user_id: uuid.UUID,
    m: Medication,
    instructions: str,
) -> bool:
    """Разбор «как принимать» → автоматическое создание расписания (ADR-191)."""
    text = (instructions or "").strip()
    if not text:
        return False
    try:
        p = parse_regimen_text(text)
    except ValueError:
        return False
    from app.models.medication import FREQUENCY_TYPES

    freq = p.get("frequency_type")
    if not freq or freq not in FREQUENCY_TYPES:
        return False
    existing = (
        await db.execute(select(MedSchedule).where(MedSchedule.medication_id == m.id, MedSchedule.user_id == user_id))
    ).scalars().all()
    if existing:
        return False
    await create_schedule(
        db,
        user_id=user_id,
        medication_id=m.id,
        dose_quantity=str(p.get("dose_quantity") or 1),
        dose_unit=p.get("dose_unit") or m.unit or "",
        frequency_type=freq,
        times_per_day=str(p.get("times_per_day") or 1),
        times_of_day=p.get("times_of_day") or "",
        interval_hours=str(p.get("interval_hours") or ""),
        days_of_week=p.get("days_of_week") or "",
        start_date=p.get("start_date") or "",
        end_date="",
        instructions=text,
        food_relation=p.get("food_relation") or "",
        duration_days=str(p.get("duration_days") or ""),
        meal_offset_min="",
        course_id="",
    )
    m._auto_schedule_created = True  # type: ignore[attr-defined]
    return True


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
# Inventory → Medication migration
# ─────────────────────────────────────────────────────────────────────────────

_MEDICAL_INVENTORY_CATEGORIES = {"hygiene_supply", "consumable", "recovery_item", "other"}
_MEDICAL_KEYWORDS = (
    "мазь", "крем", "таблетк", "лекарств", "витамин", "бинт", "пластыр",
    "йод", "зеленк", "спрей", "капл", "гель", "раствор", "аптечк",
    "ointment", "cream", "tablet", "pill", "medicine", "medication",
    "vitamin", "bandage", "plaster", "iodine", "spray", "drops", "gel",
)


async def migrate_inventory(db: AsyncSession, user_id: uuid.UUID) -> tuple[int, int]:
    """Migrate medical inventory items to Medication records."""
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
    from app.services.med.units import kit_location_label

    kits = (await db.execute(select(MedKit).where(MedKit.user_id == user_id).order_by(MedKit.name))).scalars().all()
    return [
        {
            "id": str(k.id),
            "name": k.name,
            "location": kit_location_label(k),
            "location_id": str(k.location_id) if k.location_id else None,
            "notes": k.notes,
        }
        for k in kits
    ]


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
        allow_ul_override=body.allow_ul_override,
        is_active=body.is_active,
    )
    db.add(m)
    await db.flush()
    if body.components:
        await sync_med_components(db, m, [c.row() for c in body.components])
    elif (body.active_ingredient or "").strip():
        await sync_med_components(
            db, m, [{"substance": body.active_ingredient.strip(), "inn": None, "amount": None, "unit": None}]
        )
    return await _reload_med_graph(db, m)


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
    m.allow_ul_override = body.allow_ul_override
    m.is_active = body.is_active
    await db.flush()
    if body.components:
        await sync_med_components(db, m, [c.row() for c in body.components])
    return await _reload_med_graph(db, m)


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


async def json_create_schedule(
    db: AsyncSession, user_id: uuid.UUID, body: ScheduleBody, course_id: uuid.UUID | None = None
) -> MedSchedule:
    m = await get_med(db, user_id, body.medication_id)
    freq = body.frequency_type if body.frequency_type in MED_KINDS else "daily"
    from app.models.medication import FREQUENCY_TYPES
    freq = body.frequency_type if body.frequency_type in FREQUENCY_TYPES else "daily"
    ed = body.end_date
    if not ed and body.duration_days and body.start_date:
        ed = body.start_date + timedelta(days=body.duration_days - 1)
    from app.models.medication import FOOD_RELATIONS
    relation = body.food_relation if body.food_relation in FOOD_RELATIONS else None
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
        end_date=ed,
        food_relation=relation,
        duration_days=body.duration_days,
        meal_timing=body.meal_timing,
        meal_offset_min=body.meal_offset_min,
        course_id=course_id,
        instructions=(body.instructions or "").strip() or None,
        is_active=body.is_active,
    )
    s.medication = m
    db.add(s)
    await db.flush()
    return s


async def json_create_kit(db: AsyncSession, user_id: uuid.UUID, body: KitBody) -> MedKit:
    name = _validate_name(body.name)
    loc_id = await _resolve_kit_location(db, user_id, body.location_id)
    k = MedKit(
        user_id=user_id,
        name=name,
        location=(body.location or "").strip()[:200] or None,
        location_id=loc_id,
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
    from app.services.med.graph import get_schedule

    s = await get_schedule(db, user_id, schedule_id)
    await db.delete(s)
    await db.flush()


async def json_delete_kit(db: AsyncSession, user_id: uuid.UUID, kit_id: uuid.UUID) -> None:
    k = await get_kit(db, user_id, kit_id)
    await db.delete(k)
    await db.flush()


async def json_delete_medication(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> None:
    await delete_medication(db, user_id, medication_id)
