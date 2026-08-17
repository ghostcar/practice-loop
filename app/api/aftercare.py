"""Aftercare module API (C1, PRODUCT_OVERVIEW §5.3/§7).

Структурированный журнал заботы после сцены. **Relief-only** (PD-013).
Записи — Private Record (DATA_LIFECYCLE.md): отдельное удаление, мягкие
связи с Sexual Journal (FK SET NULL) и Chastity Timer (по ID).

Страницы:
- GET  /aftercare                  — форма + история
- POST /aftercare/entries          — создать запись → redirect
- POST /aftercare/entries/{id}/delete — удалить запись → redirect

JSON API (мобильный/bearer):
- GET    /api/v2/aftercare         — сводка + записи
- POST   /api/v2/aftercare/entries — создать запись (201)
- DELETE /api/v2/aftercare/entries/{id} — удалить (204)
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.aftercare import AFTERCARE_KINDS, AftercareEntry
from app.models.journal import JournalEntry
from app.models.user import User
from app.templates_setup import templates
from app.timeutils import local_today

router = APIRouter(tags=["aftercare"])
json_router = APIRouter(prefix="/api/v2/aftercare", tags=["aftercare"])


def _entry_json(e: AftercareEntry) -> dict:
    return {
        "id": str(e.id),
        "entry_date": e.entry_date.isoformat(),
        "journal_entry_id": str(e.journal_entry_id) if e.journal_entry_id else None,
        "timer_session_id": str(e.timer_session_id) if e.timer_session_id else None,
        "kind": e.kind,
        "comfort_level": e.comfort_level,
        "notes": e.notes,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }


async def _aftercare_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Dashboard summary: entries in 30d / last entry / kinds count. Relief-only."""
    rows = (
        (
            await db.execute(
                select(AftercareEntry)
                .where(AftercareEntry.user_id == user_id)
                .order_by(AftercareEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "total": len(rows),
        "last": _entry_json(rows[0]) if rows else None,
        "kinds": {k: sum(1 for r in rows if r.kind == k) for k in AFTERCARE_KINDS},
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page + form handlers (HTMX)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/aftercare", response_class=HTMLResponse)
async def aftercare_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    entries = (
        (
            await db.execute(
                select(AftercareEntry)
                .where(AftercareEntry.user_id == user.id)
                .order_by(AftercareEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    journal_entries = (
        (
            await db.execute(
                select(JournalEntry).where(JournalEntry.user_id == user.id).order_by(JournalEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        request,
        "aftercare.html",
        {
            "t": t,
            "theme": theme,
            "nav_key": "aftercare",
            "entries": [_entry_json(e) for e in entries],
            "journal_entries": journal_entries,
            "kinds": AFTERCARE_KINDS,
            "today": local_today().isoformat(),
        },
    )


@router.post("/aftercare/entries")
async def add_entry_form(
    request: Request,
    entry_date: str = Form(default=""),
    journal_entry_id: str = Form(default=""),
    timer_session_id: str = Form(default=""),
    kind: str = Form(...),
    comfort_level: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if kind not in AFTERCARE_KINDS:
        raise HTTPException(400, "Invalid kind")

    parsed_date = date.fromisoformat(entry_date) if entry_date.strip() else local_today()
    journal_id = uuid.UUID(journal_entry_id) if journal_entry_id.strip() else None
    timer_id = uuid.UUID(timer_session_id) if timer_session_id.strip() else None
    comfort = int(comfort_level) if comfort_level.strip().isdigit() else None
    if comfort is not None and not (1 <= comfort <= 5):
        raise HTTPException(400, "comfort_level must be 1-5")

    if journal_id is not None:
        own = (
            await db.execute(select(JournalEntry).where(JournalEntry.id == journal_id, JournalEntry.user_id == user.id))
        ).scalar_one_or_none()
        if own is None:
            raise HTTPException(400, "Journal entry not found")

    e = AftercareEntry(
        user_id=user.id,
        entry_date=parsed_date,
        journal_entry_id=journal_id,
        timer_session_id=timer_id,
        kind=kind,
        comfort_level=comfort,
        notes=(notes or "").strip() or None,
    )
    db.add(e)
    await db.flush()
    return RedirectResponse(url="/aftercare", status_code=303)


@router.post("/aftercare/entries/{entry_id}/delete")
async def delete_entry_form(
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    e = (
        await db.execute(select(AftercareEntry).where(AftercareEntry.id == entry_id, AftercareEntry.user_id == user.id))
    ).scalar_one_or_none()
    if e is None:
        raise HTTPException(404, "Aftercare entry not found")
    await db.delete(e)
    await db.flush()
    return RedirectResponse(url="/aftercare", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────


@json_router.get("")
async def json_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rows = (
        (
            await db.execute(
                select(AftercareEntry)
                .where(AftercareEntry.user_id == user.id)
                .order_by(AftercareEntry.entry_date.desc())
            )
        )
        .scalars()
        .all()
    )
    return {
        "total": len(rows),
        "entries": [_entry_json(e) for e in rows[:100]],
        "kinds": {k: sum(1 for r in rows if r.kind == k) for k in AFTERCARE_KINDS},
    }


class AftercareBody(BaseModel):
    entry_date: date | None = None
    journal_entry_id: uuid.UUID | None = None
    timer_session_id: uuid.UUID | None = None
    kind: str
    comfort_level: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = None


@json_router.post("/entries", status_code=201)
async def json_add_entry(
    body: AftercareBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if body.kind not in AFTERCARE_KINDS:
        raise HTTPException(400, "Invalid kind")

    journal_id = body.journal_entry_id
    if journal_id is not None:
        own = (
            await db.execute(select(JournalEntry).where(JournalEntry.id == journal_id, JournalEntry.user_id == user.id))
        ).scalar_one_or_none()
        if own is None:
            raise HTTPException(400, "Journal entry not found")

    e = AftercareEntry(
        user_id=user.id,
        entry_date=body.entry_date or local_today(),
        journal_entry_id=journal_id,
        timer_session_id=body.timer_session_id,
        kind=body.kind,
        comfort_level=body.comfort_level,
        notes=(body.notes or "").strip() or None,
    )
    db.add(e)
    await db.flush()
    return _entry_json(e)


@json_router.delete("/entries/{entry_id}", status_code=204)
async def json_delete_entry(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    e = (
        await db.execute(select(AftercareEntry).where(AftercareEntry.id == entry_id, AftercareEntry.user_id == user.id))
    ).scalar_one_or_none()
    if e is None:
        raise HTTPException(404, "Aftercare entry not found")
    await db.delete(e)
    await db.flush()
    return None
