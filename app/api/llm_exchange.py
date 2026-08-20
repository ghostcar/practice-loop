"""API Router for External Model Exchange Hub ("Внешняя ИИ-модель").

Provides prompt exporter, response parser, reference matcher, and entity hydration.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.gamification.handler import get_or_create_progress
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.llm.pipeline.exchange import (
    build_exportable_cross_domain_prompt,
    get_user_reference_catalogs,
    parse_external_llm_response,
)
from app.models.activity_log import ActivityLog
from app.models.session import ActivitySession
from app.models.session_history import ActivitySessionHistory
from app.models.user import User
from app.templates_setup import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["llm_exchange"])


@router.get("/llm/exchange", response_class=HTMLResponse)
async def llm_exchange_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """External Model Exchange Hub Page."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    references = await get_user_reference_catalogs(db, user.id)

    return templates.TemplateResponse(
        request=request,
        name="llm_exchange.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "llm",
            "references": references,
        },
    )


@router.post("/llm/exchange/export")
async def export_prompt_endpoint(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generates compiled cross-domain prompt text for clipboard copy."""
    form = await request.form()
    domains = form.getlist("domains")
    if not domains:
        domains = ["tracker"]

    prompt = await build_exportable_cross_domain_prompt(db, user.id, domains=domains, locale=user.locale)
    return JSONResponse({"status": "ok", "prompt": prompt})


@router.post("/llm/exchange/parse")
async def parse_response_endpoint(
    raw_response: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Parses raw pasted LLM text using json_repair and returns structured items for UI matching."""
    if not raw_response.strip():
        raise HTTPException(400, "Raw response text cannot be empty")

    try:
        parsed = parse_external_llm_response(raw_response)
    except Exception as err:
        raise HTTPException(400, f"Failed to parse LLM response: {err}") from None

    references = await get_user_reference_catalogs(db, user.id)
    return JSONResponse({"status": "ok", "parsed": parsed, "references": references})


@router.post("/llm/exchange/confirm")
async def confirm_hydrated_plan_endpoint(
    title: str = Form("Сквозной план от Внешней ИИ"),
    reasoning: str = Form(""),
    items_json: str = Form("[]"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Hydrates confirmed matched items into database ActivitySession and ActivityLogs."""
    import json

    try:
        items = json.loads(items_json)
    except Exception:
        items = []

    if not items:
        return RedirectResponse(url="/llm/exchange", status_code=303)

    # Create new ActivitySession
    sess = ActivitySession(
        owner_id=user.id,
        title=title.strip()[:200] or "Сквозной план от Внешней ИИ",
        notes=f"Обоснование Внешней ИИ: {reasoning.strip()}",
        status="created",
    )
    db.add(sess)
    await db.flush()

    db.add(ActivitySessionHistory(session_id=sess.id, actor_id=user.id, event_type="created"))

    # Hydrate individual items as ActivityLogs
    for item in items:
        item_title = item.get("title", "Активность от Внешней ИИ").strip()
        log = ActivityLog(
            session_id=sess.id,
            user_id=user.id,
            selected_entity_name=item_title,
            cleaned_response={"item": item, "source": "external_model"},
            user_prompt=f"External LLM generation: {item_title}",
        )
        db.add(log)

    # Award Social XP
    prog = await get_or_create_progress(db, user.id)
    prog.xp += 30

    return RedirectResponse(url="/sessions", status_code=303)
