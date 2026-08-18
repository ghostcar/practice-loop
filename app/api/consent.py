"""Consent records API (C3 — согласия на чувствительную обработку).

Журнал явных согласий (granted/revoked): расширенный LLM-режим, фото-
верификация, обработка данных. **Relief-only** (PD-013). Каждое изменение —
новая запись-версия (история переходов), не перезаписывается.

Страницы:
- GET  /consent                  — форма + история согласий
- POST /consent                  — создать/изменить согласие → redirect

JSON API (мобильный/bearer):
- GET    /api/v2/consent         — список (фильтр по consent_type/state)
- POST   /api/v2/consent         — grant/revoke (201)
История неизменяема: отзыв оформляется новой записью, DELETE отсутствует.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.consent import PURPOSES, missing_consents, record_consent
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.consent import CONSENT_STATES, ConsentRecord
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(tags=["consent"])
json_router = APIRouter(prefix="/api/v2/consent", tags=["consent"])


def _record_json(r: ConsentRecord) -> dict:
    return {
        "id": str(r.id),
        "consent_type": r.consent_type,
        "state": r.state,
        "scope": r.scope,
        "version": r.version,
        "terms_version": r.terms_version,
        "granted_at": r.granted_at.isoformat() if r.granted_at else None,
        "revoked_at": r.revoked_at.isoformat() if r.revoked_at else None,
        "notes": r.notes,
    }


async def _latest_consents(db: AsyncSession, user_id: uuid.UUID) -> dict[str, dict]:
    """Latest granted/revoked record per consent_type (for settings/UI display)."""
    rows = (
        (
            await db.execute(
                select(ConsentRecord).where(ConsentRecord.user_id == user_id).order_by(ConsentRecord.version.desc())
            )
        )
        .scalars()
        .all()
    )
    latest: dict[str, dict] = {}
    for r in rows:
        if r.consent_type not in latest:
            latest[r.consent_type] = _record_json(r)
    return latest


# ─────────────────────────────────────────────────────────────────────────────
# Page + form handlers (HTMX)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/consent", response_class=HTMLResponse)
async def consent_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    records = (
        (
            await db.execute(
                select(ConsentRecord)
                .where(ConsentRecord.user_id == user.id)
                .order_by(ConsentRecord.consent_type.asc(), ConsentRecord.version.desc())
            )
        )
        .scalars()
        .all()
    )

    return templates.TemplateResponse(
        request,
        "consent.html",
        {
            "t": t,
            "user": user,
            "theme": theme,
            "nav_key": "consent",
            "records": [_record_json(r) for r in records],
            "latest": await _latest_consents(db, user.id),
            "consent_types": tuple(PURPOSES),
            "states": CONSENT_STATES,
        },
    )


@router.post("/consent")
async def add_consent_form(
    request: Request,
    consent_type: str = Form(...),
    state: str = Form(...),
    scope: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await record_consent(db, user, consent_type, state, scope=scope, notes=notes)
    return RedirectResponse(url="/consent", status_code=303)


@router.get("/consent/setup", response_class=HTMLResponse)
async def consent_setup_page(
    request: Request,
    required: str = Query(default=""),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    keys = [key for key in required.split(",") if key] or [key for key, item in PURPOSES.items() if item.module]
    keys = [key for key in keys if key in PURPOSES]
    return templates.TemplateResponse(
        request,
        "consent_setup.html",
        {
            "t": get_translations(detect_locale(request, user.locale)),
            "user": user,
            "theme": detect_theme(user.theme),
            "nav_key": "consent",
            "required": await missing_consents(db, user.id, keys),
        },
    )


@router.post("/consent/setup")
async def consent_setup_submit(
    consent_types: list[str] = Form(default=[]),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    for key in consent_types:
        await record_consent(db, user, key, "granted", scope="portal_lifetime")
    from app.prefs import sanitize_prefs

    still_missing = await missing_consents(
        db,
        user.id,
        [f"module:{name}" for name in sanitize_prefs(user.prefs)["enabled_modules"]],
    )
    if still_missing:
        return RedirectResponse(url="/consent/setup?required=" + ",".join(still_missing), status_code=303)
    return RedirectResponse(url="/dashboard", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────


@json_router.get("")
async def json_list(
    consent_type: str | None = Query(None),
    state: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(ConsentRecord).where(ConsentRecord.user_id == user.id)
    if consent_type is not None:
        query = query.where(ConsentRecord.consent_type == consent_type)
    if state is not None:
        query = query.where(ConsentRecord.state == state)
    rows = (await db.execute(query.order_by(ConsentRecord.version.desc()))).scalars().all()
    return {"records": [_record_json(r) for r in rows], "latest": await _latest_consents(db, user.id)}


class ConsentBody(BaseModel):
    consent_type: str
    state: str
    scope: str | None = None
    notes: str | None = None


@json_router.post("", status_code=201)
async def json_add(
    body: ConsentBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = await record_consent(db, user, body.consent_type, body.state, scope=body.scope, notes=body.notes)
    return _record_json(r)
