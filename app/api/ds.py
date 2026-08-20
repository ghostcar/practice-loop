"""D/s Suite & Keyholder Management API (Step 63 / ADR-128)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.ds_suite import AssignedDuty, ChastityLockLog, ManagedSubmissive
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(tags=["ds"])


@router.get("/ds/keyholder", response_class=HTMLResponse)
async def keyholder_dashboard_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Keyholder Dashboard — Manage registered and offline submissives."""
    submissives = (
        (
            await db.execute(
                select(ManagedSubmissive)
                .where(ManagedSubmissive.top_user_id == user.id)
                .options(
                    selectinload(ManagedSubmissive.duties),
                    selectinload(ManagedSubmissive.lock_logs),
                )
                .order_by(ManagedSubmissive.created_at.desc())
            )
        )
        .scalars()
        .all()
    )

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="ds_keyholder.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "ds",
            "submissives": submissives,
        },
    )


@router.post("/ds/submissive/create")
async def create_managed_submissive_endpoint(
    name: str = Form(...),
    is_offline: bool = Form(True),
    rules_notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates a new managed submissive profile (offline or registered)."""
    sub_profile = ManagedSubmissive(
        top_user_id=user.id,
        name=name,
        is_offline=is_offline,
        rules_notes=rules_notes,
        chastity_status="unlocked",
        compliance_score=100,
    )
    db.add(sub_profile)
    await db.commit()
    return RedirectResponse(url="/ds/keyholder", status_code=303)


@router.post("/ds/submissive/{sub_id}/lock-action")
async def lock_action_endpoint(
    sub_id: str,
    action: str = Form(...),  # lock, unlock, key_check, emergency_unlock
    reason: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Executes a keyholder lock action for a submissive."""
    sub_uuid = uuid.UUID(sub_id)
    sub = (
        await db.execute(
            select(ManagedSubmissive).where(
                ManagedSubmissive.id == sub_uuid,
                ManagedSubmissive.top_user_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if not sub:
        raise HTTPException(404, "Submissive profile not found")

    if action == "lock":
        sub.chastity_status = "locked"
    elif action == "unlock":
        sub.chastity_status = "unlocked"
    elif action == "key_check":
        sub.chastity_status = "keyholder_held"
    elif action == "emergency_unlock":
        sub.chastity_status = "emergency_released"

    log = ChastityLockLog(
        managed_sub_id=sub.id,
        action=action,
        reason=reason or f"Action {action} performed by Keyholder",
    )
    db.add(sub)
    db.add(log)
    await db.commit()
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
    """Assigns an order or duty to a managed submissive."""
    sub_uuid = uuid.UUID(managed_sub_id)
    sub = (
        await db.execute(
            select(ManagedSubmissive).where(
                ManagedSubmissive.id == sub_uuid,
                ManagedSubmissive.top_user_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if not sub:
        raise HTTPException(404, "Submissive profile not found")

    duty = AssignedDuty(
        managed_sub_id=sub.id,
        assigned_by_id=user.id,
        title=title,
        description=description,
        reward_penalty_xp=reward_penalty_xp,
        status="pending",
    )
    db.add(duty)
    await db.commit()
    return RedirectResponse(url="/ds/keyholder", status_code=303)


@router.post("/ds/duties/{duty_id}/verify")
async def verify_duty_endpoint(
    duty_id: str,
    action: str = Form(...),  # approve, reject
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Approves or rejects a submitted duty."""
    duty_uuid = uuid.UUID(duty_id)
    duty = (
        await db.execute(
            select(AssignedDuty).where(
                AssignedDuty.id == duty_uuid,
                AssignedDuty.assigned_by_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if not duty:
        raise HTTPException(404, "Assigned duty not found")

    if action == "approve":
        duty.status = "approved"
    else:
        duty.status = "rejected"

    duty.verification_notes = notes
    db.add(duty)
    await db.commit()
    return RedirectResponse(url="/ds/keyholder", status_code=303)
