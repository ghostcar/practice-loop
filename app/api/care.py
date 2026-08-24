"""Personal Care API — Thin HTTP routes.

All business logic lives in app.services.care_service (ADR-161).
This file contains only HTTP parsing, response building, and dependency injection.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.services import care_service as svc
from app.services.media import save_media
from app.templates_setup import templates

router = APIRouter(tags=["care"])
json_router = APIRouter(prefix="/api/v2/care", tags=["care"])


# ─────────────────────────────────────────────────────────────────────────────
# HTML Pages
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/care", response_class=HTMLResponse)
async def care_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_care_page_context(db, user)
    return templates.TemplateResponse(
        request=request,
        name="care.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, **ctx},
    )


@router.get("/care/builder", response_class=HTMLResponse)
async def care_builder_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="care_builder.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "care",
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# HTML Form Handlers (POST → service → redirect)
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/care/routines")
async def add_routine(
    request: Request,
    name: str = Form(...),
    area: str = Form(default="other"),
    kind: str = Form(default="home"),
    place_name: str = Form(default=""),
    place_address: str = Form(default=""),
    frequency_days: str = Form(default=""),
    notes: str = Form(default=""),
    catalog_item_id: str = Form(default=""),
    product_ids: list[str] = Form(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.create_routine(
            db, user_id=user.id, name=name, area=area, kind=kind,
            place_name=place_name, place_address=place_address,
            frequency_days=frequency_days, notes=notes,
            catalog_item_id=catalog_item_id, product_ids=product_ids,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/routines/{routine_id}/delete")
async def delete_routine(
    request: Request,
    routine_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_routine(db, user.id, routine_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/products")
async def add_product(
    request: Request,
    name: str = Form(...),
    category: str = Form(default="other"),
    brand: str = Form(default=""),
    notes: str = Form(default=""),
    inventory_item_id: str = Form(default=""),
    catalog_item_id: str = Form(default=""),
    quantity: str = Form(default=""),
    expiry_date: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.create_product(
            db, user_id=user.id, name=name, category=category, brand=brand,
            notes=notes, inventory_item_id=inventory_item_id,
            catalog_item_id=catalog_item_id, quantity=quantity, expiry_date=expiry_date,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/products/{product_id}/delete")
async def delete_product(
    request: Request,
    product_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_product(db, user.id, product_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/entries")
async def add_entry(
    request: Request,
    entry_date: str = Form(...),
    routine_id: str = Form(default=""),
    place_name: str = Form(default=""),
    place_address: str = Form(default=""),
    duration_minutes: str = Form(default=""),
    skin_reaction: str = Form(default=""),
    notes: str = Form(default=""),
    product_ids: list[str] = Form(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.create_entry(
            db, user_id=user.id, entry_date=entry_date, routine_id=routine_id,
            place_name=place_name, place_address=place_address,
            duration_minutes=duration_minutes, skin_reaction=skin_reaction,
            notes=notes, product_ids=product_ids,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/entries/{entry_id}/media")
async def add_entry_media(
    request: Request,
    entry_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        info = await save_media(file)
        await svc.attach_entry_media(db, user_id=user.id, entry_id=entry_id, file_info=info, caption=caption)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/products/{product_id}/media")
async def add_product_media(
    request: Request,
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    caption: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        info = await save_media(file)
        await svc.attach_product_media(db, user_id=user.id, product_id=product_id, file_info=info, caption=caption)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/entries/{entry_id}/delete")
async def delete_entry(
    request: Request,
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_entry(db, user.id, entry_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/courses")
async def add_course(
    request: Request,
    name: str = Form(...),
    area: str = Form(default="other"),
    place_name: str = Form(default=""),
    place_address: str = Form(default=""),
    total_sessions: str = Form(default="1"),
    interval_days: str = Form(default=""),
    start_date: str = Form(default=""),
    notes: str = Form(default=""),
    catalog_item_id: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.create_course(
            db, user_id=user.id, name=name, area=area,
            place_name=place_name, place_address=place_address,
            total_sessions=total_sessions, interval_days=interval_days,
            start_date=start_date, notes=notes, catalog_item_id=catalog_item_id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/courses/{course_id}/delete")
async def delete_course(
    request: Request,
    course_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_course(db, user.id, course_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/course-sessions/{session_id}/done")
async def mark_session_done(
    request: Request,
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.mark_course_session_done(db, user.id, session_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/care", status_code=303)


@router.post("/care/course-sessions/{session_id}/skip")
async def mark_session_skipped(
    request: Request,
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.mark_course_session_skipped(db, user.id, session_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/care", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────


@json_router.get("")
async def json_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_care_summary(db, user.id)


@json_router.post("/routines", status_code=201)
async def json_add_routine(
    body: svc.RoutineBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        routine = await svc.json_create_routine(db, user.id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return svc.routine_json(routine)


@json_router.post("/entries", status_code=201)
async def json_add_entry(
    body: svc.EntryBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        entry, product_ids = await svc.json_create_entry(db, user.id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    prod_map = {str(entry.id): [str(p) for p in product_ids]}
    return svc.entry_json(entry, prod_map)


@json_router.delete("/routines/{routine_id}", status_code=204)
async def json_delete_routine(
    routine_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.json_delete_routine(db, user.id, routine_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return None


@json_router.delete("/entries/{entry_id}", status_code=204)
async def json_delete_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.json_delete_entry(db, user.id, entry_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return None


@json_router.get("/products")
async def json_list_products(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_list_products(db, user.id)


@json_router.post("/products", status_code=201)
async def json_add_product(
    body: svc.ProductBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        product = await svc.json_create_product(db, user.id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return svc.product_json(product)


@json_router.delete("/products/{product_id}", status_code=204)
async def json_delete_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.json_delete_product(db, user.id, product_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return None


@json_router.get("/courses")
async def json_list_courses(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_list_courses(db, user.id)


@json_router.post("/courses", status_code=201)
async def json_add_course(
    body: svc.CourseBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        course = await svc.json_create_course(db, user.id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return svc.course_json(course)


@json_router.delete("/courses/{course_id}", status_code=204)
async def json_delete_course(
    course_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.json_delete_course(db, user.id, course_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return None


@json_router.post("/course-sessions/{session_id}/done")
async def json_mark_course_session_done(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        session = await svc.mark_course_session_done(db, user.id, session_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return {"id": str(session.id), "status": session.status, "completed_at": session.completed_at.isoformat()}


@json_router.post("/course-sessions/{session_id}/skip")
async def json_mark_course_session_skipped(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        session = await svc.mark_course_session_skipped(db, user.id, session_id)
    except ValueError as e:
        raise HTTPException(404, str(e)) from None
    return {"id": str(session.id), "status": session.status, "completed_at": None}


@json_router.post("/aftercare/generate")
async def json_generate_aftercare(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.llm.pipeline.aftercare import generate_aftercare_guidance
    from app.services.llm_provider import get_active_llm_config

    llm_config = await get_active_llm_config(db, user.id)
    if not llm_config:
        raise HTTPException(400, "LLM provider config is required for Aftercare AI Assistant")
    locale = detect_locale(request, user.locale)
    res = await generate_aftercare_guidance(db, user.id, llm_config, locale=locale)
    return res


# Re-export service helpers that other modules may import from care.py
from app.services.care_service import get_care_summary as _care_summary  # noqa: E402, F401
