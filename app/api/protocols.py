"""Protocol Engine UI (R5.3) — thin HTTP wrappers over protocols_service.

Business logic (queries, steps parsing, capability/ownership checks, mutation wrappers)
lives in app/services/protocols_service.py. Template rendering stays here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.services.protocols_service import (
    complete_protocol_step_from_form,
    create_protocol_from_form,
    delete_protocol_by_id,
    get_builder_common_context,
    get_protocols_page_context,
    get_run_page_context,
    serialize_protocol_steps,
    start_protocol_from_form,
    update_protocol_from_form,
)
from app.templates_setup import templates

router = APIRouter(prefix="/protocols", tags=["protocols"])


# ── Страницы ──────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
async def protocols_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await get_protocols_page_context(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="protocols.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "protocols",
            **ctx,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def protocol_builder_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="protocol_builder.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "protocols",
            "proto": None,
            "steps": [],
            **get_builder_common_context(),
        },
    )


@router.get("/{protocol_id}/edit", response_class=HTMLResponse)
async def protocol_edit_page(
    request: Request,
    protocol_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.services.protocols_service import get_own_protocol

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    proto = await get_own_protocol(db, protocol_id, user.id)
    return templates.TemplateResponse(
        request=request,
        name="protocol_builder.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "protocols",
            "proto": proto,
            "steps": serialize_protocol_steps(proto),
            **get_builder_common_context(),
        },
    )


@router.get("/{protocol_id}/run", response_class=HTMLResponse)
async def protocol_run_page(
    request: Request,
    protocol_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ctx = await get_run_page_context(db, user.id, protocol_id)
    if ctx is None:
        return RedirectResponse(url="/protocols", status_code=303)

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="protocol_run.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "protocols",
            **ctx,
        },
    )


# ── Мутации ───────────────────────────────────────────────────────────


@router.post("/create")
async def protocols_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(default=""),
    category: str = Form(default="prep"),
    anchor_type: str = Form(default="session_bound"),
    steps_json: str = Form(default="[]"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proto = await create_protocol_from_form(
        db,
        user,
        title=title,
        description=description,
        category=category,
        anchor_type=anchor_type,
        steps_json=steps_json,
    )
    return RedirectResponse(url=f"/protocols/{proto.id}/edit", status_code=303)


@router.post("/{protocol_id}/update")
async def protocols_update(
    request: Request,
    protocol_id: uuid.UUID,
    title: str = Form(...),
    description: str = Form(default=""),
    category: str = Form(default="prep"),
    anchor_type: str = Form(default="session_bound"),
    steps_json: str = Form(default="[]"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proto = await update_protocol_from_form(
        db,
        user,
        protocol_id,
        title=title,
        description=description,
        category=category,
        anchor_type=anchor_type,
        steps_json=steps_json,
    )
    return RedirectResponse(url=f"/protocols/{proto.id}/edit", status_code=303)


@router.post("/{protocol_id}/delete")
async def protocols_delete(
    request: Request,
    protocol_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await delete_protocol_by_id(db, user, protocol_id)
    return RedirectResponse(url="/protocols", status_code=303)


@router.post("/{protocol_id}/start")
async def protocols_start(
    request: Request,
    protocol_id: uuid.UUID,
    anchor_time: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await start_protocol_from_form(db, user, protocol_id, anchor_time)
    return RedirectResponse(url=f"/protocols/{run.id}/run", status_code=303)


@router.post("/runs/{run_id}/complete-step")
async def protocols_complete_step(
    request: Request,
    run_id: uuid.UUID,
    step_log_id: uuid.UUID = Form(...),
    result_payload: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    run = await complete_protocol_step_from_form(
        db,
        user,
        run_id,
        step_log_id,
        result_payload,
    )
    if run is None:
        return RedirectResponse(url="/protocols", status_code=303)
    return RedirectResponse(url=f"/protocols/{run_id}/run", status_code=303)
