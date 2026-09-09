"""Discipline, Verification Protocol, and Pillory integration for LockSessions (ADR-197)."""

from __future__ import annotations

import hashlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer.repositories import get_session
from app.models.locktimer import LockSession
from app.models.media import VerificationChallenge
from app.services.media import (
    compute_code_hmac,
    generate_verification_code,
    verify_code_constant_time,
)

logger = logging.getLogger(__name__)


async def get_active_session_challenge(
    db: AsyncSession,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> VerificationChallenge | None:
    """Returns currently active VerificationChallenge for lock session, if any and not expired."""
    now = datetime.now(UTC)
    stmt = select(VerificationChallenge).where(
        VerificationChallenge.owner_id == owner_id,
        VerificationChallenge.owner_type == "lock_session",
        VerificationChallenge.owner_ref_id == session_id,
        VerificationChallenge.state == "active",
        VerificationChallenge.expires_at > now,
    ).order_by(VerificationChallenge.created_at.desc())
    result = await db.execute(stmt)
    return result.scalars().first()


async def create_session_verification_challenge(
    db: AsyncSession,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
    *,
    ttl_minutes: int = 60,
    code_length: int = 6,
) -> tuple[VerificationChallenge, str]:
    """Creates a new single-use VerificationChallenge for the session.

    Invalidates any previous active challenges and returns (challenge, plaintext_code).
    """
    now = datetime.now(UTC)
    code = generate_verification_code(code_length)
    code_hmac = compute_code_hmac(code)

    # Invalidate previous active challenges
    old_challenges = await db.execute(
        select(VerificationChallenge).where(
            VerificationChallenge.owner_id == owner_id,
            VerificationChallenge.owner_type == "lock_session",
            VerificationChallenge.owner_ref_id == session_id,
            VerificationChallenge.state == "active",
        )
    )
    for old in old_challenges.scalars().all():
        old.state = "expired"

    challenge = VerificationChallenge(
        owner_id=owner_id,
        owner_type="lock_session",
        owner_ref_id=session_id,
        code_hmac=code_hmac,
        code_length=code_length,
        state="active",
        max_attempts=5,
        attempt_count=0,
        expires_at=now + timedelta(minutes=ttl_minutes),
        created_at=now,
    )
    db.add(challenge)
    await db.flush()
    return challenge, code


async def verify_session_photo_submission(
    db: AsyncSession,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
    tag_number: str,
    verification_code: str,
    notes: str | None = None,
) -> dict:
    """Verifies user photo submission with one-time verification code and seal tag.

    Returns dict with success status, error details, and inspection log info.
    """
    now = datetime.now(UTC)
    session = await get_session(db, session_id, owner_id)
    if session is None:
        return {"success": False, "error": "Сессия не найдена"}

    challenge = await get_active_session_challenge(db, session_id, owner_id)
    if challenge is None:
        return {"success": False, "error": "Нет активного запроса на проверку. Запросите новый код."}

    challenge.attempt_count += 1
    if not verify_code_constant_time(verification_code.strip(), challenge.code_hmac):
        if challenge.attempt_count >= challenge.max_attempts:
            challenge.state = "failed"
            await db.flush()
            return {"success": False, "error": "Превышено число попыток ввода кода. Запросите новый код."}
        await db.flush()
        rem = challenge.max_attempts - challenge.attempt_count
        return {"success": False, "error": f"Неверный проверочный код. Осталось попыток: {rem}"}

    # Code verified successfully -> consume challenge
    challenge.state = "consumed"
    challenge.consumed_at = now

    # Record seal inspection
    from app.services.wear_reactive_service import record_seal_inspection
    inspection_notes = f"Код проверки {verification_code.strip()} подтверждён. {notes or ''}".strip()
    inspection = await record_seal_inspection(
        db,
        user_id=owner_id,
        tag_number=tag_number.strip(),
        comfort_score=None,
        notes=inspection_notes,
    )

    return {
        "success": True,
        "tag_number": tag_number.strip(),
        "inspection_id": str(inspection.id) if inspection else None,
        "verified_at": now.isoformat(),
    }


async def send_session_to_pillory(
    db: AsyncSession,
    session: LockSession,
    reason: str,
    details: str | None = None,
) -> bool:
    """Publishes lock session to public Pillory (/social/pillory) if pillory_enabled is True."""
    if not session.pillory_enabled:
        return False

    try:
        from app.platform.social.models import SocialPublication, SocialSubject
        from app.platform.social.repositories import create_publication, register_subject

        # Ensure subject
        subject_res = await db.execute(
            select(SocialSubject).where(
                SocialSubject.subject_type == "timer.session",
                SocialSubject.domain_object_id == str(session.id),
                SocialSubject.is_active.is_(True),
            )
        )
        subject = subject_res.scalar_one_or_none()
        if subject is None:
            subject = await register_subject(
                db,
                session.owner_id,
                "timer.session",
                str(session.id),
                projection_snapshot={"title": f"Сессия {str(session.id)[:8]}", "state": session.state},
            )

        # Check existing active pillory publication
        existing_pub = await db.execute(
            select(SocialPublication).where(
                SocialPublication.subject_id == subject.id,
                SocialPublication.subject_namespace == "tracker.pillory",
                SocialPublication.is_active.is_(True),
            )
        )
        if existing_pub.scalar_one_or_none() is not None:
            return True  # Already on pillory

        snapshot = {
            "title": f"Нарушение регламента: {reason}",
            "summary": details or f"Сессия пояса {str(session.id)[:8]} нарушила режим ношения или срок проверки.",
            "session_id": str(session.id),
            "tag_number": session.current_tag_number or "—",
            "violation_at": datetime.now(UTC).isoformat(),
        }
        snapshot_hash = hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()

        await create_publication(
            db,
            session.owner_id,
            subject.id,
            visibility="public",
            snapshot=snapshot,
            snapshot_hash=snapshot_hash,
            subject_namespace="tracker.pillory",
            source="auto",
        )
        from app.models.user import User
        from app.services import identity_service

        user = await db.get(User, session.owner_id)
        if user:
            identity_service.on_pillory_status(user, is_pilloried=True)
        await db.flush()
        return True
    except Exception:
        logger.exception("Failed to send session %s to Pillory", session.id)
        return False


async def apply_pillory_vote_to_session(
    db: AsyncSession,
    session: LockSession,
    vote_type: str,
) -> dict:
    """Applies community vote effect to active session if pillory_auto_extend is enabled."""
    if not session.pillory_auto_extend or session.state != "active":
        return {"applied": False, "reason": "Сессия не активна или авто-продление выключено"}

    from app.timeutils import as_utc

    now = datetime.now(UTC)
    base_end = as_utc(session.effective_end_at) if session.effective_end_at else now

    if vote_type == "add_15m":
        session.effective_end_at = base_end + timedelta(minutes=15)
        action_desc = "+15 минут добавлено сообществом"
    elif vote_type == "add_1h":
        session.effective_end_at = base_end + timedelta(hours=1)
        action_desc = "+1 час добавлен сообществом"
    elif vote_type == "sub_15m":
        session.effective_end_at = max(now, base_end - timedelta(minutes=15))
        action_desc = "-15 минут сокращено сообществом"
    elif vote_type == "assign_task":
        # Assign penalty verification task to user day
        from app.models.task import Task
        task = Task(
            user_id=session.owner_id,
            title="[Pillory] Внеплановая инспекция пояса по решению сообщества",
            category="chastity",
            status="pending",
            scheduled_date=now.date(),
            due_time=now + timedelta(hours=2),
            xp_reward=10,
        )
        db.add(task)
        action_desc = "Назначена внеплановая инспекция пояса"
    else:
        return {"applied": False, "reason": "Неизвестный тип голоса"}

    session.updated_at = now
    await db.flush()
    eff_end_iso = session.effective_end_at.isoformat() if session.effective_end_at else None
    return {"applied": True, "action": action_desc, "effective_end_at": eff_end_iso}
