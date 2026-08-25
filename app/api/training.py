"""Training API — Thin HTTP routes.

All business logic lives in app.services.training_service (ADR-166).
This file contains only HTTP parsing, response building, and dependency injection.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.services import training_service as svc
from app.services.errors import NotFoundError
from app.templates_setup import templates

router = APIRouter(prefix="/training", tags=["training"])


# ─────────────────────────────────────────────────────────────────────────────
# HTML Pages
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/builder", response_class=HTMLResponse)
async def training_builder_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="training_builder.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "training",
        },
    )


@router.get("/", response_class=HTMLResponse)
async def training_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_training_page_context(db, user)
    return templates.TemplateResponse(
        request=request,
        name="training.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, **ctx},
    )


@router.get("/adaptive", response_class=HTMLResponse)
async def adaptive_training_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_adaptive_page_context(db, user)
    return templates.TemplateResponse(
        request=request,
        name="training_adaptive.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, **ctx},
    )


# ─────────────────────────────────────────────────────────────────────────────
# HTML Form Handlers
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/plan")
async def generate_plan(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    form = await request.form()
    plan_name = (form.get("name", "").strip())[:200] or None
    try:
        await svc.generate_plan(db, user.id, plan_name, locale)
    except ValueError as e:
        return RedirectResponse(url=f"/training?error={e}", status_code=303)
    except Exception as e:
        # LLM errors, network failures, etc. — don't leave partial plan state
        return RedirectResponse(url=f"/training?error={e}", status_code=303)
    return RedirectResponse(url="/training", status_code=303)


@router.post("/tasks")
async def create_manual_training_task(
    request: Request,
    entity_id: uuid.UUID = Form(...),
    training_day_id: str = Form(default=""),
    planned_comment: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    form = await request.form()
    try:
        await svc.create_manual_task(
            db,
            user_id=user.id,
            entity_id=entity_id,
            training_day_id=training_day_id,
            planned_comment=planned_comment,
            form_data=form,
            locale=locale,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        return RedirectResponse(url=f"/training?error={str(e)}", status_code=303)
    return RedirectResponse(url="/training", status_code=303)


@router.post("/tasks/{log_id}/subtasks/{sub_idx}/toggle")
async def toggle_subtask(
    log_id: uuid.UUID,
    sub_idx: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.toggle_subtask(db, user.id, log_id, sub_idx)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return RedirectResponse(url="/training", status_code=303)


@router.post("/tasks/{log_id}/complete")
async def complete_training_task(
    log_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.complete_task(db, user.id, log_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return RedirectResponse(url="/training", status_code=303)


@router.post("/analyze")
async def analyze_day(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    form = await request.form()
    plan_id_str = form.get("training_day_id", "")
    plan_id = None
    if plan_id_str:
        try:
            plan_id = uuid.UUID(str(plan_id_str))
        except ValueError:
            plan_id = None
    try:
        await svc.analyze_day(db, user.id, plan_id, locale)
    except ValueError as e:
        return RedirectResponse(url=f"/training?error={e}", status_code=303)
    except Exception as e:
        return RedirectResponse(url=f"/training?error={e}", status_code=303)
    return RedirectResponse(url="/training", status_code=303)


@router.post("/log-entry/reorder")
async def reorder_log_entries(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    payload = await request.json()
    training_day_id_str = payload.get("training_day_id")
    ids = payload.get("ids", [])
    if not training_day_id_str or not ids:
        raise HTTPException(status_code=400, detail="training_day_id and ids required")
    try:
        td_id = uuid.UUID(str(training_day_id_str))
        id_list = [uuid.UUID(str(i)) for i in ids]
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid id format") from None
    try:
        await svc.reorder_log_entries(db, user.id, td_id, id_list)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return {"status": "ok"}


@router.post("/log-entry/{entry_id}")
async def update_log_entry(
    entry_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    try:
        entry = await svc.update_log_entry(db, user.id, entry_id, form)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return HTMLResponse(svc.render_log_entry_row(entry))


@router.post("/log-entry")
async def add_extra_log_entry(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    td_str = form.get("training_day_id", "")
    time_label = form.get("time_label", "").strip()[:20]
    if not td_str or not time_label:
        raise HTTPException(status_code=400, detail="training_day_id and time_label required")
    try:
        td_id = uuid.UUID(td_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid training_day_id") from None
    try:
        entry = await svc.add_extra_log_entry(db, user_id=user.id, td_id=td_id, time_label=time_label, form_data=form)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return HTMLResponse(svc.render_log_entry_row(entry))


@router.delete("/log-entry/{entry_id}")
async def delete_log_entry(
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_log_entry(db, user.id, entry_id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    return HTMLResponse("")


@router.post("/adaptive/create")
async def create_adaptive_program_endpoint(
    request: Request,
    title: str = Form(...),
    focus_domain: str = Form("bladder_control"),
    total_days: int = Form(14),
    difficulty_level: int = Form(2),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.create_adaptive_program(
        db,
        user_id=user.id,
        title=title,
        focus_domain=focus_domain,
        total_days=total_days,
        difficulty_level=difficulty_level,
    )
    return RedirectResponse(url="/training/adaptive", status_code=303)


@router.post("/adaptive/steps/{step_id}/log")
async def log_step_feedback_endpoint(
    request: Request,
    step_id: uuid.UUID,
    comfort_score: int = Form(...),
    actual_minutes: int = Form(...),
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.log_step_feedback(
        db,
        step_id=step_id,
        comfort_score=comfort_score,
        actual_minutes=actual_minutes,
        notes=notes,
        user_id=user.id,
    )
    return RedirectResponse(url="/training/adaptive", status_code=303)


# Re-export for tests that import from app.api.training (ADR-166)
_render_log_entry_row = svc.render_log_entry_row
