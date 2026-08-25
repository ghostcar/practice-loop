"""Aftercare Module — thin HTTP wrappers over app.services.aftercare_service."""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.services.aftercare_service import (
    AFTERCARE_KINDS,
    aftercare_summary,
    create_entry,
    delete_entry,
    get_aftercare_page_context,
)
from app.templates_setup import templates

router = APIRouter(tags=["aftercare"])
json_router = APIRouter(prefix="/api/v2/aftercare", tags=["aftercare"])

# Re-exports for dashboard_service + today.py
async def _aftercare_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    return await aftercare_summary(db, user_id)

__all__ = ["router", "json_router", "_aftercare_summary"]


# ── Pages ──
@router.get("/aftercare", response_class=HTMLResponse)
async def aftercare_page(
    request: Request, db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    t = get_translations(locale)
    ctx = await get_aftercare_page_context(db, user.id)
    return templates.TemplateResponse(request=request, name="aftercare.html", context={
        "request": request, "t": t, "user": user, "locale": locale,
        "theme": detect_theme(user.theme), "active_nav": "aftercare",
        "kinds": AFTERCARE_KINDS, **ctx,
    })


@router.post("/aftercare/entries")
async def add_entry_form(
    request: Request, entry_date: str = Form(default=""),
    journal_entry_id: str = Form(default=""),
    timer_session_id: str = Form(default=""),
    kind: str = Form(...), comfort_level: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    parsed_date = date.fromisoformat(entry_date) if entry_date else date.today()
    comfort = int(comfort_level) if comfort_level else None
    jid = uuid.UUID(journal_entry_id) if journal_entry_id else None
    tid = uuid.UUID(timer_session_id) if timer_session_id else None
    await create_entry(db, user.id, entry_date=parsed_date, kind=kind,
                       comfort_level=comfort, notes=notes or None,
                       journal_entry_id=jid, timer_session_id=tid)
    return RedirectResponse(url="/aftercare", status_code=303)


@router.post("/aftercare/delete")
async def delete_entry_form(
    entry_id: uuid.UUID = Form(...),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    try:
        await delete_entry(db, user.id, entry_id)
    except ValueError:
        raise HTTPException(404, "Entry not found") from None
    return RedirectResponse(url="/aftercare", status_code=303)


# ── JSON API ──
@json_router.get("")
async def json_list_entries(
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import select

    from app.models.aftercare import AftercareEntry
    rows = (await db.execute(
        select(AftercareEntry)
        .where(AftercareEntry.user_id == user.id)
        .order_by(AftercareEntry.entry_date.desc())
    )).scalars().all()
    return {
        "total": len(rows),
        "entries": [{
            "id": str(r.id), "entry_date": r.entry_date.isoformat(),
            "kind": r.kind, "comfort_level": r.comfort_level,
            "notes": r.notes,
            "journal_entry_id": str(r.journal_entry_id) if r.journal_entry_id else None,
            "timer_session_id": str(r.timer_session_id) if r.timer_session_id else None,
        } for r in rows],
    }


class AftercareBody(BaseModel):
    kind: str = "physical"
    comfort_level: int | None = None
    notes: str | None = None
    journal_entry_id: str | None = None
    timer_session_id: str | None = None
    entry_date: str | None = None


@json_router.post("/entries", status_code=201)
async def json_add_entry(
    body: AftercareBody, user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.kind not in AFTERCARE_KINDS:
        raise HTTPException(400, "Invalid kind")
    # Validate journal_entry_id belongs to user
    if body.journal_entry_id:
        from sqlalchemy import select

        from app.models.journal import JournalEntry
        je = (await db.execute(
            select(JournalEntry).where(JournalEntry.id == uuid.UUID(body.journal_entry_id))
        )).scalar_one_or_none()
        if not je or je.user_id != user.id:
            raise HTTPException(400, "Journal entry not found or not owned")
    parsed_date = date.fromisoformat(body.entry_date) if body.entry_date else date.today()
    jid = uuid.UUID(body.journal_entry_id) if body.journal_entry_id else None
    tid = uuid.UUID(body.timer_session_id) if body.timer_session_id else None
    entry = await create_entry(db, user.id, entry_date=parsed_date, kind=body.kind,
                               comfort_level=body.comfort_level, notes=body.notes,
                               journal_entry_id=jid, timer_session_id=tid)
    return JSONResponse({
        "id": str(entry.id),
        "entry_date": entry.entry_date.isoformat() if entry.entry_date else None,
        "kind": entry.kind,
        "comfort_level": entry.comfort_level,
        "notes": entry.notes,
        "journal_entry_id": str(entry.journal_entry_id) if entry.journal_entry_id else None,
        "timer_session_id": str(entry.timer_session_id) if entry.timer_session_id else None,
    }, status_code=201)


@json_router.delete("/entries/{entry_id}", status_code=204)
async def json_delete_entry(
    entry_id: uuid.UUID, user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await delete_entry(db, user.id, entry_id)
    except ValueError:
        raise HTTPException(404, "Entry not found") from None
    return JSONResponse(None, status_code=204)
