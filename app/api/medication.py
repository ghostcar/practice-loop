"""Medication Organizer API (M3 Personal Suite, Шаг 11b).

Health-модуль — **relief-only** (PD-013): никакой игровой интеграции, никаких
штрафов. Все записи Private Record (DATA_LIFECYCLE.md).

Страницы:
- GET  /medications               — каталог + «сегодня» + остатки/сроки + аптечки
- POST /medications               — создать препарат
- POST /medications/{id}/update   — обновить
- POST /medications/{id}/delete   — удалить (каскад stocks/schedules/intakes)
- POST /medications/{id}/stock    — добавить партию (остаток/срок)
- POST /medications/{id}/schedule — добавить расписание приёма
- POST /med-stocks/{id}/delete    — удалить партию
- POST /med-schedules/{id}/delete — удалить расписание
- POST /med-intakes               — записать факт приёма (taken/missed/skipped/...)
- POST /med-kits / med-kits/{id}/delete — аптечки
- GET  /medications/export        — CSV для врача (явный Shared Artifact)

JSON API (мобильный/bearer):
- GET  /api/v2/medications        — список + остатки/расписания
- GET  /api/v2/medications/today  — «сегодня» + истекающие + низкий остаток
- POST /api/v2/medications/{id}/intake — записать приём
- GET  /api/v2/medications/export — JSON-экспорт
"""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
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
from app.models.user import User
from app.templates_setup import templates
from app.timeutils import local_date, local_now, local_today

router = APIRouter(tags=["medication"])

EXPIRING_SOON_DAYS = 30

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _med_dict(m: Medication) -> dict:
    return {
        "id": str(m.id),
        "name": m.name,
        "kind": m.kind,
        "active_ingredient": m.active_ingredient,
        "form": m.form,
        "strength": m.strength,
        "unit": m.unit,
        "instructions": m.instructions,
        "notes": m.notes,
        "is_active": m.is_active,
    }


def _stock_dict(st: MedStock) -> dict:
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


def _schedule_dict(s: MedSchedule) -> dict:
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


def _doses_today(s: MedSchedule, today: date) -> int:
    """Ожидаемое число приёмов сегодня по расписанию (0 = не в этот день)."""
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


async def _schedule_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """«Сегодня»: расписания с невыполненными приёмами + истекающие/низкий остаток."""
    today = local_today()
    schedules = (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user_id))).scalars().all()
    intakes = (await db.execute(select(MedIntake).where(MedIntake.user_id == user_id))).scalars().all()

    # количество принятых сегодня по каждому расписанию (по локальному дню устройства)
    taken_today: dict[str, int] = {}
    for it in intakes:
        if it.status != "taken" or it.schedule_id is None:
            continue
        taken_dt = it.taken_at or it.created_at
        if taken_dt is not None and local_date(taken_dt) == today:
            taken_today[str(it.schedule_id)] = taken_today.get(str(it.schedule_id), 0) + 1

    due = []
    for s in schedules:
        expected = _doses_today(s, today)
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
# Page: list + dashboard
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/medications", response_class=HTMLResponse)
async def medications_page(
    request: Request,
    migrated: int = 0,
    skipped: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    meds = (
        (await db.execute(select(Medication).where(Medication.user_id == user.id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    kits = (await db.execute(select(MedKit).where(MedKit.user_id == user.id).order_by(MedKit.name))).scalars().all()
    stocks = (await db.execute(select(MedStock).where(MedStock.user_id == user.id))).scalars().all()
    schedules = (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user.id))).scalars().all()
    summary = await _schedule_summary(db, user.id)

    # index by medication id
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
        d = _med_dict(m)
        d["stocks"] = stocks_by_med.get(str(m.id), [])
        d["schedules"] = schedules_by_med.get(str(m.id), [])
        meds_data.append(d)

    # Count migrated inventory items for the migration banner/button.
    from sqlalchemy import func

    from app.models.life import InventoryItem

    migrated_count_result = await db.execute(
        select(func.count(InventoryItem.id)).where(
            InventoryItem.user_id == user.id, InventoryItem.migrated_to_medication.is_(True)
        )
    )
    migrated_count = migrated_count_result.scalar() or 0

    return templates.TemplateResponse(
        request=request,
        name="medication.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "meds": meds_data,
            "kits": [{"id": str(k.id), "name": k.name, "location": k.location} for k in kits],
            "summary": summary,
            "kinds": list(MED_KINDS),
            "intake_statuses": list(INTAKE_STATUSES),
            "frequency_types": list(FREQUENCY_TYPES),
            "migrated": migrated,
            "skipped": skipped,
            "migrated_count": migrated_count,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# CRUD (form posts) — commit via get_db (no explicit db.commit in router)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/medications")
async def create_medication(
    request: Request,
    name: str = Form(...),
    kind: str = Form(default="medication"),
    active_ingredient: str = Form(default=""),
    form: str = Form(default=""),
    strength: str = Form(default=""),
    unit: str = Form(default=""),
    instructions: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")
    if kind not in MED_KINDS:
        kind = "medication"
    m = Medication(
        user_id=user.id,
        name=name,
        kind=kind,
        active_ingredient=(active_ingredient or "").strip()[:200] or None,
        form=(form or "").strip()[:50] or None,
        strength=(strength or "").strip()[:50] or None,
        unit=(unit or "").strip()[:20] or None,
        instructions=(instructions or "").strip() or None,
        notes=(notes or "").strip() or None,
    )
    db.add(m)
    await db.flush()
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/medications/{medication_id}/update")
async def update_medication(
    request: Request,
    medication_id: uuid.UUID,
    name: str = Form(...),
    kind: str = Form(default="medication"),
    active_ingredient: str = Form(default=""),
    form: str = Form(default=""),
    strength: str = Form(default=""),
    unit: str = Form(default=""),
    instructions: str = Form(default=""),
    notes: str = Form(default=""),
    is_active: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    m = await _get_med(db, user.id, medication_id)
    m.name = name.strip()[:200] or m.name
    if kind in MED_KINDS:
        m.kind = kind
    m.active_ingredient = (active_ingredient or "").strip()[:200] or None
    m.form = (form or "").strip()[:50] or None
    m.strength = (strength or "").strip()[:50] or None
    m.unit = (unit or "").strip()[:20] or None
    m.instructions = (instructions or "").strip() or None
    m.notes = (notes or "").strip() or None
    m.is_active = is_active.strip().lower() in {"1", "on", "true", "yes"}
    db.add(m)
    await db.flush()
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/medications/{medication_id}/delete")
async def delete_medication(
    request: Request,
    medication_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    m = await _get_med(db, user.id, medication_id)
    await db.delete(m)
    await db.flush()
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/medications/{medication_id}/stock")
async def add_stock(
    request: Request,
    medication_id: uuid.UUID,
    quantity: str = Form(default="0"),
    unit: str = Form(default=""),
    kit_id: str = Form(default=""),
    lot_number: str = Form(default=""),
    expiry_date: str = Form(default=""),
    low_stock_threshold: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    m = await _get_med(db, user.id, medication_id)
    try:
        qty = float(quantity or 0)
    except ValueError:
        qty = 0.0
    kit = None
    if kit_id and kit_id not in ("", "__none__"):
        kit = await _get_kit(db, user.id, uuid.UUID(kit_id))
    expiry = None
    if expiry_date.strip():
        try:
            expiry = date.fromisoformat(expiry_date.strip())
        except ValueError:
            raise HTTPException(400, "Invalid expiry_date format (ISO 8601)") from None
    threshold = None
    if low_stock_threshold.strip():
        try:
            threshold = float(low_stock_threshold)
        except ValueError:
            threshold = None
    st = MedStock(
        user_id=user.id,
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
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/medications/{medication_id}/schedule")
async def add_schedule(
    request: Request,
    medication_id: uuid.UUID,
    dose_quantity: str = Form(default="1"),
    dose_unit: str = Form(default=""),
    frequency_type: str = Form(default="daily"),
    times_per_day: str = Form(default=""),
    times_of_day: str = Form(default=""),
    interval_hours: str = Form(default=""),
    days_of_week: str = Form(default=""),
    start_date: str = Form(default=""),
    end_date: str = Form(default=""),
    instructions: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    m = await _get_med(db, user.id, medication_id)
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
        user_id=user.id,
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
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-stocks/{stock_id}/delete")
async def delete_stock(
    request: Request,
    stock_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    st = (
        await db.execute(select(MedStock).where(MedStock.id == stock_id, MedStock.user_id == user.id))
    ).scalar_one_or_none()
    if st is None:
        raise HTTPException(404, "Stock not found")
    await db.delete(st)
    await db.flush()
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-schedules/{schedule_id}/delete")
async def delete_schedule(
    request: Request,
    schedule_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    s = (
        await db.execute(select(MedSchedule).where(MedSchedule.id == schedule_id, MedSchedule.user_id == user.id))
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "Schedule not found")
    await db.delete(s)
    await db.flush()
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-intakes")
async def record_intake_form(
    request: Request,
    medication_id: uuid.UUID = Form(...),
    schedule_id: str = Form(default=""),
    status: str = Form(default="taken"),
    taken_at: str = Form(default=""),
    quantity_taken: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    m = await _get_med(db, user.id, medication_id)
    sched = None
    if schedule_id and schedule_id != "__none__":
        sched = (
            await db.execute(
                select(MedSchedule).where(MedSchedule.id == uuid.UUID(schedule_id), MedSchedule.user_id == user.id)
            )
        ).scalar_one_or_none()
    if status not in INTAKE_STATUSES:
        status = "unknown"
    taken_dt = None
    if taken_at.strip():
        try:
            taken_dt = datetime.fromisoformat(taken_at.strip())
        except ValueError:
            taken_dt = None
    if status == "taken" and taken_dt is None:
        taken_dt = local_now()
    qty = None
    if quantity_taken.strip():
        try:
            qty = float(quantity_taken)
        except ValueError:
            qty = None
    it = MedIntake(
        user_id=user.id,
        medication_id=m.id,
        schedule_id=sched.id if sched else None,
        scheduled_at=local_now(),
        taken_at=taken_dt,
        status=status,
        quantity_taken=qty,
        notes=(notes or "").strip() or None,
    )
    db.add(it)
    await db.flush()
    # ADR-085: on-time intake may earn XP/achievements (positive-only, never penalizes).
    if status == "taken":
        from app.gamification.medication import on_medication_taken

        await on_medication_taken(db, user.id, m.name, on_time=True)
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-kits")
async def create_kit(
    request: Request,
    name: str = Form(...),
    location: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    name = name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")
    k = MedKit(
        user_id=user.id,
        name=name,
        location=(location or "").strip()[:200] or None,
        notes=(notes or "").strip() or None,
    )
    db.add(k)
    await db.flush()
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-kits/{kit_id}/delete")
async def delete_kit(
    request: Request,
    kit_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    k = (await db.execute(select(MedKit).where(MedKit.id == kit_id, MedKit.user_id == user.id))).scalar_one_or_none()
    if k is None:
        raise HTTPException(404, "Kit not found")
    await db.delete(k)
    await db.flush()
    return RedirectResponse(url="/medications", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# Export (CSV for doctor — explicit Shared Artifact)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/medications/export")
async def export_medications(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    meds = (
        (await db.execute(select(Medication).where(Medication.user_id == user.id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    intakes = (
        (await db.execute(select(MedIntake).where(MedIntake.user_id == user.id).order_by(MedIntake.created_at.desc())))
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
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ─────────────────────────────────────────────────────────────────────────────
# One-time inventory→medicine migration (Шаг 12)
# ─────────────────────────────────────────────────────────────────────────────

# Inventory category slugs that logically belong to the medicine domain.
_MEDICAL_INVENTORY_CATEGORIES = {"hygiene_supply", "consumable", "recovery_item", "other"}
# Keyword hints in item name/description that suggest a medical item regardless of category.
_MEDICAL_KEYWORDS = (
    "мазь",
    "крем",
    "таблетк",
    "лекарств",
    "витамин",
    "бинт",
    "пластыр",
    "йод",
    "зеленк",
    "спрей",
    "капл",
    "гель",
    "раствор",
    "аптечк",
    "ointment",
    "cream",
    "tablet",
    "pill",
    "medicine",
    "medication",
    "vitamin",
    "bandage",
    "plaster",
    "iodine",
    "spray",
    "drops",
    "gel",
)


@router.post("/medications/migrate-inventory")
async def migrate_inventory_to_medications(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """One-time migration: create Medication records from medical inventory items.

    Idempotent: items already migrated (``migrated_to_medication = True``) or
    whose name already exists as a medication are skipped. Migrated inventory
    items are marked (not deleted) so the user can review and clean up.
    """

    from app.models.life import InventoryItem

    items = (
        (
            await db.execute(
                select(InventoryItem)
                .where(InventoryItem.user_id == user.id, InventoryItem.migrated_to_medication.is_(False))
                .order_by(InventoryItem.name)
            )
        )
        .scalars()
        .all()
    )

    existing_names = set(
        (await db.execute(select(Medication.name).where(Medication.user_id == user.id))).scalars().all()
    )

    created = 0
    skipped_duplicate = 0
    migrated_items: list[dict] = []
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
            user_id=user.id,
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
        migrated_items.append({"name": name, "inventory_id": str(item.id)})

    if created:
        await db.flush()

    return RedirectResponse(
        url=f"/medications?migrated={created}&skipped={skipped_duplicate}",
        status_code=303,
    )


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────

json_router = APIRouter(prefix="/api/v2/medications", tags=["medication"])


async def _get_med(db: AsyncSession, user_id: uuid.UUID, medication_id: uuid.UUID) -> Medication:
    m = (
        await db.execute(select(Medication).where(Medication.id == medication_id, Medication.user_id == user_id))
    ).scalar_one_or_none()
    if m is None:
        raise HTTPException(404, "Medication not found")
    return m


async def _get_kit(db: AsyncSession, user_id: uuid.UUID, kit_id: uuid.UUID) -> MedKit:
    k = (await db.execute(select(MedKit).where(MedKit.id == kit_id, MedKit.user_id == user_id))).scalar_one_or_none()
    if k is None:
        raise HTTPException(404, "Kit not found")
    return k


@json_router.get("")
async def json_list(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    meds = (
        (await db.execute(select(Medication).where(Medication.user_id == user.id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    stocks = (await db.execute(select(MedStock).where(MedStock.user_id == user.id))).scalars().all()
    schedules = (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user.id))).scalars().all()
    out = []
    for m in meds:
        d = _med_dict(m)
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


@json_router.get("/today")
async def json_today(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await _schedule_summary(db, user.id)


@json_router.get("/stocks")
async def json_list_stocks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Список партий/остатков — для мобильного клиента (owner-scoped)."""
    stocks = (
        (await db.execute(select(MedStock).where(MedStock.user_id == user.id).order_by(MedStock.created_at.desc())))
        .scalars()
        .all()
    )
    return [_stock_dict(st) for st in stocks]


@json_router.get("/schedules")
async def json_list_schedules(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Список расписаний приёма — для мобильного клиента (owner-scoped)."""
    schedules = (
        (
            await db.execute(
                select(MedSchedule).where(MedSchedule.user_id == user.id).order_by(MedSchedule.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_schedule_dict(s) for s in schedules]


@json_router.get("/kits")
async def json_list_kits(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Список аптечек — для мобильного клиента (owner-scoped)."""
    kits = (await db.execute(select(MedKit).where(MedKit.user_id == user.id).order_by(MedKit.name))).scalars().all()
    return [{"id": str(k.id), "name": k.name, "location": k.location, "notes": k.notes} for k in kits]


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


@json_router.post("", status_code=201)
async def json_create_medication(
    body: MedicationBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Создать препарат (JSON) — для мобильного клиента."""
    name = body.name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")
    kind = body.kind if body.kind in MED_KINDS else "medication"
    m = Medication(
        user_id=user.id,
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
    return _med_dict(m)


@json_router.post("/stocks", status_code=201)
async def json_create_stock(
    body: StockBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Создать партию/остаток (JSON) — для мобильного клиента."""
    m = await _get_med(db, user.id, body.medication_id)
    kit = await _get_kit(db, user.id, body.kit_id) if body.kit_id else None
    st = MedStock(
        user_id=user.id,
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
    return _stock_dict(st)


@json_router.post("/schedules", status_code=201)
async def json_create_schedule(
    body: ScheduleBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Создать расписание приёма (JSON) — для мобильного клиента."""
    m = await _get_med(db, user.id, body.medication_id)
    freq = body.frequency_type if body.frequency_type in FREQUENCY_TYPES else "daily"
    s = MedSchedule(
        user_id=user.id,
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
    return _schedule_dict(s)


@json_router.post("/kits", status_code=201)
async def json_create_kit(
    body: KitBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Создать аптечку (JSON) — для мобильного клиента."""
    name = body.name.strip()[:200]
    if not name:
        raise HTTPException(400, "Name is required")
    k = MedKit(
        user_id=user.id,
        name=name,
        location=(body.location or "").strip()[:200] or None,
        notes=(body.notes or "").strip() or None,
    )
    db.add(k)
    await db.flush()
    return {"id": str(k.id), "name": k.name, "location": k.location, "notes": k.notes}


@json_router.delete("/stocks/{stock_id}", status_code=204)
async def json_delete_stock(
    stock_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    st = (
        await db.execute(select(MedStock).where(MedStock.id == stock_id, MedStock.user_id == user.id))
    ).scalar_one_or_none()
    if st is None:
        raise HTTPException(404, "Stock not found")
    await db.delete(st)
    await db.flush()
    return None


@json_router.delete("/schedules/{schedule_id}", status_code=204)
async def json_delete_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    s = (
        await db.execute(select(MedSchedule).where(MedSchedule.id == schedule_id, MedSchedule.user_id == user.id))
    ).scalar_one_or_none()
    if s is None:
        raise HTTPException(404, "Schedule not found")
    await db.delete(s)
    await db.flush()
    return None


@json_router.delete("/kits/{kit_id}", status_code=204)
async def json_delete_kit(
    kit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    k = (await db.execute(select(MedKit).where(MedKit.id == kit_id, MedKit.user_id == user.id))).scalar_one_or_none()
    if k is None:
        raise HTTPException(404, "Kit not found")
    await db.delete(k)
    await db.flush()
    return None


@json_router.delete("/{medication_id}", status_code=204)
async def json_delete_medication(
    medication_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    m = await _get_med(db, user.id, medication_id)
    await db.delete(m)
    await db.flush()
    return None


class IntakeBody(BaseModel):
    schedule_id: uuid.UUID | None = None
    status: str = "taken"
    taken_at: str | None = None
    quantity_taken: float | None = None
    notes: str | None = None


@json_router.post("/{medication_id}/intake", status_code=201)
async def json_record_intake(
    medication_id: uuid.UUID,
    body: IntakeBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    m = await _get_med(db, user.id, medication_id)
    status = body.status if body.status in INTAKE_STATUSES else "unknown"
    sched = None
    if body.schedule_id:
        sched = (
            await db.execute(
                select(MedSchedule).where(MedSchedule.id == body.schedule_id, MedSchedule.user_id == user.id)
            )
        ).scalar_one_or_none()
        if sched is None:
            raise HTTPException(404, "Schedule not found")
    taken_dt = None
    if body.taken_at:
        try:
            taken_dt = datetime.fromisoformat(body.taken_at)
        except ValueError:
            raise HTTPException(400, "Invalid taken_at (ISO 8601)") from None
    if status == "taken" and taken_dt is None:
        taken_dt = local_now()
    it = MedIntake(
        user_id=user.id,
        medication_id=m.id,
        schedule_id=sched.id if sched else None,
        scheduled_at=local_now(),
        taken_at=taken_dt,
        status=status,
        quantity_taken=body.quantity_taken,
        notes=body.notes,
    )
    db.add(it)
    await db.flush()
    # ADR-085: on-time intake may earn XP/achievements (positive-only, never penalizes).
    if status == "taken":
        from app.gamification.medication import on_medication_taken

        await on_medication_taken(db, user.id, m.name, on_time=True)
    return {
        "id": str(it.id),
        "medication_id": str(m.id),
        "schedule_id": str(sched.id) if sched else None,
        "status": it.status,
        "taken_at": it.taken_at.isoformat() if it.taken_at else None,
        "quantity_taken": it.quantity_taken,
    }


@json_router.get("/export")
async def json_export(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    meds = (
        (await db.execute(select(Medication).where(Medication.user_id == user.id).order_by(Medication.name)))
        .scalars()
        .all()
    )
    intakes = (
        (await db.execute(select(MedIntake).where(MedIntake.user_id == user.id).order_by(MedIntake.created_at.desc())))
        .scalars()
        .all()
    )
    return {
        "medications": [_med_dict(m) for m in meds],
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
