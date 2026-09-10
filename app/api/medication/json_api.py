"""Medication Organizer — JSON API routes (mobile / bearer)."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.models.medication import MedCourse, MedStock
from app.models.user import User
from app.services import med_service as svc
from app.services.errors import NotFoundError
from app.timeutils import local_today

logger = logging.getLogger(__name__)

json_router = APIRouter(prefix="/api/v2/medications", tags=["medication"])


@json_router.get("")
async def json_list(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_list_medications(db, user.id)


@json_router.get("/today")
async def json_today(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.schedule_summary(db, user.id)


@json_router.get("/stocks")
async def json_list_stocks(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_list_stocks(db, user.id)


@json_router.get("/schedules")
async def json_list_schedules(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_list_schedules(db, user.id)


@json_router.get("/kits")
async def json_list_kits(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_list_kits(db, user.id)


@json_router.get("/kits/{kit_id}")
async def json_get_kit(
    kit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        k = await svc.get_kit(db, user.id, kit_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    stmt = (
        select(MedStock)
        .where(MedStock.kit_id == kit_id, MedStock.user_id == user.id)
    )
    stocks = (await db.execute(stmt)).scalars().all()
    today = local_today()
    items = [
        {
            "id": str(st.id),
            "medication_id": str(st.medication_id),
            "medication_name": st.medication.name if st.medication else "",
            "form": st.medication.form if st.medication else "",
            "strength": st.medication.strength if st.medication else "",
            "quantity": st.quantity,
            "unit": st.unit or (st.medication.unit if st.medication else "шт"),
            "lot_number": st.lot_number or "",
            "expiry_date": st.expiry_date.isoformat() if st.expiry_date else None,
            "is_expired": st.expiry_date is not None and st.expiry_date < today,
            "notes": st.notes or "",
        }
        for st in sorted(stocks, key=lambda x: (x.medication.name.lower() if x.medication else ""))
    ]
    return {
        "id": str(k.id),
        "name": k.name,
        "location": k.location,
        "notes": k.notes,
        "items": items,
    }


@json_router.post("", status_code=201)
async def json_create_medication(
    body: svc.MedicationBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        m = await svc.json_create_medication(db, user.id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return svc.med_dict(m)


@json_router.put("/{medication_id}")
async def json_update_medication(
    medication_id: uuid.UUID,
    body: svc.MedicationBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        m = await svc.json_update_medication(db, user.id, medication_id, body)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return svc.med_dict(m)


@json_router.post("/stocks", status_code=201)
async def json_create_stock(
    body: svc.StockBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        st = await svc.json_create_stock(db, user.id, body)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return svc.stock_dict(st)


@json_router.post("/schedules", status_code=201)
async def json_create_schedule(
    body: svc.ScheduleBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        s = await svc.json_create_schedule(db, user.id, body)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return svc.schedule_dict(s)


@json_router.post("/kits", status_code=201)
async def json_create_kit(
    body: svc.KitBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        k = await svc.json_create_kit(db, user.id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {
        "id": str(k.id),
        "name": k.name,
        "location": k.location,
        "location_id": str(k.location_id) if k.location_id else None,
        "notes": k.notes,
    }


@json_router.delete("/stocks/{stock_id}", status_code=204)
async def json_delete_stock(
    stock_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.json_delete_stock(db, user.id, stock_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return None


@json_router.delete("/schedules/{schedule_id}", status_code=204)
async def json_delete_schedule(
    schedule_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.json_delete_schedule(db, user.id, schedule_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return None


@json_router.delete("/kits/{kit_id}", status_code=204)
async def json_delete_kit(
    kit_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.json_delete_kit(db, user.id, kit_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return None


@json_router.delete("/{medication_id}", status_code=204)
async def json_delete_medication(
    medication_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.json_delete_medication(db, user.id, medication_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except Exception as e:  # noqa: BLE001
        logger.warning("JSON medication delete failed %s: %s", medication_id, e)
        raise HTTPException(500, str(e)[:400]) from None
    return None


@json_router.get("/courses")
async def json_list_courses(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    courses = (
        (await db.execute(select(MedCourse).where(MedCourse.user_id == user.id).order_by(MedCourse.created_at.desc())))
        .scalars()
        .all()
    )
    return [await svc.course_summary(db, c) for c in courses]


@json_router.post("/courses", status_code=201)
async def json_create_course(
    body: svc.CourseBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        c = await svc.json_create_course(db, user.id, body)
    except (NotFoundError, ValueError) as e:
        raise HTTPException(400, str(e)) from None
    return await svc.course_summary(db, c)


@json_router.get("/courses/{course_id}/plan")
async def json_course_plan(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        c = await svc.get_course(db, user.id, course_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return await svc.course_summary(db, c)


@json_router.delete("/courses/{course_id}", status_code=204)
async def json_delete_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.delete_course(db, user.id, course_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return None


class CombineSlotsBody(BaseModel):
    schedule_ids: list[uuid.UUID]
    times_of_day: str
    food_relation: str | None = None


@json_router.post("/courses/{course_id}/combine-slots")
async def json_combine_course_slots(
    course_id: uuid.UUID,
    body: CombineSlotsBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.batch_combine_course_slots(
            db, user.id, course_id, body.schedule_ids,
            times_of_day=body.times_of_day, food_relation=body.food_relation or "",
        )
        c = await svc.get_course(db, user.id, course_id)
        return await svc.course_summary(db, c)
    except (NotFoundError, ValueError) as e:
        raise HTTPException(400, str(e)) from None


class StockUpdateBody(BaseModel):
    quantity: float
    unit: str | None = None
    lot_number: str | None = None
    expiry_date: str | None = None
    notes: str | None = None
    kit_id: str | None = None


@json_router.put("/stocks/{stock_id}")
async def json_update_stock(
    stock_id: uuid.UUID,
    body: StockUpdateBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        st = await svc.update_stock(
            db, user.id, stock_id,
            quantity=body.quantity,
            unit=body.unit or "",
            lot_number=body.lot_number or "",
            expiry_date=body.expiry_date or "",
            notes=body.notes or "",
            kit_id=body.kit_id or "",
        )
        return svc.stock_dict(st)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@json_router.post("/regimen/parse")
async def json_parse_regimen(
    body: svc.RegimenParseBody,
    user: User = Depends(get_current_user),
):
    try:
        return svc.parse_regimen_text(body.text)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


class AnalogsQueryBody(BaseModel):
    target_substance: str | None = None
    source_type: str = "llm"
    target_strength: str | None = None


@json_router.post("/{medication_id}/analogs")
async def json_find_analogs(
    medication_id: uuid.UUID,
    body: AnalogsQueryBody | None = None,
    target_substance: str | None = Query(default=None),
    source_type: str = Query(default="llm"),
    target_strength: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """JSON parity: поиск аналогов (онлайн/LLM/комбинированный) с выбором веществ.
    422 no_composition/no_llm, 502 llm_error.
    """
    ts = body.target_substance if (body and body.target_substance is not None) else target_substance
    st = (body.source_type if (body and body.source_type is not None) else source_type) or "llm"
    t_str = body.target_strength if (body and body.target_strength is not None) else target_strength
    try:
        data = await svc.find_analogs(
            db,
            user.id,
            medication_id,
            locale="ru",
            target_substance=ts,
            source_type=st,
            target_strength=t_str,
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        code = str(e)
        status = 502 if code == "llm_error" else 422
        raise HTTPException(status, code) from None
    return {"status": "ok", "analogues": data}


@json_router.get("/{medication_id}/equivalents")
async def json_equivalents(
    medication_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await svc.get_equivalents(db, user.id, medication_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None


@json_router.post("/autofill")
async def json_autofill(
    body: svc.AutofillBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    info = await svc.autofill_info(db, user.id, body.name, locale=user.locale or "en")
    if info is None:
        raise HTTPException(404, "Pharma entry not found")
    return info


@json_router.post("/{medication_id}/intake", status_code=201)
async def json_record_intake(
    medication_id: uuid.UUID,
    body: svc.IntakeBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        it = await svc.record_intake(
            db, user_id=user.id, medication_id=medication_id,
            schedule_id=body.schedule_id, status=body.status,
            taken_at=body.taken_at, quantity_taken=body.quantity_taken,
            notes=body.notes, substituted_for_id=body.substituted_for_id,
            ul_confirmed=body.ul_confirmed, gamification=True,
            kit_id=body.kit_id,
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return {
        "id": str(it.id),
        "medication_id": str(it.medication_id),
        "schedule_id": str(it.schedule_id) if it.schedule_id else None,
        "status": it.status,
        "taken_at": it.taken_at.isoformat() if it.taken_at else None,
        "quantity_taken": it.quantity_taken,
    }


@json_router.get("/export")
async def json_export(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.get_json_export(db, user.id)
