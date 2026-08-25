"""D/s Suite & Keyholder Management service.

Extracted from app/api/ds.py (ADR-171).  HTTP layer stays thin.
"""

from __future__ import annotations

import random
import uuid
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ds_suite import (
    AssignedDuty,
    CapabilityGrant,
    CapabilityGrantClaimAttempt,
    ChastityLockLog,
    ManagedSubmissive,
    WearCheckInLog,
)
from app.services.dead_mans_switch import record_activity_heartbeat
from app.services.errors import NotFoundError

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def _get_owned_submissive(db: AsyncSession, sub_id: str, user_id: uuid.UUID) -> ManagedSubmissive:
    """Get a submissive owned by the user, or raise NotFoundError."""
    sub_uuid = uuid.UUID(sub_id)
    sub = (
        await db.execute(
            select(ManagedSubmissive).where(
                ManagedSubmissive.id == sub_uuid,
                ManagedSubmissive.top_user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if not sub:
        raise NotFoundError("Submissive profile not found")
    return sub


# ─────────────────────────────────────────────────────────────────────────────
# Keyholder dashboard context
# ─────────────────────────────────────────────────────────────────────────────


async def get_keyholder_context(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Load submissives list for keyholder dashboard."""
    submissives = list(
        (
            await db.execute(
                select(ManagedSubmissive)
                .where(ManagedSubmissive.top_user_id == user_id)
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
    return {"submissives": submissives}


# ─────────────────────────────────────────────────────────────────────────────
# Portal context
# ─────────────────────────────────────────────────────────────────────────────


async def get_portal_context(db: AsyncSession, user_id: uuid.UUID, sub_id: str | None = None) -> dict:
    """Load portal context: submissives, selected sub, checkins, cohort analytics."""
    submissives = list(
        (
            await db.execute(
                select(ManagedSubmissive)
                .where(ManagedSubmissive.top_user_id == user_id)
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
        checkins = list(
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

    from app.analytics.engine import aggregate_keyholder_cohort_analytics
    cohort_analytics = await aggregate_keyholder_cohort_analytics(db, user_id)

    return {
        "submissives": submissives,
        "selected_sub": selected_sub,
        "checkins": checkins,
        "cohort_analytics": cohort_analytics,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Submissive CRUD
# ─────────────────────────────────────────────────────────────────────────────


async def create_submissive(
    db: AsyncSession, user_id: uuid.UUID, *, name: str, is_offline: bool, rules_notes: str,
) -> ManagedSubmissive:
    sub_profile = ManagedSubmissive(
        top_user_id=user_id,
        name=name,
        is_offline=is_offline,
        rules_notes=rules_notes,
        chastity_status="unlocked",
        compliance_score=100,
    )
    db.add(sub_profile)
    await db.flush()
    return sub_profile


async def lock_action(db: AsyncSession, sub_id: str, user_id: uuid.UUID, *, action: str, reason: str) -> None:
    """Execute a keyholder lock action."""
    sub = await _get_owned_submissive(db, sub_id, user_id)

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
    await db.flush()


async def assign_duty(
    db: AsyncSession, user_id: uuid.UUID, *, managed_sub_id: str, title: str,
    description: str, reward_penalty_xp: int,
) -> None:
    """Assign a duty to a submissive."""
    sub = await _get_owned_submissive(db, managed_sub_id, user_id)

    duty = AssignedDuty(
        managed_sub_id=sub.id,
        assigned_by_id=user_id,
        title=title,
        description=description,
        reward_penalty_xp=reward_penalty_xp,
        status="pending",
    )
    db.add(duty)
    await db.flush()


async def verify_duty(db: AsyncSession, duty_id: str, user_id: uuid.UUID, *, action: str, notes: str) -> None:
    """Approve or reject a duty."""
    duty_uuid = uuid.UUID(duty_id)
    duty = (
        await db.execute(
            select(AssignedDuty).where(AssignedDuty.id == duty_uuid, AssignedDuty.assigned_by_id == user_id)
        )
    ).scalar_one_or_none()
    if not duty:
        raise NotFoundError("Assigned duty not found")

    duty.status = "approved" if action == "approve" else "rejected"
    duty.verification_notes = notes
    db.add(duty)
    await db.flush()


async def ai_keyholder_spin(db: AsyncSession, sub_id: str, user_id: uuid.UUID) -> dict:
    """AI Keyholder random wheel spin. Returns result dict."""
    sub = await _get_owned_submissive(db, sub_id, user_id)

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
    await db.flush()
    return {"action_type": action_type, "result_title": result_title}


# ─────────────────────────────────────────────────────────────────────────────
# Delegation (My Top)
# ─────────────────────────────────────────────────────────────────────────────


async def get_delegation_context(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Load grants for delegation page."""
    grants = list(
        (
            await db.execute(
                select(CapabilityGrant)
                .where(CapabilityGrant.sub_user_id == user_id)
                .order_by(CapabilityGrant.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {"grants": grants}


async def create_grant_invite(
    db: AsyncSession, user_id: uuid.UUID, *, selected_scopes: dict[str, bool],
) -> None:
    """Generate an invite code for a Top to claim delegation."""
    if not any(selected_scopes.values()):
        raise ValueError("Select at least one delegated capability")

    invite_code = f"DS-{uuid.uuid4().hex[:12].upper()}"
    grant = CapabilityGrant(
        sub_user_id=user_id,
        invite_code=invite_code,
        status="pending",
        expires_at=datetime.now(UTC) + timedelta(hours=24),
        **selected_scopes,
    )
    db.add(grant)
    await db.flush()


async def claim_grant_invite(db: AsyncSession, user_id: uuid.UUID, invite_code: str) -> str:
    """Top claims delegation. Returns 'success', 'rate_limited', 'invalid', 'self_claim'."""
    clean_code = invite_code.strip().upper()

    # Rate limit: 10 attempts per 15 min
    window_start = datetime.now(UTC) - timedelta(minutes=15)
    recent_attempts = await db.scalar(
        select(func.count())
        .select_from(CapabilityGrantClaimAttempt)
        .where(
            CapabilityGrantClaimAttempt.actor_id == user_id,
            CapabilityGrantClaimAttempt.created_at >= window_start,
        )
    )
    if (recent_attempts or 0) >= 10:
        return "rate_limited"

    attempt = CapabilityGrantClaimAttempt(
        actor_id=user_id,
        invite_code_hash=sha256(clean_code.encode("utf-8")).hexdigest(),
        succeeded=False,
    )
    db.add(attempt)

    grant = (
        await db.execute(
            select(CapabilityGrant)
            .where(
                CapabilityGrant.invite_code == clean_code,
                CapabilityGrant.status == "pending",
                CapabilityGrant.expires_at > datetime.now(UTC),
            )
            .with_for_update()
        )
    ).scalar_one_or_none()

    if not grant:
        await db.flush()
        return "invalid"

    if grant.sub_user_id == user_id:
        await db.flush()
        return "self_claim"

    grant.top_user_id = user_id
    grant.status = "active"
    attempt.succeeded = True

    # Create ManagedSubmissive link if not exists
    existing_sub = (
        await db.execute(
            select(ManagedSubmissive).where(
                ManagedSubmissive.top_user_id == user_id,
                ManagedSubmissive.sub_user_id == grant.sub_user_id,
            )
        )
    ).scalar_one_or_none()

    if not existing_sub:
        sub_profile = ManagedSubmissive(
            top_user_id=user_id,
            sub_user_id=grant.sub_user_id,
            name=f"Submissive User ({grant.sub_user_id.hex[:6]})",
            is_offline=False,
            chastity_status="unlocked",
            compliance_score=100,
        )
        db.add(sub_profile)

    await db.flush()
    return "success"


async def revoke_grant(db: AsyncSession, grant_id: str, user_id: uuid.UUID) -> None:
    """Emergency revoke delegation."""
    grant_uuid = uuid.UUID(grant_id)
    grant = (
        await db.execute(
            select(CapabilityGrant).where(
                CapabilityGrant.id == grant_uuid,
                CapabilityGrant.sub_user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if not grant:
        raise NotFoundError("Grant not found")

    grant.status = "revoked"
    db.add(grant)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Check-ins
# ─────────────────────────────────────────────────────────────────────────────


async def get_checkins_context(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Load wear check-ins for the user."""
    checkins = list(
        (
            await db.execute(
                select(WearCheckInLog)
                .join(ManagedSubmissive, WearCheckInLog.managed_sub_id == ManagedSubmissive.id)
                .where((ManagedSubmissive.top_user_id == user_id) | (ManagedSubmissive.sub_user_id == user_id))
                .order_by(WearCheckInLog.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {"checkins": checkins}


async def log_wear_checkin(
    db: AsyncSession, user_id: uuid.UUID, *,
    managed_sub_id: str, tag_number: str, comfort_score: int, notes: str, photo_url: str,
) -> None:
    """Log a wear check-in with optional OCR seal inspection."""
    from app.media.ocr_seals import extract_seal_tag_from_photo

    sub_uuid = uuid.UUID(managed_sub_id)
    is_verified = bool(photo_url)

    if photo_url:
        ocr_res = extract_seal_tag_from_photo(b"SAMPLE_TAG_PHOTO_BYTES", expected_tag=tag_number)
        if ocr_res.get("is_match"):
            is_verified = True

    checkin = WearCheckInLog(
        managed_sub_id=sub_uuid,
        tag_number=tag_number or None,
        comfort_score=comfort_score,
        notes=notes,
        photo_url=photo_url or None,
        is_verified_closed=is_verified,
    )
    db.add(checkin)
    await record_activity_heartbeat(db, user_id, switch_type="wear_checkin")
    await db.flush()


def ocr_verify_seal(tag_number: str) -> dict:
    """Run OCR seal inspection."""
    from app.media.ocr_seals import extract_seal_tag_from_photo

    return extract_seal_tag_from_photo(b"SAMPLE_TAG_BYTES", expected_tag=tag_number)


# ─────────────────────────────────────────────────────────────────────────────
# Telegram code for offline sub
# ─────────────────────────────────────────────────────────────────────────────


async def generate_sub_tg_code(db: AsyncSession, sub_id: str, user_id: uuid.UUID) -> str:
    """Generate a 6-char code for linking an offline submissive to Telegram bot."""
    sub = await _get_owned_submissive(db, sub_id, user_id)

    code = f"SUB-{uuid.uuid4().hex[:6].upper()}"
    sub.telegram_link_code = code
    sub.telegram_link_code_expires = datetime.now(UTC) + timedelta(minutes=30)
    db.add(sub)
    await db.flush()
    return code
