"""Activity Sessions — CRUD, lifecycle, JSON API, and interactive pages.

All business logic lives in app.services.sessions_service (ADR-169).
This file contains only HTTP parsing, response building, and dependency injection.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.session import ActivitySession
from app.models.user import User
from app.services import sessions_service as svc
from app.services.errors import NotFoundError
from app.templates_setup import templates

router = APIRouter(tags=["sessions"])
session_json_router = APIRouter(prefix="/api/v2/sessions", tags=["sessions"])


# ─────────────────────────────────────────────────────────────────────────────
# Interactive pages
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/sessions/live", response_class=HTMLResponse)
async def sessions_live_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="sessions_live.html",
        context={
            "request": request, "t": t, "user": user, "locale": locale,
            "theme": theme, "active_nav": "sessions",
        },
    )


@router.get("/sessions/coop", response_class=HTMLResponse)
async def sessions_coop_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_coop_page_context(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="sessions_coop.html",
        context={
            "request": request, "t": t, "user": user, "locale": locale, "theme": theme,
            "active_nav": "sessions", **ctx,
        },
    )


@router.get("/sessions", response_class=HTMLResponse)
async def sessions_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_sessions_page_context(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="sessions.html",
        context={
            "request": request, "t": t, "user": user, "locale": locale, "theme": theme,
            "active_nav": "sessions", **ctx,
        },
    )


@router.get("/sessions/rules-builder", response_class=HTMLResponse)
async def sessions_rules_builder_page(request: Request, user: User = Depends(get_current_user)):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request, name="sessions_rules_builder.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, "active_nav": "sessions"},
    )


@router.get("/sessions/wizard", response_class=HTMLResponse)
async def sessions_wizard_page(request: Request, user: User = Depends(get_current_user)):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request, name="sessions_wizard.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, "active_nav": "sessions"},
    )


@router.get("/sessions/ambient", response_class=HTMLResponse)
async def sessions_ambient_page(request: Request, user: User = Depends(get_current_user)):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request, name="sessions_ambient.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, "active_nav": "sessions"},
    )


# ─────────────────────────────────────────────────────────────────────────────
# Lifecycle mutations
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/sessions/live/complete")
async def live_session_complete_endpoint(
    session_id: str | None = Form(None),
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.complete_live_session(db, user.id, session_id, notes)
    except ValueError as e:
        if "UUID" in str(e):
            raise HTTPException(status_code=400, detail=str(e)) from None
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/live/interrupt")
async def live_session_interrupt_endpoint(
    session_id: str | None = Form(None),
    reason: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.interrupt_live_session(db, user.id, session_id, reason)
    except ValueError as e:
        if "UUID" in str(e):
            raise HTTPException(status_code=400, detail=str(e)) from None
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/create-from-template")
async def create_session_from_template(
    request: Request,
    template_type: str = Form(default="chastity"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.create_session_from_template(db, user.id, template_type)
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/create-custom")
async def create_custom_session(
    request: Request,
    title: str = Form(...),
    ai_role: str = Form(default="keyholder"),
    notes: str = Form(default=""),
    ext_wheel: bool = Form(default=False),
    ext_pillory: bool = Form(default=False),
    ext_tag_seal: bool = Form(default=False),
    ext_peer_review: bool = Form(default=False),
    ext_dice: bool = Form(default=False),
    ext_aftercare: bool = Form(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.create_custom_session(
        db, user.id, title=title, ai_role=ai_role, notes=notes,
        ext_wheel=ext_wheel, ext_pillory=ext_pillory, ext_tag_seal=ext_tag_seal,
        ext_peer_review=ext_peer_review, ext_dice=ext_dice, ext_aftercare=ext_aftercare,
    )
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions")
async def create_session(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    await svc.create_session(db, user.id)
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/accept")
async def accept_session(s_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        session = await svc.get_owned_session(db, s_id, user.id)
        await svc.accept_session(db, session, user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/tasks/attach")
async def attach_session_task(
    s_id: uuid.UUID, task_id: uuid.UUID = Form(...),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    try:
        session = await svc.get_owned_session(db, s_id, user.id)
        await svc.attach_task(db, session, task_id, user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/tasks/{task_id}/detach")
async def detach_session_task(
    s_id: uuid.UUID, task_id: uuid.UUID,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    try:
        session = await svc.get_owned_session(db, s_id, user.id)
        await svc.detach_task(db, session, task_id, user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/start")
async def start_session(s_id: uuid.UUID, request: Request, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    try:
        session = await svc.get_owned_session(db, s_id, user.id)
        await svc.start_session(db, session, user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/end")
async def end_session(s_id: uuid.UUID, request: Request, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    try:
        session = await svc.get_owned_session(db, s_id, user.id)
        await svc.end_session(db, session, user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return RedirectResponse(url="/sessions", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (api/v2/sessions)
# ─────────────────────────────────────────────────────────────────────────────


class _SessionCreateIn(BaseModel):
    title: str | None = None
    notes: str | None = None
    session_rules: dict | None = None


class _SessionTaskIn(BaseModel):
    task_id: uuid.UUID


@session_json_router.get("")
async def json_sessions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await svc.get_sessions_page_context(db, user.id)
    return [svc.session_json(s) for s in result["sessions"]]


@session_json_router.post("")
async def json_create_session(data: _SessionCreateIn, user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    session = await svc.create_session(db, user.id, title=data.title, notes=data.notes, session_rules=data.session_rules)
    return JSONResponse(svc.session_json(session), status_code=201)


@session_json_router.post("/{session_id}/accept")
async def json_accept_session(session_id: uuid.UUID, user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    try:
        session = await svc.get_owned_session(db, session_id, user.id)
        await svc.accept_session(db, session, user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return svc.session_json(session)


@session_json_router.post("/{session_id}/start")
async def json_start_session(session_id: uuid.UUID, user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    try:
        session = await svc.get_owned_session(db, session_id, user.id)
        await svc.start_session(db, session, user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return svc.session_json(session)


@session_json_router.post("/{session_id}/end")
async def json_end_session(session_id: uuid.UUID, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    try:
        session = await svc.get_owned_session(db, session_id, user.id)
        await svc.end_session(db, session, user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return svc.session_json(session)


@session_json_router.post("/{session_id}/tasks")
async def json_attach_session_task(session_id: uuid.UUID, data: _SessionTaskIn,
                                   user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        session = await svc.get_owned_session(db, session_id, user.id)
        await svc.attach_task(db, session, data.task_id, user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    await db.refresh(session, ["logs"])
    return svc.session_json(session)


@session_json_router.delete("/{session_id}/tasks/{task_id}", status_code=204)
async def json_detach_session_task(session_id: uuid.UUID, task_id: uuid.UUID,
                                   user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    try:
        session = await svc.get_owned_session(db, session_id, user.id)
        await svc.detach_task(db, session, task_id, user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    return None


@session_json_router.get("/{session_id}/history")
async def json_session_history(session_id: uuid.UUID, user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    try:
        await svc.get_owned_session(db, session_id, user.id)
    except NotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return await svc.get_session_history(db, session_id)
