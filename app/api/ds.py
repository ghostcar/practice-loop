"""D/s Suite & Keyholder Management API (Step 63 / ADR-128).

All business logic lives in app.services.ds_service (ADR-171).
This file contains only HTTP parsing, response building, and dependency injection.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.user import User
from app.services import ds_service as svc
from app.services.errors import NotFoundError
from app.templates_setup import templates
from app.tier_guard import require_feature

router = APIRouter(tags=["ds"])


# ─────────────────────────────────────────────────────────────────────────────
# Keyholder dashboard
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/ds/keyholder", response_class=HTMLResponse)
async def keyholder_dashboard_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_keyholder_context(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="ds_keyholder.html",
        context={
            "request": request, "t": t, "user": user, "locale": locale,
            "theme": theme, "active_nav": "ds", **ctx,
        },
    )


@router.get("/ds/portal", response_class=HTMLResponse)
async def ds_command_center_portal_page(
    request: Request,
    sub_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    _access: None = Depends(require_feature("ds_portal")),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_portal_context(db, user.id, sub_id)
    return templates.TemplateResponse(
        request=request,
        name="ds_portal.html",
        context={
            "request": request, "t": t, "user": user, "locale": locale,
            "theme": theme, "active_nav": "ds_portal", **ctx,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Submissive CRUD
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/ds/submissive/create")
async def create_managed_submissive_endpoint(
    name: str = Form(...),
    is_offline: bool = Form(True),
    rules_notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.create_submissive(db, user.id, name=name, is_offline=is_offline, rules_notes=rules_notes)
    return RedirectResponse(url="/ds/keyholder", status_code=303)


@router.post("/ds/submissive/{sub_id}/lock-action")
async def lock_action_endpoint(
    sub_id: str,
    action: str = Form(...),
    reason: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.lock_action(db, sub_id, user.id, action=action, reason=reason)
    except NotFoundError:
        raise HTTPException(404, "Submissive profile not found") from None
    return RedirectResponse(url="/ds/keyholder", status_code=303)


@router.post("/ds/duties/assign")
async def assign_duty_endpoint(
    managed_sub_id: str = Form(...),
    title: str = Form(...),
    description: str = Form(""),
    reward_penalty_xp: int = Form(50),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.assign_duty(
            db, user.id, managed_sub_id=managed_sub_id, title=title,
            description=description, reward_penalty_xp=reward_penalty_xp,
        )
    except NotFoundError:
        raise HTTPException(404, "Submissive profile not found") from None
    return RedirectResponse(url="/ds/keyholder", status_code=303)


@router.post("/ds/duties/{duty_id}/verify")
async def verify_duty_endpoint(
    duty_id: str,
    action: str = Form(...),
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.verify_duty(db, duty_id, user.id, action=action, notes=notes)
    except NotFoundError:
        raise HTTPException(404, "Assigned duty not found") from None
    return RedirectResponse(url="/ds/keyholder", status_code=303)


@router.post("/ds/submissive/{sub_id}/ai-keyholder-spin")
async def ai_keyholder_spin_endpoint(
    sub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.ai_keyholder_spin(db, sub_id, user.id)
    except NotFoundError:
        raise HTTPException(404, "Submissive profile not found") from None
    return RedirectResponse(url="/ds/keyholder", status_code=303)


@router.post("/ds/submissive/{sub_id}/telegram-code")
async def generate_submissive_telegram_code_endpoint(
    sub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        code = await svc.generate_sub_tg_code(db, sub_id, user.id)
    except NotFoundError:
        raise HTTPException(404, "Submissive profile not found") from None
    return RedirectResponse(url=f"/ds/portal?sub_id={sub_id}", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# Delegation (My Top)
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/ds/my-top", response_class=HTMLResponse)
async def my_top_delegation_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_delegation_context(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="ds_my_top.html",
        context={
            "request": request, "t": t, "user": user, "locale": locale,
            "theme": theme, "active_nav": "ds", **ctx,
        },
    )


@router.post("/ds/grant/create")
async def create_grant_invite_endpoint(
    scope_chastity: bool = Form(default=False),
    scope_tasks: bool = Form(default=False),
    scope_training: bool = Form(default=False),
    scope_medication: bool = Form(default=False),
    scope_aftercare: bool = Form(default=False),
    scope_inventory: bool = Form(default=False),
    scope_health_view: bool = Form(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    selected_scopes = {
        "scope_chastity": scope_chastity,
        "scope_tasks": scope_tasks,
        "scope_training": scope_training,
        "scope_medication": scope_medication,
        "scope_aftercare": scope_aftercare,
        "scope_inventory": scope_inventory,
        "scope_health_view": scope_health_view,
    }
    try:
        await svc.create_grant_invite(db, user.id, selected_scopes=selected_scopes)
    except ValueError as e:
        raise HTTPException(400, str(e)) from None
    return RedirectResponse(url="/ds/my-top", status_code=303)


@router.post("/ds/grant/claim")
async def claim_grant_invite_endpoint(
    invite_code: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await svc.claim_grant_invite(db, user.id, invite_code)
    if result == "rate_limited":
        return PlainTextResponse("Too many invite claim attempts", status_code=429)
    elif result == "invalid":
        return PlainTextResponse("Invalid or expired invite code", status_code=404)
    elif result == "self_claim":
        raise HTTPException(400, "Cannot claim self-delegation grant") from None
    return RedirectResponse(url="/ds/keyholder", status_code=303)


@router.post("/ds/grant/{grant_id}/revoke")
async def revoke_grant_endpoint(
    grant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await svc.revoke_grant(db, grant_id, user.id)
    except NotFoundError:
        raise HTTPException(404, "Grant not found") from None
    return RedirectResponse(url="/ds/my-top", status_code=303)


# ─────────────────────────────────────────────────────────────────────────────
# Check-ins
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/ds/checkins", response_class=HTMLResponse)
async def wear_checkins_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    ctx = await svc.get_checkins_context(db, user.id)
    return templates.TemplateResponse(
        request=request,
        name="ds_checkins.html",
        context={
            "request": request, "t": t, "user": user, "locale": locale,
            "theme": theme, "active_nav": "ds", **ctx,
        },
    )


@router.post("/ds/checkins/log")
async def log_wear_checkin_endpoint(
    managed_sub_id: str = Form(...),
    tag_number: str = Form(""),
    comfort_score: int = Form(5),
    notes: str = Form(""),
    photo_url: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await svc.log_wear_checkin(
        db, user.id, managed_sub_id=managed_sub_id, tag_number=tag_number,
        comfort_score=comfort_score, notes=notes, photo_url=photo_url,
    )
    return RedirectResponse(url="/ds/checkins", status_code=303)


@router.post("/api/v2/ds/checkins/ocr-verify")
async def ocr_verify_seal_endpoint(
    tag_number: str = Form(""),
    user: User = Depends(get_current_user),
):
    result = svc.ocr_verify_seal(tag_number)
    return JSONResponse({"status": "success", **result})
