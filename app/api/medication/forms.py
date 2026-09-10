"""Medication Organizer — HTML form routes (thin wrappers)."""

from __future__ import annotations

import contextlib
import logging
import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.services import med_service as svc
from app.services.errors import NotFoundError
from app.templates_setup import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["medication"])


# ── HTML Pages ──────────────────────────────────────────────────────────────


@router.get("/medications", response_class=HTMLResponse)
async def medications_page(
    request: Request,
    q: str = "",
    migrated: int = 0,
    skipped: int = 0,
    analogs_error: str = "",
    del_err: int = 0,
    del_detail: str = "",
    sched_auto: int = 0,
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
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "analogs_error": (analogs_error or "").strip()[:32],
            "del_err": int(del_err or 0),
            "del_detail": (del_detail or "").strip()[:500],
            "sched_auto": int(sched_auto or 0),
            **ctx,
        },
    )


# ── HTML Form Handlers ─────────────────────────────────────────────────────


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
    auto_schedule: bool = Form(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        m = await svc.create_medication(
            db, user_id=user.id, name=name, kind=kind,
            active_ingredient=active_ingredient, form=form, strength=strength,
            manufacturer=manufacturer, storage_conditions=storage_conditions,
            prescription_required=prescription_required, unit=unit,
            instructions=instructions, notes=notes, kit_id=kit_id,
            stock_quantity=stock_quantity, components=components,
            allow_ul_override=allow_ul_override,
            auto_schedule=auto_schedule,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    sched = 1 if getattr(m, "_auto_schedule_created", False) else 0
    qs = "?sched_auto=1" if sched else ""
    anchor = f"#med-{m.id}" if sched else ""
    return RedirectResponse(url=f"/medications{qs}{anchor}", status_code=303)


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
        m = await svc.update_medication(
            db, user_id=user.id, medication_id=medication_id, name=name, kind=kind,
            active_ingredient=active_ingredient, form=form, strength=strength,
            manufacturer=manufacturer, storage_conditions=storage_conditions,
            prescription_required=prescription_required, unit=unit,
            instructions=instructions, notes=notes, is_active=is_active,
            components=components, allow_ul_override=allow_ul_override,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    sched = 1 if getattr(m, "_auto_schedule_created", False) else 0
    qs = "?sched_auto=1" if sched else ""
    return RedirectResponse(url=f"/medications{qs}#med-{medication_id}", status_code=303)


@router.post("/medications/{medication_id}/find-analogs")
async def find_medication_analogs(
    request: Request,
    medication_id: uuid.UUID,
    target_substance: str | None = Form(default=None),
    source_type: str = Form(default="llm"),
    target_strength: str | None = Form(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    try:
        await svc.find_analogs(
            db,
            user.id,
            medication_id,
            locale=locale,
            allow_directory_fallback=True,
            target_substance=target_substance,
            source_type=source_type,
            target_strength=target_strength,
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        code = str(e)
        return RedirectResponse(url=f"/medications?analogs_error={code}#med-{medication_id}", status_code=303)
    return RedirectResponse(url=f"/medications?analogs_done=1#med-{medication_id}", status_code=303)


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


@router.get("/medications/{medication_id}/equivalents")
async def equivalents_page(
    request: Request,
    medication_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = await svc.get_equivalents(db, user.id, medication_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return data


@router.post("/medications/parse-regimen")
async def parse_regimen_text(
    request: Request,
    text: str = Form(default=""),
    user: User = Depends(get_current_user),
):
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
    except Exception as e:  # noqa: BLE001
        logger.warning("Medication delete failed %s: %s", medication_id, e)
        detail = str(e)[:400]
        return RedirectResponse(url=f"/medications?del_err=1&del_detail={quote(detail)}", status_code=303)
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
            db, user_id=user.id, medication_id=medication_id,
            quantity=quantity, unit=unit, kit_id=kit_id, lot_number=lot_number,
            expiry_date=expiry_date, low_stock_threshold=low_stock_threshold, notes=notes,
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
    preferred_kit_id: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.create_schedule(
            db, user_id=user.id, medication_id=medication_id,
            dose_quantity=dose_quantity, dose_unit=dose_unit,
            frequency_type=frequency_type, times_per_day=times_per_day,
            times_of_day=times_of_day, interval_hours=interval_hours,
            days_of_week=days_of_week, start_date=start_date, end_date=end_date,
            instructions=instructions, food_relation=food_relation,
            duration_days=duration_days, meal_offset_min=meal_offset_min,
            preferred_kit_id=preferred_kit_id,
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


@router.post("/med-stocks/{stock_id}/update")
async def update_stock_form(
    request: Request,
    stock_id: uuid.UUID,
    quantity: str = Form(default="0"),
    unit: str = Form(default=""),
    lot_number: str = Form(default=""),
    expiry_date: str = Form(default=""),
    low_stock_threshold: str = Form(default=""),
    notes: str = Form(default=""),
    kit_id: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.update_stock(
            db, user.id, stock_id,
            quantity=quantity, unit=unit, lot_number=lot_number,
            expiry_date=expiry_date, low_stock_threshold=low_stock_threshold,
            notes=notes, kit_id=kit_id,
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
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


@router.post("/med-schedules/{schedule_id}/update")
async def update_schedule_form(
    request: Request,
    schedule_id: uuid.UUID,
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
    preferred_kit_id: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.update_schedule(
            db, user.id, schedule_id,
            dose_quantity=dose_quantity, dose_unit=dose_unit,
            frequency_type=frequency_type, times_per_day=times_per_day,
            times_of_day=times_of_day, interval_hours=interval_hours,
            days_of_week=days_of_week, start_date=start_date, end_date=end_date,
            instructions=instructions, food_relation=food_relation,
            duration_days=duration_days, meal_offset_min=meal_offset_min,
            preferred_kit_id=preferred_kit_id,
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-intakes/batch")
async def record_intake_batch(
    request: Request,
    schedule_ids: str = Form(default=""),
    slot_time: str = Form(default=""),
    kit_id: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ids = [uuid.UUID(sid) for sid in schedule_ids.split(",") if sid.strip()]
    kid = None
    if kit_id and kit_id not in ("", "__none__", "none"):
        with contextlib.suppress(ValueError):
            kid = uuid.UUID(kit_id)
    with contextlib.suppress(NotFoundError, ValueError):
        await svc.record_batch_intake(db, user_id=user.id, schedule_ids=ids, slot_time=slot_time, kit_id=kid)
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-courses/generate-wizard")
async def generate_course_wizard(
    request: Request,
    goal: str = Form(default="hrt_lactation"),
    custom_prompt: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        data = await svc.generate_course_protocol(
            db, user_id=user.id, goal=goal, custom_prompt=custom_prompt
        )
        return {"status": "ok", "data": data}
    except Exception as exc:
        logger.error("Wizard generation error: %s", exc)
        return {"status": "error", "message": str(exc)}


@router.post("/med-courses/apply-wizard")
async def apply_course_wizard(
    request: Request,
    course_data: str = Form(...),
    kit_id: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    import json
    try:
        parsed = json.loads(course_data)
        kit_uuid = uuid.UUID(kit_id.strip()) if kit_id.strip() else None
        await svc.apply_generated_course(db, user_id=user.id, course_data=parsed, kit_id=kit_uuid)
    except Exception as exc:
        logger.error("Apply wizard error: %s", exc)
        raise HTTPException(400, f"Failed to apply course: {exc}") from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/medications/check-interactions")
async def check_interactions_endpoint(
    request: Request,
    med_names: str = Form(default=""),
    user: User = Depends(get_current_user),
):
    names = [n.strip() for n in med_names.split(",") if n.strip()]
    warnings = svc.check_drug_interactions(names)
    return {"status": "ok", "warnings": warnings}


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
            db, user_id=user.id, course_id=course_id, medication_id=medication_id,
            dose_quantity=dose_quantity, dose_unit=dose_unit, frequency_type=frequency_type,
            times_per_day=times_per_day, times_of_day=times_of_day, interval_hours=interval_hours,
            days_of_week=days_of_week, food_relation=food_relation,
            duration_days=duration_days, meal_offset_min=meal_offset_min,
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


@router.post("/med-courses/{course_id}/update")
async def update_course_form(
    request: Request,
    course_id: uuid.UUID,
    name: str = Form(...),
    start_date: str = Form(default=""),
    end_date: str = Form(default=""),
    status: str = Form(default="active"),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.update_course(
            db, user_id=user.id, course_id=course_id, name=name,
            start_date=start_date, end_date=end_date, status=status, notes=notes,
        )
    except (ValueError, NotFoundError) as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-courses/{course_id}/items/{item_id}/update")
async def update_course_item_form(
    request: Request,
    course_id: uuid.UUID,
    item_id: uuid.UUID,
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
        await svc.get_course(db, user.id, course_id)
        await svc.update_schedule(
            db, user.id, item_id,
            dose_quantity=dose_quantity, dose_unit=dose_unit,
            frequency_type=frequency_type, times_per_day=times_per_day,
            times_of_day=times_of_day, interval_hours=interval_hours,
            days_of_week=days_of_week, start_date=start_date, end_date=end_date,
            instructions=instructions, food_relation=food_relation,
            duration_days=duration_days, meal_offset_min=meal_offset_min,
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-courses/{course_id}/combine-slots")
async def combine_course_slots_form(
    request: Request,
    course_id: uuid.UUID,
    schedule_ids: list[str] = Form(default=[]),
    times_of_day: str = Form(...),
    food_relation: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        parsed_ids = [uuid.UUID(x.strip()) for x in schedule_ids if x.strip()]
        if parsed_ids:
            await svc.batch_combine_course_slots(
                db, user.id, course_id, parsed_ids,
                times_of_day=times_of_day, food_relation=food_relation,
            )
    except (ValueError, NotFoundError) as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-courses/{course_id}/items/{item_id}/delete")
async def delete_course_item_form(
    request: Request,
    course_id: uuid.UUID,
    item_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_course_item(db, user.id, course_id, item_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
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
    ul_confirmed: str = Form(default=""),
    kit_id: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sched_id = None
    if schedule_id and schedule_id != "__none__":
        sched_id = uuid.UUID(schedule_id)
    kid = None
    if kit_id and kit_id not in ("", "__none__", "none"):
        with contextlib.suppress(ValueError):
            kid = uuid.UUID(kit_id)
    qty = None
    if quantity_taken.strip():
        try:
            qty = float(quantity_taken)
        except ValueError:
            qty = None
    try:
        await svc.record_intake(
            db, user_id=user.id, medication_id=medication_id, schedule_id=sched_id,
            status=status, taken_at=taken_at, quantity_taken=qty, notes=notes,
            ul_confirmed=ul_confirmed.strip().lower() in {"1", "on", "true", "yes"},
            gamification=True, kit_id=kid,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-intakes/prn")
async def record_intake_prn(
    request: Request,
    medication_id: uuid.UUID = Form(...),
    quantity_taken: str = Form(default="1.0"),
    kit_id: str = Form(default=""),
    symptom_reason: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    qty = 1.0
    if quantity_taken.strip():
        try:
            qty = float(quantity_taken)
        except ValueError:
            qty = 1.0
    kit_uuid = None
    if kit_id.strip():
        with contextlib.suppress(ValueError):
            kit_uuid = uuid.UUID(kit_id.strip())
    try:
        await svc.record_prn_intake(
            db,
            user_id=user.id,
            medication_id=medication_id,
            quantity_taken=qty,
            kit_id=kit_uuid,
            symptom_reason=symptom_reason.strip() or None,
            notes=notes.strip() or None,
            gamification=True,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-intakes/{intake_id}/delete")
async def delete_intake_form(
    request: Request,
    intake_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_intake(db, user_id=user.id, intake_id=intake_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
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


@router.post("/med-kits/{kit_id}/update")
async def update_kit_form(
    request: Request,
    kit_id: uuid.UUID,
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
        await svc.update_kit(
            db, user_id=user.id, kit_id=kit_id, name=name, location=location, location_id=loc_uuid, notes=notes
        )
    except (ValueError, NotFoundError) as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-kits/{kit_id}/add-stock")
async def add_stock_to_kit_form(
    request: Request,
    kit_id: uuid.UUID,
    medication_id: uuid.UUID = Form(...),
    quantity: float = Form(default=1.0),
    unit: str = Form(default=""),
    expiry_date: str = Form(default=""),
    lot_number: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.add_stock_to_kit(
            db, user_id=user.id, kit_id=kit_id, medication_id=medication_id,
            quantity=quantity, unit=unit, expiry_date=expiry_date,
            lot_number=lot_number, notes=notes,
        )
    except (ValueError, NotFoundError) as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/med-kits/{kit_id}/add-item")
async def add_item_to_kit_form(
    request: Request,
    kit_id: uuid.UUID,
    medication_id: uuid.UUID = Form(...),
    unit: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.add_stock_to_kit(
            db, user_id=user.id, kit_id=kit_id, medication_id=medication_id,
            quantity=0.0, unit=unit, expiry_date="", lot_number="", notes=notes,
        )
    except (ValueError, NotFoundError) as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/medications", status_code=303)


@router.post("/medications/scan-barcode")
async def scan_barcode_endpoint(
    request: Request,
    raw_code: str = Form(default=""),
    file: UploadFile | None = File(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.datamatrix_service import decode_datamatrix_from_image, parse_gs1_datamatrix

    parsed_items = []
    if file and file.filename:
        try:
            image_bytes = await file.read()
            results = decode_datamatrix_from_image(image_bytes)
            parsed_items = [r.to_dict() for r in results]
        except Exception as e:
            logger.warning("Barcode image scan failed: %s", e)
    elif raw_code.strip():
        res = parse_gs1_datamatrix(raw_code.strip())
        parsed_items = [res.to_dict()]

    if not parsed_items:
        from fastapi.responses import JSONResponse
        return JSONResponse({"status": "not_found", "message": "Штрихкод / DataMatrix не обнаружен"}, status_code=404)

    first = parsed_items[0]
    matched = await svc.find_medication_by_barcode(db, user.id, gtin=first.get("gtin"), ean13=first.get("ean13"))
    matched_data = None
    if matched:
        matched_data = {"id": str(matched.id), "name": matched.name, "form": matched.form, "strength": matched.strength}

    from fastapi.responses import JSONResponse
    return JSONResponse({
        "status": "ok",
        "parsed": first,
        "all_barcodes": parsed_items,
        "matched_medication": matched_data,
    })


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
    return RedirectResponse(url=f"/medications?migrated={created}&skipped={skipped}", status_code=303)
