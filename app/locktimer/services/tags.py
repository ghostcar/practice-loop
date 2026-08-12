"""LockTimer tag (numbered seal) verification — close-time tags, verify, audit."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer.repositories import write_audit
from app.models.locktimer import LockSession, LockSlotOccurrence, LockTagViolation


def _now() -> datetime:
    return datetime.now(UTC)


async def verify_tag(
    db: AsyncSession,
    *,
    occurrence: LockSlotOccurrence,
    provided_tag: str,
    owner_id: uuid.UUID,
    now: datetime | None = None,
) -> dict:
    """Verify that a provided tag number matches the one stored at close.

    If mismatch, records a violation. Returns dict with match status.
    """
    if now is None:
        now = _now()

    session = await db.get(LockSession, occurrence.session_id)
    if session is None or session.owner_id != owner_id:
        raise ValueError("Session not found")

    expected = occurrence.close_tag_number
    matched = expected == provided_tag

    if not matched:
        violation = LockTagViolation(
            session_id=occurrence.session_id,
            slot_occurrence_id=occurrence.id,
            expected_tag=expected,
            provided_tag=provided_tag,
            reason="mismatch",
            created_at=now,
        )
        db.add(violation)
        await db.flush()

        await write_audit(
            db,
            session_id=occurrence.session_id,
            actor_type="user",
            actor_user_id=owner_id,
            event_type="locktimer.tag.verified_mismatch",
            object_type="lock_slot_occurrence",
            object_id=occurrence.id,
            payload={
                "expected_tag": expected,
                "provided_tag": provided_tag,
                "violation_id": str(violation.id),
            },
        )

    return {
        "matched": matched,
        "expected_tag": expected,
        "provided_tag": provided_tag,
        "violation_id": str(violation.id) if not matched else None,
    }


async def lookup_tag(
    db: AsyncSession,
    *,
    tag_number: str,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> dict | None:
    """Look up which slot was closed with a given tag number."""
    session = await db.get(LockSession, session_id)
    if session is None or session.owner_id != owner_id:
        raise ValueError("Session not found")

    result = await db.execute(
        select(LockSlotOccurrence).where(
            LockSlotOccurrence.session_id == session_id,
            LockSlotOccurrence.close_tag_number == tag_number,
        )
    )
    occ = result.scalars().first()
    if occ is None:
        return None

    return {
        "slot_occurrence_id": str(occ.id),
        "session_id": str(occ.session_id),
        "state": occ.state,
        "close_tag_number": occ.close_tag_number,
        "actual_closed_at": occ.actual_closed_at.isoformat() if occ.actual_closed_at else None,
    }


async def list_tag_violations(
    db: AsyncSession,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
    limit: int = 50,
) -> list[LockTagViolation]:
    """List tag violations for a session (owner-scoped)."""
    session = await db.get(LockSession, session_id)
    if session is None or session.owner_id != owner_id:
        raise ValueError("Session not found")

    result = await db.execute(
        select(LockTagViolation)
        .where(LockTagViolation.session_id == session_id)
        .order_by(LockTagViolation.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
