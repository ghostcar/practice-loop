"""Universal Omni-Pillory Service (ADR-206 Stage 4).

Manages per-trigger disciplinary pillory sessions, multi-trigger tracking,
escalating timer freezes, and autonomous repentance across the personal contour.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.locktimer import LockSession
from app.models.pillory import PilloryEntry
from app.models.user import User
from app.services.discipline_engine import calc_effective_multiplier
from app.services.identity_service import on_pillory_status

logger = logging.getLogger(__name__)


async def create_pillory_entry(
    db: AsyncSession,
    user: User,
    *,
    trigger: str,
    title: str,
    reason: str,
    duration_minutes: int = 60,
    lock_session: LockSession | None = None,
    config: dict[str, Any] | None = None,
    requires_photo: bool = True,
    freeze_lock_timer: bool = True,
) -> PilloryEntry:
    """Creates an independent PilloryEntry for a specific trigger violation."""
    now = datetime.now(UTC)
    eff_mult = calc_effective_multiplier(user)

    cfg = {
        "extension_step_minutes": 15,
        "soften_step_minutes": 10,
        "freeze_threshold": 4,
        "freeze_add_minutes": 15,
        "freeze_escalation_step": 5,
        "media_shame": lock_session is None,
        **(config or {}),
    }

    # Scale initial duration by effective multiplier
    scaled_duration = int(round(duration_minutes * eff_mult))
    expires_at = now + timedelta(minutes=scaled_duration)

    lock_session_id = lock_session.id if lock_session else None

    # If user has an active lock session and freeze is requested, freeze it immediately
    if lock_session is None and freeze_lock_timer:
        # Check if user has an active lock session in db
        stmt = select(LockSession).where(
            LockSession.owner_id == user.id,
            LockSession.state.in_(["active", "locked", "frozen"]),
        ).order_by(LockSession.created_at.desc())
        active_sess = (await db.execute(stmt)).scalars().first()
        if active_sess:
            lock_session = active_sess
            lock_session_id = active_sess.id

    if lock_session and freeze_lock_timer:
        from app.locktimer.services.gamification_extensions_service import freeze_session_timer

        await freeze_session_timer(
            db,
            lock_session.id,
            user.id,
            reason=f"Позорный столб: {title} ({reason})",
        )

    entry = PilloryEntry(
        user_id=user.id,
        lock_session_id=lock_session_id,
        trigger=trigger,
        title=title,
        reason=reason,
        initial_duration_minutes=scaled_duration,
        current_duration_minutes=scaled_duration,
        extensions_count=0,
        softens_count=0,
        freeze_timer_minutes=0,
        status="active",
        requires_repentance_photo=requires_photo,
        config=cfg,
        started_at=now,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    db.add(entry)

    # Award user the #pilloried identity tag
    on_pillory_status(user, is_pilloried=True)

    await db.flush()
    return entry


async def list_active_pillory_entries(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[PilloryEntry]:
    """Lists all currently active Pillory entries for a user."""
    stmt = (
        select(PilloryEntry)
        .where(PilloryEntry.user_id == user_id, PilloryEntry.status == "active")
        .order_by(PilloryEntry.created_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_pillory_entry(
    db: AsyncSession,
    entry_id: uuid.UUID,
    user_id: uuid.UUID | None = None,
) -> PilloryEntry | None:
    """Gets PilloryEntry by ID with optional user ownership check."""
    stmt = select(PilloryEntry).where(PilloryEntry.id == entry_id)
    if user_id:
        stmt = stmt.where(PilloryEntry.user_id == user_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def extend_pillory_entry(
    db: AsyncSession,
    entry: PilloryEntry,
    user: User,
) -> dict[str, Any]:
    """Extends pillory duration, applying multiplier and freeze escalations at 4+ extensions."""
    now = datetime.now(UTC)
    eff_mult = calc_effective_multiplier(user)
    cfg = dict(entry.config or {})

    step_min = int(cfg.get("extension_step_minutes", 15))
    added_min = int(round(step_min * eff_mult))

    entry.extensions_count += 1
    entry.current_duration_minutes += added_min
    entry.expires_at = max(now, entry.expires_at) + timedelta(minutes=added_min)

    freeze_added_min = 0
    freeze_thresh = int(cfg.get("freeze_threshold", 4))

    # Check 4+ extensions threshold: trigger freeze escalation
    if entry.extensions_count >= freeze_thresh:
        base_freeze = int(cfg.get("freeze_add_minutes", 15))
        escalation_step = int(cfg.get("freeze_escalation_step", 5))
        extra_times = entry.extensions_count - freeze_thresh
        freeze_added_min = base_freeze + (extra_times * escalation_step)
        entry.freeze_timer_minutes += freeze_added_min

        # If user has an associated lock session, add freeze penalty to it
        if entry.lock_session_id:
            sess = await db.get(LockSession, entry.lock_session_id)
            if sess:
                if sess.is_frozen and sess.frozen_remaining_seconds:
                    sess.frozen_remaining_seconds += freeze_added_min * 60
                elif not sess.is_frozen and sess.state == "active":
                    from app.locktimer.services.gamification_extensions_service import freeze_session_timer

                    await freeze_session_timer(
                        db, sess.id, user.id, reason=f"Позорный столб: эскалация заморозки ({entry.extensions_count} продлений)"
                    )
                    if sess.frozen_remaining_seconds:
                        sess.frozen_remaining_seconds += freeze_added_min * 60

    entry.updated_at = now
    await db.flush()

    return {
        "success": True,
        "extensions_count": entry.extensions_count,
        "added_minutes": added_min,
        "current_duration_minutes": entry.current_duration_minutes,
        "freeze_added_minutes": freeze_added_min,
        "total_freeze_minutes": entry.freeze_timer_minutes,
        "expires_at": entry.expires_at.isoformat(),
    }


async def soften_pillory_entry(
    db: AsyncSession,
    entry: PilloryEntry,
    user: User,
) -> dict[str, Any]:
    """Softens pillory duration, reducing remaining time."""
    now = datetime.now(UTC)
    cfg = dict(entry.config or {})
    soften_min = int(cfg.get("soften_step_minutes", 10))

    entry.softens_count += 1
    entry.current_duration_minutes = max(5, entry.current_duration_minutes - soften_min)
    entry.expires_at = max(now + timedelta(minutes=5), entry.expires_at - timedelta(minutes=soften_min))
    entry.updated_at = now
    await db.flush()

    return {
        "success": True,
        "softens_count": entry.softens_count,
        "subtracted_minutes": soften_min,
        "current_duration_minutes": entry.current_duration_minutes,
        "expires_at": entry.expires_at.isoformat(),
    }


async def submit_repentance(
    db: AsyncSession,
    entry: PilloryEntry,
    user: User,
    photo_url: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Submits repentance (photo or emulation) to release or halve remaining sentence."""
    now = datetime.now(UTC)
    entry.requires_repentance_photo = False
    if photo_url:
        entry.repentance_photo_url = photo_url

    # Complete this pillory entry
    entry.status = "completed"
    entry.updated_at = now

    # Check if there are other active pillory entries for this user
    other_active = await list_active_pillory_entries(db, user.id)
    remaining_active = [e for e in other_active if e.id != entry.id]

    unfrozen_timer = False
    if not remaining_active:
        # User is completely released from pillory
        on_pillory_status(user, is_pilloried=False)

        # Unfreeze lock session timer if frozen by pillory
        if entry.lock_session_id:
            sess = await db.get(LockSession, entry.lock_session_id)
            if sess and sess.is_frozen:
                from app.locktimer.services.gamification_extensions_service import unfreeze_session_timer

                await unfreeze_session_timer(db, sess.id, user.id, reason="Снятие с Позорного столба (раскаяние)")
                unfrozen_timer = True

    await db.flush()
    return {
        "success": True,
        "status": "completed",
        "remaining_pillory_count": len(remaining_active),
        "unfrozen_timer": unfrozen_timer,
    }
