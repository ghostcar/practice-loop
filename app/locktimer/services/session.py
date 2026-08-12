"""LockTimer session service — C3 start (freeze + snapshot + atomic start), C5 safety stop."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import domain as d
from app.locktimer import enums as e
from app.locktimer import repositories as repos
from app.locktimer.repositories import get_active_session, get_session, write_audit
from app.locktimer.services.materializer import _compute_initial_end, _materialize_session
from app.models.locktimer import (
    LockSession,
    LockSessionSnapshot,
    LockSlotOccurrence,
    LockTaskOccurrence,
)


def _now() -> datetime:
    return datetime.now(UTC)


async def start_session(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
    now: datetime | None = None,
) -> LockSession:
    """Validate, create canonical snapshot, atomically start the session.

    Returns the started LockSession.
    Raises ValueError if session not found, not a draft, or another active session exists.
    """
    if now is None:
        now = _now()

    session = await get_session(db, session_id, owner_id)
    if session is None:
        raise ValueError("Session not found")
    if session.state != e.SESSION_DRAFT:
        raise ValueError(f"Cannot start session in state {session.state}")

    # Check for existing active session (partial unique index enforces this at DB level too)
    existing = await get_active_session(db, owner_id)
    if existing is not None:
        raise ValueError("Another active session already exists")

    # Build canonical config
    slot_rules = await repos.list_slot_rules(db, session_id)
    task_rules = await repos.list_task_rules(db, session_id)

    config = {
        "duration_type": session.duration_type,
        "timezone": session.timezone,
        "merge_gap_seconds": session.merge_gap_seconds,
        "can_extend_duration": session.can_extend_duration,
        "max_end_at": session.max_end_at.isoformat() if session.max_end_at else None,
        "original_end_at": session.original_end_at.isoformat() if session.original_end_at else None,
        "slot_rules": [
            {
                "id": str(r.id),
                "name": r.name,
                "rule_type": r.rule_type,
                "schedule": r.schedule,
                "duration_seconds": r.duration_seconds,
                "allow_late_open": r.allow_late_open,
                "max_late_seconds": r.max_late_seconds,
                "extend_on_late_open": r.extend_on_late_open,
                "close_grace_seconds": r.close_grace_seconds,
                "late_close_policy": r.late_close_policy,
            }
            for r in slot_rules
        ],
        "task_rules": [
            {
                "id": str(r.id),
                "title": r.title,
                "schedule_type": r.schedule_type,
                "schedule": r.schedule,
                "due_window_seconds": r.due_window_seconds,
                "hide_until_due": r.hide_until_due,
                "requires_report": r.requires_report,
                "penalty_policy": r.penalty_policy,
            }
            for r in task_rules
        ],
    }

    canonical = d.canonical_json(config)
    config_hash = d.sha256_hex(canonical)

    # Create immutable snapshot
    snapshot = LockSessionSnapshot(
        session_id=session.id,
        schema_version=1,
        canonical_config=config,
        config_sha256=config_hash,
    )
    db.add(snapshot)

    # Determine effective start/end
    started_at = session.requested_start_at or now
    effective_end = _compute_initial_end(session, started_at)

    # Atomically transition to active
    stmt = (
        update(LockSession)
        .where(
            LockSession.id == session_id,
            LockSession.owner_id == owner_id,
            LockSession.state == e.SESSION_DRAFT,
        )
        .values(
            state=e.SESSION_ACTIVE,
            started_at=started_at,
            effective_end_at=effective_end,
            row_version=LockSession.row_version + 1,
            updated_at=now,
        )
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise ValueError("Session already started or not found")
    await db.flush()
    session = await get_session(db, session_id, owner_id)
    if session is None:
        raise ValueError("Session not found after start")

    # Audit
    await write_audit(
        db,
        session_id=session_id,
        actor_type="user",
        actor_user_id=owner_id,
        event_type="locktimer.session.started",
        object_type="lock_session",
        object_id=session_id,
        from_version=0,
        to_version=session.row_version,
        payload={"config_sha256": config_hash},
    )

    # Materialize initial occurrences (C4)
    await _materialize_session(db, session, slot_rules, task_rules, now)

    return session


async def safety_stop(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
    reason_code: str = "user_requested",
    now: datetime | None = None,
) -> LockSession:
    """Immediately safety-stop an active session. Cancels future occurrences."""
    if now is None:
        now = _now()

    d.validate_safety_stop_reason(reason_code)

    session = await get_session(db, session_id, owner_id)
    if session is None:
        raise ValueError("Session not found")
    if session.state != e.SESSION_ACTIVE:
        raise ValueError(f"Cannot safety-stop session in state {session.state}")

    # Atomically transition
    stmt = (
        update(LockSession)
        .where(
            LockSession.id == session_id,
            LockSession.owner_id == owner_id,
            LockSession.state == e.SESSION_ACTIVE,
        )
        .values(
            state=e.SESSION_SAFETY_STOPPED,
            safety_stopped_at=now,
            safety_stop_reason_code=reason_code,
            row_version=LockSession.row_version + 1,
            updated_at=now,
        )
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise ValueError("Session already stopped or not active")
    await db.flush()
    session = await get_session(db, session_id, owner_id)
    if session is None:
        raise ValueError("Session not found after safety stop")

    # Cancel future occurrences
    await _cancel_future_occurrences(db, session_id, now)

    await write_audit(
        db,
        session_id=session_id,
        actor_type="user",
        actor_user_id=owner_id,
        event_type="locktimer.session.safety_stopped",
        object_type="lock_session",
        object_id=session_id,
        from_version=session.row_version - 1,
        to_version=session.row_version,
        payload={"reason_code": reason_code},
    )

    await db.flush()
    return session


async def _cancel_future_occurrences(
    db: AsyncSession,
    session_id: uuid.UUID,
    now: datetime,
) -> None:
    """Cancel all future slot and task occurrences."""
    # Cancel future slots
    await db.execute(
        update(LockSlotOccurrence)
        .where(
            LockSlotOccurrence.session_id == session_id,
            LockSlotOccurrence.state.in_((e.SLOT_PENDING, e.SLOT_ELIGIBLE)),
            LockSlotOccurrence.planned_open_at > now,
        )
        .values(
            state=e.SLOT_CANCELLED,
            blocked_reason_code="safety_stop",
            row_version=LockSlotOccurrence.row_version + 1,
            updated_at=now,
        )
    )

    # Cancel future tasks
    await db.execute(
        update(LockTaskOccurrence)
        .where(
            LockTaskOccurrence.session_id == session_id,
            LockTaskOccurrence.state.in_((e.TASK_SCHEDULED, e.TASK_VISIBLE)),
            LockTaskOccurrence.due_at > now,
        )
        .values(
            state=e.TASK_SAFETY_CANCELLED,
            finalized_at=now,
            final_reason_code="safety_stop",
            row_version=LockTaskOccurrence.row_version + 1,
            updated_at=now,
        )
    )
