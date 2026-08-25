"""Sexual Journal API — Thin HTTP routes.

All business logic lives in app.services.journal_service (ADR-164).
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
from app.services import journal_service as svc
from app.services.errors import NotFoundError
from app.services.media import save_media
from app.templates_setup import templates
from app.timeutils import local_today

router = APIRouter(tags=["journal"])
json_router = APIRouter(prefix="/api/v2/journal", tags=["journal"])


# ─────────────────────────────────────────────────────────────────────────────
# HTML Pages
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/journal", response_class=HTMLResponse)
async def journal_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_journal_page_context(db, user)
    return templates.TemplateResponse(
        request=request,
        name="journal.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "today": local_today(),
            **ctx,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# HTML Form Handlers
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/journal/entries")
async def add_entry(
    request: Request,
    entry_date: str = Form(...),
    partner_id: str = Form(default=""),
    activity_type: str = Form(default=""),
    duration_minutes: str = Form(default=""),
    desire_before: str = Form(default=""),
    arousal_before: str = Form(default=""),
    protection: str = Form(default="none"),
    orgasms: str = Form(default=""),
    intensity: str = Form(default=""),
    satisfaction: str = Form(default=""),
    pleasure: str = Form(default=""),
    reactions: str = Form(default=""),
    emotional_state: str = Form(default=""),
    aftercare: str = Form(default=""),
    recovery: str = Form(default=""),
    notes: str = Form(default=""),
    activity_log_id: str = Form(default=""),
    catalog_item_id: str = Form(default=""),
    care_product_ids: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.create_entry(
            db, user_id=user.id, entry_date=entry_date, partner_id=partner_id,
            activity_type=activity_type, duration_minutes=duration_minutes,
            desire_before=desire_before, arousal_before=arousal_before,
            protection=protection, orgasms=orgasms, intensity=intensity,
            satisfaction=satisfaction, pleasure=pleasure, reactions=reactions,
            emotional_state=emotional_state, aftercare=aftercare, recovery=recovery,
            notes=notes, activity_log_id=activity_log_id, catalog_item_id=catalog_item_id,
            care_product_ids=care_product_ids,
        )
    except (ValueError, NotFoundError) as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/journal", status_code=303)


@router.post("/journal/entries/{entry_id}/complete")
async def complete_entry(
    request: Request,
    entry_id: uuid.UUID,
    activity_type: str = Form(default=""),
    duration_minutes: str = Form(default=""),
    desire_before: str = Form(default=""),
    arousal_before: str = Form(default=""),
    protection: str = Form(default="none"),
    orgasms: str = Form(default=""),
    intensity: str = Form(default=""),
    satisfaction: str = Form(default=""),
    pleasure: str = Form(default=""),
    reactions: str = Form(default=""),
    emotional_state: str = Form(default=""),
    aftercare: str = Form(default=""),
    recovery: str = Form(default=""),
    notes: str = Form(default=""),
    catalog_item_id: str = Form(default=""),
    care_product_ids: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.complete_entry(
            db, user_id=user.id, entry_id=entry_id,
            activity_type=activity_type, duration_minutes=duration_minutes,
            desire_before=desire_before, arousal_before=arousal_before,
            protection=protection, orgasms=orgasms, intensity=intensity,
            satisfaction=satisfaction, pleasure=pleasure, reactions=reactions,
            emotional_state=emotional_state, aftercare=aftercare, recovery=recovery,
            notes=notes, catalog_item_id=catalog_item_id, care_product_ids=care_product_ids,
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/journal", status_code=303)


@router.post("/journal/entries/{entry_id}/media")
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
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/journal", status_code=303)


@router.post("/journal/entries/{entry_id}/delete")
async def delete_entry(
    request: Request,
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_entry(db, user.id, entry_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/journal", status_code=303)


@router.post("/journal/partners")
async def add_partner(
    request: Request,
    name: str = Form(...),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.create_partner(db, user_id=user.id, name=name, notes=notes)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/journal", status_code=303)


@router.post("/journal/partners/{partner_id}/delete")
async def delete_partner(
    request: Request,
    partner_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_partner(db, user.id, partner_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/journal", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────


@json_router.get("")
async def json_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_journal_summary(db, user.id)


@json_router.post("/entries", status_code=201)
async def json_add_entry(
    body: svc.EntryBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        entry = await svc.json_create_entry(db, user.id, body)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return svc.entry_json(entry)


@json_router.post("/entries/{entry_id}/complete")
async def json_complete_entry(
    entry_id: uuid.UUID,
    body: svc.CompleteBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        entry = await svc.json_complete_entry(db, user.id, entry_id, body)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return svc.entry_json(entry)


@json_router.post("/partners", status_code=201)
async def json_add_partner(
    body: svc.PartnerBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        partner = await svc.json_create_partner(db, user.id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return {"id": str(partner.id), "name": partner.name, "notes": partner.notes}


@json_router.delete("/entries/{entry_id}", status_code=204)
async def json_delete_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.json_delete_entry(db, user.id, entry_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return None


@json_router.delete("/partners/{partner_id}", status_code=204)
async def json_delete_partner(
    partner_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.json_delete_partner(db, user.id, partner_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return None


@json_router.post("/partners/{partner_id}/analyze")
async def json_analyze_partner_dynamics(
    request: Request,
    partner_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.services.llm_provider import get_active_llm_config as get_llm

    llm_config = await get_llm(db, user.id)
    if not llm_config:
        raise HTTPException(400, "LLM provider config is required for Partner Dynamics Consultant")
    locale = detect_locale(request, user.locale)
    try:
        res = await svc.json_analyze_partner_dynamics(db, user.id, partner_id, llm_config, locale=locale)
    except Exception as e:
        raise HTTPException(500, str(e)) from None
    return res


# Re-export helpers that other modules import from journal.py
from app.services.journal_service import (
    ensure_timer_slot_entry,  # noqa: E402, F401
    get_pending_slot_entry,  # noqa: E402, F401
)
from app.services.journal_service import journal_summary as _journal_summary  # noqa: E402, F401
