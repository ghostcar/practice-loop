"""Medication Organizer API — Thin HTTP routes.

All business logic lives in app.services.med_service (ADR-162).
This file contains only HTTP parsing, response building, and dependency injection.
"""

from __future__ import annotations

import contextlib
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.medication import MedCourse
from app.models.user import User
from app.services import med_service as svc
from app.services.errors import NotFoundError
from app.templates_setup import templates

router = APIRouter(tags=["medication"])
json_router = APIRouter(prefix="/api/v2/medications", tags=["medication"])


# ─────────────────────────────────────────────────────────────────────────────
# HTML Pages
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/medications", response_class=HTMLResponse)
async def medications_page(
    request: Request,
    q: str = "",
    migrated: int = 0,
    skipped: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_med_page_context(db, user, migrated=migrated, skipped=skipped, t=t, q=q)
    return templates.TemplateResponse(
        request=request,
        name="medication.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, **ctx},
    )


# ─────────────────────────────────────────────────────────────────────────────
# HTML Form Handlers
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/medications")
async def create_medication(
    request: Request,
    name: str = Form(...),
    kind: str = Form(default="medication"),
    active_ingredient: str = Form(default=""),
    form: str = Form(default=""),
    strength: str = Form(default=""),
    manufacturer: str = Form(default=""),
    storage_conditions: str = Form(default=""),
    prescription_required: bool = Form(default=False),
    unit: str = Form(default=""),
    instructions: str = Form(default=""),
    notes: str = Form(default=""),
    kit_id: str = Form(default=""),
    stock_quantity: str = Form(default=""),
    components: str = Form(default=""),
    allow_ul_override: bool = Form(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.create_medication(
            db,
            user_id=user.id,
            name=name,
            kind=kind,
            active_ingredient=active_ingredient,
            form=form,
            strength=strength,
            manufacturer=manufacturer,
            storage_conditions=storage_conditions,
            prescription_required=prescription_required,
            unit=unit,
            instructions=instructions,
            notes=notes,
            kit_id=kit_id,
            stock_quantity=stock_quantity,
            components=components,
            allow_ul_override=allow_ul_override,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
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
    manufacturer: str = Form(default=""),
    storage_conditions: str = Form(default=""),
    prescription_required: bool = Form(default=False),
    unit: str = Form(default=""),
    instructions: str = Form(default=""),
    notes: str = Form(default=""),
    is_active: str = Form(default=""),
    components: str = Form(default=""),
    allow_ul_override: bool = Form(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.update_medication(
            db,
            user_id=user.id,
            medication_id=medication_id,
            name=name,
            kind=kind,
            active_ingredient=active_ingredient,
            form=form,
            strength=strength,
            manufacturer=manufacturer,
            storage_conditions=storage_conditions,
            prescription_required=prescription_required,
            unit=unit,
            instructions=instructions,
            notes=notes,
            is_active=is_active,
            components=components,
            allow_ul_override=allow_ul_override,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/medications/{medication_id}/find-analogs")
async def find_medication_analogs(
    request: Request,
    medication_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        analogs_data = await svc.find_analogs(db, user.id, medication_id)
    except (NotFoundError, ValueError) as e:
        raise HTTPException(400, str(e)) from None
    return {"status": "ok", "analogues": analogs_data}


@router.post("/medications/autofill-info")
async def autofill_medication_info(
    request: Request,
    name: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    t = get_translations(locale)
    info = await svc.autofill_info(db, user.id, name, locale=locale)
    if info is None:
        return {"status": "not_found", "message": t["med_autofill_not_found"]}
    return {"status": "ok", "data": info}


@router.post("/medications/parse-regimen")
async def parse_regimen_text(
    request: Request,
    text: str = Form(default=""),
    user: User = Depends(get_current_user),
):
    """ADR-189 (фаза D): свободный текст режима → параметры для предзаполнения формы.

    Парсер ничего не сохраняет: результат подтверждает пользователь перед submit.
    """
    locale = detect_locale(request, user.locale)
    t = get_translations(locale)
    try:
        params = svc.parse_regimen_text(text)
    except ValueError:
        return {"status": "error", "message": t["med_parse_error"]}
    return {"status": "ok", "params": params}


@router.post("/medications/{medication_id}/delete")
async def delete_medication(
    request: Request,
    medication_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_medication(db, user.id, medication_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
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
    try:
        await svc.create_stock(
            db,
            user_id=user.id,
            medication_id=medication_id,
            quantity=quantity,
            unit=unit,
            kit_id=kit_id,
            lot_number=lot_number,
            expiry_date=expiry_date,
            low_stock_threshold=low_stock_threshold,
            notes=notes,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
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
    food_relation: str = Form(default=""),
    duration_days: str = Form(default=""),
    meal_offset_min: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.create_schedule(
            db,
            user_id=user.id,
            medication_id=medication_id,
            dose_quantity=dose_quantity,
            dose_unit=dose_unit,
            frequency_type=frequency_type,
            times_per_day=times_per_day,
            times_of_day=times_of_day,
            interval_hours=interval_hours,
            days_of_week=days_of_week,
            start_date=start_date,
            end_date=end_date,
            instructions=instructions,
            food_relation=food_relation,
            duration_days=duration_days,
            meal_offset_min=meal_offset_min,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-stocks/{stock_id}/delete")
async def delete_stock(
    request: Request,
    stock_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_stock(db, user.id, stock_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-schedules/{schedule_id}/delete")
async def delete_schedule(
    request: Request,
    schedule_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_schedule(db, user.id, schedule_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-intakes/batch")
async def record_intake_batch(
    request: Request,
    schedule_ids: str = Form(default=""),
    slot_time: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Одна сводная задача на приём (ADR-189): отметить принятым весь временной слот."""
    ids = [uuid.UUID(sid) for sid in schedule_ids.split(",") if sid.strip()]
    with contextlib.suppress(NotFoundError, ValueError):
        await svc.record_batch_intake(db, user_id=user.id, schedule_ids=ids, slot_time=slot_time)
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-courses")
async def create_course_form(
    request: Request,
    name: str = Form(...),
    notes: str = Form(default=""),
    start_date: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.create_course(db, user_id=user.id, name=name, notes=notes, start_date=start_date)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-courses/{course_id}/items")
async def add_course_item_form(
    request: Request,
    course_id: uuid.UUID,
    medication_id: uuid.UUID = Form(...),
    dose_quantity: str = Form(default="1"),
    dose_unit: str = Form(default=""),
    frequency_type: str = Form(default="daily"),
    times_per_day: str = Form(default=""),
    times_of_day: str = Form(default=""),
    interval_hours: str = Form(default=""),
    days_of_week: str = Form(default=""),
    food_relation: str = Form(default=""),
    duration_days: str = Form(default=""),
    meal_offset_min: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.add_course_item(
            db,
            user_id=user.id,
            course_id=course_id,
            medication_id=medication_id,
            dose_quantity=dose_quantity,
            dose_unit=dose_unit,
            frequency_type=frequency_type,
            times_per_day=times_per_day,
            times_of_day=times_of_day,
            interval_hours=interval_hours,
            days_of_week=days_of_week,
            food_relation=food_relation,
            duration_days=duration_days,
            meal_offset_min=meal_offset_min,
        )
    except (NotFoundError, ValueError) as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-courses/{course_id}/status")
async def set_course_status_form(
    request: Request,
    course_id: uuid.UUID,
    status: str = Form(default="planned"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.set_course_status(db, user.id, course_id, status)
    except (NotFoundError, ValueError) as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-courses/{course_id}/delete")
async def delete_course_form(
    request: Request,
    course_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_course(db, user.id, course_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
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
    sched_id = None
    if schedule_id and schedule_id != "__none__":
        sched_id = uuid.UUID(schedule_id)
    qty = None
    if quantity_taken.strip():
        try:
            qty = float(quantity_taken)
        except ValueError:
            qty = None
    try:
        await svc.record_intake(
            db,
            user_id=user.id,
            medication_id=medication_id,
            schedule_id=sched_id,
            status=status,
            taken_at=taken_at,
            quantity_taken=qty,
            notes=notes,
            gamification=True,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-kits")
async def create_kit(
    request: Request,
    name: str = Form(...),
    location: str = Form(default=""),
    location_id: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    loc_uuid = None
    if location_id.strip():
        try:
            loc_uuid = uuid.UUID(location_id.strip())
        except ValueError:
            raise HTTPException(400, "Invalid location") from None
    try:
        await svc.create_kit(db, user_id=user.id, name=name, location=location, notes=notes, location_id=loc_uuid)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-kits/{kit_id}/delete")
async def delete_kit(
    request: Request,
    kit_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_kit(db, user.id, kit_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.get("/medications/export")
async def export_medications(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    content, filename = await svc.get_csv_export(db, user.id)
    return Response(
        content=content,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/medications/migrate-inventory")
async def migrate_inventory_to_medications(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    created, skipped = await svc.migrate_inventory(db, user.id)
    return RedirectResponse(
        url=f"/medications?migrated={created}&skipped={skipped}",
        status_code=303,
    )


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────


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


@json_router.post("/regimen/parse")
async def json_parse_regimen(
    body: svc.RegimenParseBody,
    user: User = Depends(get_current_user),
):
    """ADR-189 (фаза D, mobile parity): текст режима → структурированные параметры."""
    try:
        return svc.parse_regimen_text(body.text)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@json_router.post("/autofill")
async def json_autofill(
    body: svc.AutofillBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """ADR-190 (фаза E, mobile parity): наименование → поля формы + components[]; 404 = не найдено."""
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
            db,
            user_id=user.id,
            medication_id=medication_id,
            schedule_id=body.schedule_id,
            status=body.status,
            taken_at=body.taken_at,
            quantity_taken=body.quantity_taken,
            notes=body.notes,
            gamification=True,
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


# Re-export service helpers that other modules may import from medication.py
from app.services.med_service import schedule_summary as _schedule_summary  # noqa: E402, F401
