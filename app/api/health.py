"""Health + Cycle foundation API — Thin HTTP routes.

All business logic lives in app.services.health_service (ADR-163).
This file contains only HTTP parsing, response building, and dependency injection.
"""

from __future__ import annotations

import json as _json
import logging
import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.services import health_service as svc
from app.services.errors import NotFoundError
from app.templates_setup import templates

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])
json_router = APIRouter(prefix="/api/v2/health", tags=["health"])


# ─────────────────────────────────────────────────────────────────────────────
# HTML Pages
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/health", response_class=HTMLResponse)
async def health_page(
    request: Request,
    analysis: str = "",
    error: str = "",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_health_page_context(db, user, analysis=analysis, error=error)
    return templates.TemplateResponse(
        request=request,
        name="health.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, **ctx},
    )


@router.get("/health/body-cycle", response_class=HTMLResponse)
async def health_body_cycle_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    logs = await svc.get_body_cycle_page_context(db, user)
    return templates.TemplateResponse(
        request=request,
        name="health_body_cycle.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "health",
            "logs": logs,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# HTML Form Handlers
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/health/state")
async def save_state(
    request: Request,
    event_date: str = Form(...),
    mood: str = Form(default=""),
    energy: str = Form(default=""),
    sleep_hours: str = Form(default=""),
    sleep_quality: str = Form(default=""),
    recovery: str = Form(default=""),
    skin_sensitivity: str = Form(default=""),
    post_session_drop: str = Form(default=""),
    hrt_taken: str = Form(default=""),
    symptoms: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.save_health_state(
            db, user_id=user.id, event_date=event_date, mood=mood, energy=energy,
            sleep_hours=sleep_hours, sleep_quality=sleep_quality, recovery=recovery,
            skin_sensitivity=skin_sensitivity, post_session_drop=post_session_drop,
            hrt_taken=hrt_taken, symptoms=symptoms, notes=notes,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/health", status_code=303)


@router.post("/health/analyze")
async def analyze_labs_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.llm.pipeline import get_active_llm_config
    from app.prefs import get_prefs

    llm_config = await get_active_llm_config(db, user.id)
    if llm_config is None:
        return RedirectResponse(url="/health?error=no_llm_config", status_code=303)
    locale = detect_locale(request, user.locale)
    mode = get_prefs().llm_mode
    try:
        result = await svc.analyze_labs_async(db, user.id, llm_config, locale=locale, llm_mode=mode)
    except Exception as exc:
        logger.warning("health analyze failed: %s", exc)
        return RedirectResponse(url="/health?error=analyze_failed", status_code=303)
    encoded = _json.dumps(result, ensure_ascii=False)
    return RedirectResponse(url=f"/health?analysis={encoded}", status_code=303)


@router.post("/health/labs")
async def add_lab(
    request: Request,
    name: str = Form(...),
    measured_at: str = Form(...),
    value: str = Form(...),
    unit: str = Form(default=""),
    ref_range: str = Form(default=""),
    lab_name: str = Form(default=""),
    flagged: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.add_lab(
            db, user_id=user.id, name=name, measured_at=measured_at, value=value,
            unit=unit, ref_range=ref_range, lab_name=lab_name, flagged=flagged, notes=notes,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/health", status_code=303)


@router.post("/health/labs/{lab_id}/delete")
async def delete_lab(
    request: Request,
    lab_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_lab(db, user.id, lab_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/health", status_code=303)


@router.post("/health/cycle/settings")
async def save_cycle_settings(
    request: Request,
    cycle_length: str = Form(default="28"),
    period_length: str = Form(default="5"),
    contraception: str = Form(default="none"),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.save_cycle_settings(
            db, user_id=user.id, cycle_length=cycle_length, period_length=period_length,
            contraception=contraception, notes=notes,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/health", status_code=303)


@router.post("/health/cycle/events")
async def add_cycle_event(
    request: Request,
    event_date: str = Form(...),
    event_type: str = Form(...),
    value: str = Form(default=""),
    notes: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.add_cycle_event(
            db, user_id=user.id, event_date=event_date, event_type=event_type,
            value=value, notes=notes,
        )
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/health", status_code=303)


@router.post("/health/cycle/events/{event_id}/delete")
async def delete_cycle_event(
    request: Request,
    event_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.delete_cycle_event(db, user.id, event_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return RedirectResponse(url="/health", status_code=303)


@router.post("/health/body-cycle/log")
async def log_body_cycle_endpoint(
    request: Request,
    cycle_phase: str = Form("neutral"),
    energy_level: int = Form(3),
    soreness_level: int = Form(1),
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.log_body_cycle(
        db, user_id=user.id, cycle_phase=cycle_phase,
        energy_level=energy_level, soreness_level=soreness_level, notes=notes,
    )
    return RedirectResponse(url="/health/body-cycle", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# JSON API (mobile / bearer)
# ─────────────────────────────────────────────────────────────────────────────


@json_router.get("")
async def json_summary(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_health_summary(db, user.id)


@json_router.get("/states")
async def json_states(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_list_states(db, user.id)


@json_router.get("/labs")
async def json_labs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_list_labs(db, user.id)


@json_router.get("/cycle")
async def json_cycle(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_cycle(db, user.id)


@json_router.post("/state", status_code=201)
async def json_save_state(
    body: svc.StateBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_save_state(db, user.id, body)


@json_router.post("/labs", status_code=201)
async def json_add_lab(
    body: svc.LabBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await svc.json_add_lab(db, user.id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@json_router.delete("/labs/{lab_id}", status_code=204)
async def json_delete_lab(
    lab_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.json_delete_lab(db, user.id, lab_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return None


@json_router.post("/cycle/events", status_code=201)
async def json_add_cycle_event(
    body: svc.CycleEventBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        return await svc.json_add_cycle_event(db, user.id, body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None


@json_router.delete("/cycle/events/{event_id}", status_code=204)
async def json_delete_cycle_event(
    event_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        await svc.json_delete_cycle_event(db, user.id, event_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e)) from None
    return None


@json_router.post("/cycle/settings", status_code=201)
async def json_save_cycle_settings(
    body: svc.CycleSettingsBody,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await svc.json_save_cycle_settings(db, user.id, body)


@json_router.post("/analyze")
async def json_analyze_labs(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.llm.pipeline import get_active_llm_config
    from app.prefs import get_prefs

    llm_config = await get_active_llm_config(db, user.id)
    if llm_config is None:
        raise HTTPException(400, "No active LLM config — configure one in /llm-configs")
    locale = detect_locale(request, user.locale)
    mode = get_prefs().llm_mode
    try:
        result = await svc.analyze_labs_async(db, user.id, llm_config, locale=locale, llm_mode=mode)
    except Exception as exc:
        logger.warning("health analyze (json) failed: %s", exc)
        raise HTTPException(502, "LLM analysis failed — retry") from exc
    return {
        "summary": result.get("summary", ""),
        "observations": result.get("observations", []),
        "assumptions": result.get("assumptions", []),
        "questions_for_doctor": result.get("questions_for_doctor", []),
        "recommendations": result.get("recommendations", []),
        "mode": result.get("_mode", mode),
    }


# Re-export helpers that other modules import from health.py
from app.services.health_service import cycle_phase as _cycle_phase  # noqa: E402, F401
from app.services.health_service import day_of_cycle as _day_of_cycle  # noqa: E402, F401
from app.services.health_service import get_cycle_context as _get_cycle_context  # noqa: E402, F401
from app.services.health_service import health_summary as _health_summary  # noqa: E402, F401
