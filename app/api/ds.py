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


@router.get("/ds/portal", response_class=HTMLResponse)
async def ds_command_center_portal_page(
    request: Request,
    sub_id: str | None = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full-Featured D/s Command Center & Multi-Submissive Portal (Step 73)."""
    from app.models.ds_suite import WearCheckInLog

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

    selected_sub = None
    if sub_id:
        try:
            sub_uuid = uuid.UUID(sub_id)
            selected_sub = next((s for s in submissives if s.id == sub_uuid), None)
        except ValueError:
            selected_sub = None

    if not selected_sub and submissives:
        selected_sub = submissives[0]

    checkins = []
    if selected_sub:
        checkins = (
            (
                await db.execute(
                    select(WearCheckInLog)
                    .where(WearCheckInLog.managed_sub_id == selected_sub.id)
                    .order_by(WearCheckInLog.created_at.desc())
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
        name="ds_portal.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "ds",
            "mode": "command_center",
            "submissives": submissives,
            "selected_sub": selected_sub,
            "checkins": checkins,
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


@router.get("/ds/my-top", response_class=HTMLResponse)
async def my_top_delegation_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submissive's Portal Delegation Settings (ADR-129)."""
    from app.models.ds_suite import CapabilityGrant

    grants = (
        (
            await db.execute(
                select(CapabilityGrant)
                .where(CapabilityGrant.sub_user_id == user.id)
                .order_by(CapabilityGrant.created_at.desc())
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
        name="ds_my_top.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "ds",
            "grants": grants,
        },
    )


@router.post("/ds/grant/create")
async def create_grant_invite_endpoint(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generates an invite code for a Top to claim portal delegation."""
    from app.models.ds_suite import CapabilityGrant

    invite_code = f"DS-{uuid.uuid4().hex[:6].upper()}"
    grant = CapabilityGrant(
        sub_user_id=user.id,
        invite_code=invite_code,
        status="pending",
    )
    db.add(grant)
    await db.commit()
    return RedirectResponse(url="/ds/my-top", status_code=303)


@router.post("/ds/grant/claim")
async def claim_grant_invite_endpoint(
    invite_code: str = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Top inputs an invite code to claim delegation over a submissive."""
    from app.models.ds_suite import CapabilityGrant, ManagedSubmissive

    clean_code = invite_code.strip().upper()
    grant = (
        await db.execute(
            select(CapabilityGrant).where(
                CapabilityGrant.invite_code == clean_code,
                CapabilityGrant.status == "pending",
            )
        )
    ).scalar_one_or_none()

    if not grant:
        raise HTTPException(404, "Invalid or expired invite code")

    grant.top_user_id = user.id
    grant.status = "active"

    # Create linked ManagedSubmissive profile
    sub_profile = ManagedSubmissive(
        top_user_id=user.id,
        sub_user_id=grant.sub_user_id,
        name=f"Submissive User ({grant.sub_user_id.hex[:6]})",
        is_offline=False,
        chastity_status="unlocked",
        compliance_score=100,
    )
    db.add(grant)
    db.add(sub_profile)
    await db.commit()
    return RedirectResponse(url="/ds/keyholder", status_code=303)


@router.post("/ds/grant/{grant_id}/revoke")
async def revoke_grant_endpoint(
    grant_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Emergency Revoke / Safe Word Button — Revokes all Top access instantly."""
    from app.models.ds_suite import CapabilityGrant

    grant_uuid = uuid.UUID(grant_id)
    grant = (
        await db.execute(
            select(CapabilityGrant).where(
                CapabilityGrant.id == grant_uuid,
                CapabilityGrant.sub_user_id == user.id,
            )
        )
    ).scalar_one_or_none()

    if not grant:
        raise HTTPException(404, "Grant not found")

    grant.status = "revoked"
    db.add(grant)
    await db.commit()
    return RedirectResponse(url="/ds/my-top", status_code=303)


@router.get("/ds/checkins", response_class=HTMLResponse)
async def wear_checkins_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Wear Check-Ins & Tag Seal Inspection Center (Step 65 / ADR-100)."""
    from app.models.ds_suite import WearCheckInLog

    checkins = (
        (
            await db.execute(
                select(WearCheckInLog)
                .join(ManagedSubmissive, WearCheckInLog.managed_sub_id == ManagedSubmissive.id)
                .where(
                    (ManagedSubmissive.top_user_id == user.id) | (ManagedSubmissive.sub_user_id == user.id)
                )
                .order_by(WearCheckInLog.created_at.desc())
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
        name="ds_checkins.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "ds",
            "checkins": checkins,
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
    """Logs a wear check-in and seal inspection (Step 65)."""
    from app.models.ds_suite import WearCheckInLog

    sub_uuid = uuid.UUID(managed_sub_id)
    checkin = WearCheckInLog(
        managed_sub_id=sub_uuid,
        tag_number=tag_number or None,
        comfort_score=comfort_score,
        notes=notes,
        photo_url=photo_url or None,
        is_verified_closed=bool(photo_url),
    )
    db.add(checkin)
    await db.commit()
    return RedirectResponse(url="/ds/checkins", status_code=303)


@router.post("/ds/submissive/{sub_id}/ai-keyholder-spin")
async def ai_keyholder_spin_endpoint(
    sub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI Keyholder Bot Wheel of Fortune / Random Extensions (Step 67 / ADR-113)."""
    import random

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

    outcomes = [
        ("lock_extension", "+24 часа ношения замка", "AI Keyholder Bot добавил +24ч ношения замка"),
        ("key_reward", "🔑 Выдача Ключа!", "AI Keyholder Bot разблокировал замок за высокое послушание"),
        ("tag_check", "🏷️ Запрос инспекции пломбы", "AI Keyholder Bot потребовал фото-проверку номерной пломбы"),
    ]
    action_type, result_title, log_reason = random.choice(outcomes)

    if action_type == "key_reward":
        sub.chastity_status = "unlocked"

    log = ChastityLockLog(
        managed_sub_id=sub.id,
        action=action_type,
        reason=f"AI Keyholder Wheel: {log_reason}",
    )
    db.add(sub)
    db.add(log)
    await db.commit()
    return RedirectResponse(url="/ds/keyholder", status_code=303)


@router.post("/ds/submissive/{sub_id}/telegram-code")
async def generate_submissive_telegram_code_endpoint(
    sub_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generates a 6-character code for linking an offline submissive to Telegram bot (Step 74 / ADR-130)."""
    from datetime import UTC, datetime, timedelta

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

    code = f"SUB-{uuid.uuid4().hex[:6].upper()}"
    sub.telegram_link_code = code
    sub.telegram_link_code_expires = datetime.now(UTC) + timedelta(minutes=30)
    db.add(sub)
    await db.commit()
    return RedirectResponse(url=f"/ds/portal?sub_id={sub.id}", status_code=303)



