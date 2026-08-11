"""LockTimer repositories — owner-scoped queries and conditional UPDATE helpers."""

from __future__ import annotations

import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.locktimer import (
    LockAuditEvent,
    LockSession,
    LockSlotOccurrence,
    LockSlotRule,
    LockTaskOccurrence,
    LockTaskRule,
    LockTimerTemplate,
)

# ---------------------------------------------------------------------------
# LockTimerTemplate
# ---------------------------------------------------------------------------


async def get_template(db: AsyncSession, template_id: uuid.UUID, owner_id: uuid.UUID) -> LockTimerTemplate | None:
    result = await db.execute(
        select(LockTimerTemplate).where(
            LockTimerTemplate.id == template_id,
            LockTimerTemplate.owner_id == owner_id,
        )
    )
    return result.scalar_one_or_none()


async def list_templates(db: AsyncSession, owner_id: uuid.UUID) -> list[LockTimerTemplate]:
    result = await db.execute(
        select(LockTimerTemplate)
        .where(
            LockTimerTemplate.owner_id == owner_id,
            LockTimerTemplate.archived_at.is_(None),
        )
        .order_by(LockTimerTemplate.updated_at.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# LockSession
# ---------------------------------------------------------------------------


async def get_session(db: AsyncSession, session_id: uuid.UUID, owner_id: uuid.UUID) -> LockSession | None:
    result = await db.execute(
        select(LockSession).where(
            LockSession.id == session_id,
            LockSession.owner_id == owner_id,
        )
    )
    return result.scalar_one_or_none()


async def get_active_session(db: AsyncSession, owner_id: uuid.UUID) -> LockSession | None:
    result = await db.execute(
        select(LockSession).where(
            LockSession.owner_id == owner_id,
            LockSession.state == "active",
        )
    )
    return result.scalar_one_or_none()


async def list_sessions(db: AsyncSession, owner_id: uuid.UUID, limit: int = 50) -> list[LockSession]:
    result = await db.execute(
        select(LockSession).where(LockSession.owner_id == owner_id).order_by(LockSession.updated_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Conditional UPDATE helper (for atomic state transitions)
# ---------------------------------------------------------------------------


async def transition_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
    from_states: frozenset[str],
    to_state: str,
    **extra_fields,
) -> LockSession | None:
    """Atomically update session state; returns updated row or None if not eligible."""
    result = await db.execute(
        update(LockSession)
        .where(
            LockSession.id == session_id,
            LockSession.owner_id == owner_id,
            LockSession.state.in_(from_states),
        )
        .values(state=to_state, row_version=LockSession.row_version + 1, **extra_fields)
        .returning(LockSession)
    )
    row = result.scalar_one_or_none()
    if row is not None:
        await db.flush()
    return row


# ---------------------------------------------------------------------------
# LockSlotRule / LockTaskRule
# ---------------------------------------------------------------------------


async def list_slot_rules(db: AsyncSession, session_id: uuid.UUID) -> list[LockSlotRule]:
    result = await db.execute(select(LockSlotRule).where(LockSlotRule.session_id == session_id))
    return list(result.scalars().all())


async def list_task_rules(db: AsyncSession, session_id: uuid.UUID) -> list[LockTaskRule]:
    result = await db.execute(select(LockTaskRule).where(LockTaskRule.session_id == session_id))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Occurrences
# ---------------------------------------------------------------------------


async def list_slot_occurrences(
    db: AsyncSession, session_id: uuid.UUID, state: str | None = None, limit: int = 200
) -> list[LockSlotOccurrence]:
    stmt = select(LockSlotOccurrence).where(LockSlotOccurrence.session_id == session_id)
    if state:
        stmt = stmt.where(LockSlotOccurrence.state == state)
    stmt = stmt.order_by(LockSlotOccurrence.planned_open_at).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def list_task_occurrences(
    db: AsyncSession, session_id: uuid.UUID, state: str | None = None, limit: int = 200
) -> list[LockTaskOccurrence]:
    stmt = select(LockTaskOccurrence).where(LockTaskOccurrence.session_id == session_id)
    if state:
        stmt = stmt.where(LockTaskOccurrence.state == state)
    stmt = stmt.order_by(LockTaskOccurrence.appears_at).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Audit (append-only)
# ---------------------------------------------------------------------------


async def write_audit(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    actor_type: str,
    actor_user_id: uuid.UUID | None,
    event_type: str,
    object_type: str,
    object_id: uuid.UUID,
    correlation_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    from_version: int | None = None,
    to_version: int | None = None,
    payload: dict | None = None,
) -> LockAuditEvent:
    event = LockAuditEvent(
        session_id=session_id,
        actor_type=actor_type,
        actor_user_id=actor_user_id,
        event_type=event_type,
        object_type=object_type,
        object_id=object_id,
        correlation_id=correlation_id or uuid.uuid4(),
        idempotency_key=idempotency_key,
        from_version=from_version,
        to_version=to_version,
        payload=payload or {},
    )
    db.add(event)
    await db.flush()
    return event
