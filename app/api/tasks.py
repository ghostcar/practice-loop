"""Tasks API — generation, creation, completion.

All business logic lives in app.services.tasks_service (ADR-170).
This file contains only HTTP parsing, response building, and dependency injection.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.services import tasks_service as svc
from app.services.errors import NotFoundError
from app.templates_setup import templates

router = APIRouter(prefix="/tasks", tags=["tasks"])


# ─────────────────────────────────────────────────────────────────────────────
# Page
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    error: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    body_part_id: str | None = Query(None),
    location_id: str | None = Query(None),
    inventory_item_id: str | None = Query(None),
    attention: bool = Query(False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    ctx = await svc.get_tasks_page_context(
        db, user.id,
        status_filter=status_filter,
        body_part_id=body_part_id,
        location_id=location_id,
        inventory_item_id=inventory_item_id,
        attention=attention,
    )

    return templates.TemplateResponse(
        request=request,
        name="tasks.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "error": error,
            "active_nav": "tasks",
            "status_filter": status_filter or "",
            "body_part_id": body_part_id or "",
            "location_id": location_id or "",
            "inventory_item_id": inventory_item_id or "",
            "attention": attention,
            **ctx,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# API: Generate
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/generate")
async def generate_task_endpoint(
    request: Request,
    custom_prompt: str = Form(default=""),
    preferred_body_part: str = Form(default=""),
    preferred_location: str = Form(default=""),
    preferred_item: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    try:
        await svc.execute_llm_generation(
            db, user.id, locale=locale,
            custom_prompt=custom_prompt.strip() or None,
            body_part_id=preferred_body_part.strip() or None,
            location_id=preferred_location.strip() or None,
            inventory_item_id=preferred_item.strip() or None,
        )
    except ValueError as e:
        return RedirectResponse(url=f"/tasks/?error={e}", status_code=status.HTTP_303_SEE_OTHER)
    except Exception:
        return RedirectResponse(
            url="/tasks/?error=LLM+request+failed.+Check+your+provider+configuration.",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(url="/tasks/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/generate-deterministic")
async def generate_deterministic(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.execute_deterministic_task(db, user.id)
    except ValueError as e:
        return RedirectResponse(url=f"/tasks/?error={e}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/tasks/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/generate-weekly")
async def generate_weekly_endpoint(
    request: Request,
    days: int = Form(7),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    try:
        await svc.execute_weekly_generation(db, user.id, locale=locale, days=days)
    except (ValueError, Exception) as e:
        return RedirectResponse(url="/tasks/?error=generation_failed", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/tasks/", status_code=status.HTTP_303_SEE_OTHER)


# ─────────────────────────────────────────────────────────────────────────────
# Params form
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/params-form", response_class=HTMLResponse)
async def params_form(
    request: Request,
    entity_id: uuid.UUID,
    prefix: str = Query(default="param_"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    try:
        entity, defs = await svc.get_entity_for_params(db, entity_id, user.id)
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Entity not found") from None

    return templates.TemplateResponse(
        request=request,
        name="partials/params_form.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "entity": entity,
            "param_defs": defs,
            "form_prefix": prefix,
        },
    )


@router.post("/create")
async def create_manual_task(
    request: Request,
    entity_id: uuid.UUID = Form(...),
    planned_comment: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    form = await request.form()
    try:
        await svc.create_manual_task_from_form(
            db, user.id, entity_id, form_data=form, planned_comment=planned_comment, locale=locale,
        )
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Entity not found") from None
    except ValueError as e:
        return RedirectResponse(url=f"/tasks/?error={e}", status_code=status.HTTP_303_SEE_OTHER)
    return RedirectResponse(url="/tasks/", status_code=status.HTTP_303_SEE_OTHER)


# ─────────────────────────────────────────────────────────────────────────────
# Complete / Interrupt
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{log_id}/complete")
async def complete_task(
    request: Request,
    log_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.complete_task(db, log_id, user)
    except ValueError:
        raise HTTPException(status_code=404, detail="Activity not found") from None
    return RedirectResponse(url="/tasks/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{log_id}/interrupt")
async def interrupt_task(
    request: Request,
    log_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.interrupt_task(db, log_id, user)
    except ValueError:
        raise HTTPException(status_code=404, detail="Activity not found") from None
    return RedirectResponse(url="/tasks/", status_code=status.HTTP_303_SEE_OTHER)
