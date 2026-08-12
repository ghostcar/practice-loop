"""LockTimer application services — C3 draft/start, C4 materializer, C5 execution.

All services operate within a SQLAlchemy AsyncSession and are owner-scoped.
Domain logic (enums, domain.py) is called but never duplicated here.

REFACTORING.md step 1 (Session 82): split from a single module into siblings
(drafts, materializer, session, jobs, tags). This file keeps the C5 execution
core (open/close slot, task lifecycle, penalties) and re-exports every sibling
symbol so all historical import paths keep working.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import domain as d
from app.locktimer import enums as e
from app.locktimer.repositories import write_audit
from app.locktimer.services.drafts import (
    _next_rule_sort_order,
    add_slot_rule,
    add_task_rule,
    create_draft,
    delete_slot_rule,
    delete_task_rule,
    reorder_rules,
    update_draft,
)
from app.locktimer.services.jobs import claim_jobs, emit_outbox_event, enqueue_job
from app.locktimer.services.materializer import (
    _combine_date_time,
    _compute_initial_end,
    _generate_slot_occurrences,
    _generate_task_occurrences,
    _in_progress_check,
    _make_slot_occ,
    _make_task_occ,
    _materialize_session,
    _parse_date,
)
from app.locktimer.services.session import _cancel_future_occurrences, safety_stop, start_session
from app.locktimer.services.tags import list_tag_violations, lookup_tag, verify_tag
from app.models.locktimer import (
    LockPenaltyEvent,
    LockSession,
    LockSlotOccurrence,
    LockSlotRule,
    LockTaskOccurrence,
)

__all__ = [
    # drafts
    "_next_rule_sort_order",
    "create_draft",
    "update_draft",
    "add_slot_rule",
    "add_task_rule",
    "delete_slot_rule",
    "delete_task_rule",
    "reorder_rules",
    # session
    "start_session",
    "safety_stop",
    "_cancel_future_occurrences",
    # materializer
    "_compute_initial_end",
    "_materialize_session",
    "_generate_slot_occurrences",
    "_generate_task_occurrences",
    "_parse_date",
    "_combine_date_time",
    "_in_progress_check",
    "_make_slot_occ",
    "_make_task_occ",
    # jobs
    "emit_outbox_event",
    "enqueue_job",
    "claim_jobs",
    # tags
    "verify_tag",
    "lookup_tag",
    "list_tag_violations",
    # execution core
    "open_slot",
    "close_slot",
    "reveal_task",
    "submit_task",
    "complete_task",
    "skip_task",
    "apply_penalty",
]


def _now() -> datetime:
    return datetime.now(UTC)


# ============================================================================
# C5 — Slot execution
# ============================================================================


async def open_slot(
    db: AsyncSession,
    *,
    occurrence: LockSlotOccurrence,
    owner_id: uuid.UUID,
    now: datetime | None = None,
) -> LockSlotOccurrence:
    """Open a slot occurrence. Must be eligible; late open applies extension."""
    if now is None:
        now = _now()

    if occurrence.state not in (e.SLOT_PENDING, e.SLOT_ELIGIBLE):
        raise ValueError(f"Cannot open slot in state {occurrence.state}")

    # Check eligibility
    if now < occurrence.eligible_from:
        raise ValueError("Slot not yet eligible")
    if now > occurrence.eligible_until:
        raise ValueError("Slot eligibility window expired")

    extension_seconds = 0
    rule = await db.get(LockSlotRule, occurrence.rule_id)
    if now > occurrence.planned_open_at:
        # Late open — apply late policy
        late_seconds = int((now - occurrence.planned_open_at).total_seconds())
        if rule and rule.extend_on_late_open:
            extension_seconds = min(late_seconds, rule.max_late_seconds)

    # Compute close_due_at
    duration = rule.duration_seconds if rule else 3600
    close_due = now + timedelta(seconds=duration + extension_seconds)

    stmt = (
        update(LockSlotOccurrence)
        .where(
            LockSlotOccurrence.id == occurrence.id,
            LockSlotOccurrence.state.in_((e.SLOT_PENDING, e.SLOT_ELIGIBLE)),
        )
        .values(
            state=e.SLOT_OPEN,
            actual_opened_at=now,
            close_due_at=close_due,
            extension_applied_seconds=extension_seconds,
            row_version=LockSlotOccurrence.row_version + 1,
            updated_at=now,
        )
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise ValueError("Slot already opened or not eligible")
    await db.flush()
    occ = await db.get(LockSlotOccurrence, occurrence.id)
    if occ is None:
        raise ValueError("Slot not found after open")

    await write_audit(
        db,
        session_id=occ.session_id,
        actor_type="user",
        actor_user_id=owner_id,
        event_type="locktimer.slot.opened",
        object_type="lock_slot_occurrence",
        object_id=occ.id,
        from_version=occurrence.row_version,
        to_version=occ.row_version,
        payload={"extension_applied_seconds": extension_seconds},
    )

    await db.flush()
    return occ


async def close_slot(
    db: AsyncSession,
    *,
    occurrence: LockSlotOccurrence,
    owner_id: uuid.UUID,
    tag_number: str | None = None,
    now: datetime | None = None,
) -> LockSlotOccurrence:
    """Close an open slot. If rule requires tag, tag_number is mandatory."""
    if now is None:
        now = _now()

    if occurrence.state != e.SLOT_OPEN:
        raise ValueError(f"Cannot close slot in state {occurrence.state}")

    # Check tag requirement
    rule = await db.get(LockSlotRule, occurrence.rule_id)
    if rule and rule.require_tag and not tag_number:
        raise ValueError("Tag number is required for this slot — rule requires a numbered tag")

    # Check tag uniqueness within session (if provided)
    if tag_number:
        existing_result = await db.execute(
            select(LockSlotOccurrence).where(
                LockSlotOccurrence.session_id == occurrence.session_id,
                LockSlotOccurrence.close_tag_number == tag_number,
                LockSlotOccurrence.id != occurrence.id,
            )
        )
        if existing_result.scalars().first():
            raise ValueError(f"Tag number '{tag_number}' has already been used in this session")

    values: dict = {
        "state": e.SLOT_CLOSED,
        "actual_closed_at": now,
        "row_version": LockSlotOccurrence.row_version + 1,
        "updated_at": now,
    }
    if tag_number:
        values["close_tag_number"] = tag_number

    stmt = (
        update(LockSlotOccurrence)
        .where(
            LockSlotOccurrence.id == occurrence.id,
            LockSlotOccurrence.state == e.SLOT_OPEN,
        )
        .values(**values)
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise ValueError("Slot already closed or not open")
    await db.flush()
    occ = await db.get(LockSlotOccurrence, occurrence.id)
    if occ is None:
        raise ValueError("Slot not found after close")

    await write_audit(
        db,
        session_id=occ.session_id,
        actor_type="user",
        actor_user_id=owner_id,
        event_type="locktimer.slot.closed",
        object_type="lock_slot_occurrence",
        object_id=occ.id,
        from_version=occurrence.row_version,
        to_version=occ.row_version,
        payload={"closed_at": now.isoformat()},
    )

    await db.flush()
    return occ


# ============================================================================
# C5 — Task execution
# ============================================================================


async def reveal_task(
    db: AsyncSession,
    *,
    occurrence: LockTaskOccurrence,
    owner_id: uuid.UUID,
    now: datetime | None = None,
) -> LockTaskOccurrence:
    """Make a hidden task visible."""
    if now is None:
        now = _now()

    if occurrence.state not in (e.TASK_SCHEDULED, e.TASK_VISIBLE):
        raise ValueError(f"Cannot reveal task in state {occurrence.state}")

    values: dict = {
        "content_visible": True,
        "revealed_at": now,
        "row_version": LockTaskOccurrence.row_version + 1,
        "updated_at": now,
    }
    if occurrence.state == e.TASK_SCHEDULED:
        values["state"] = e.TASK_VISIBLE

    stmt = (
        update(LockTaskOccurrence)
        .where(
            LockTaskOccurrence.id == occurrence.id,
            LockTaskOccurrence.state.in_((e.TASK_SCHEDULED, e.TASK_VISIBLE)),
        )
        .values(**values)
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise ValueError("Task cannot be revealed")
    await db.flush()
    occ = await db.get(LockTaskOccurrence, occurrence.id)
    if occ is None:
        raise ValueError("Task not found after reveal")
    return occ


async def submit_task(
    db: AsyncSession,
    *,
    occurrence: LockTaskOccurrence,
    owner_id: uuid.UUID,
    now: datetime | None = None,
) -> LockTaskOccurrence:
    """Submit a visible task for verification/completion."""
    if now is None:
        now = _now()

    if occurrence.state not in (e.TASK_VISIBLE, e.TASK_SUBMITTED):
        raise ValueError(f"Cannot submit task in state {occurrence.state}")

    if occurrence.state == e.TASK_VISIBLE:
        stmt = (
            update(LockTaskOccurrence)
            .where(
                LockTaskOccurrence.id == occurrence.id,
                LockTaskOccurrence.state == e.TASK_VISIBLE,
            )
            .values(
                state=e.TASK_SUBMITTED,
                row_version=LockTaskOccurrence.row_version + 1,
                updated_at=now,
            )
        )
        result = await db.execute(stmt)
        if result.rowcount == 0:
            raise ValueError("Task already submitted")
        await db.flush()
        occurrence = await db.get(LockTaskOccurrence, occurrence.id)
        if occurrence is None:
            raise ValueError("Task not found after submit")

    await db.flush()
    return occurrence


async def complete_task(
    db: AsyncSession,
    *,
    occurrence: LockTaskOccurrence,
    owner_id: uuid.UUID,
    now: datetime | None = None,
) -> LockTaskOccurrence:
    """Complete a submitted task."""
    if now is None:
        now = _now()

    valid_states = (e.TASK_SUBMITTED, e.TASK_VERIFYING)
    if occurrence.state not in valid_states:
        raise ValueError(f"Cannot complete task in state {occurrence.state}")

    stmt = (
        update(LockTaskOccurrence)
        .where(
            LockTaskOccurrence.id == occurrence.id,
            LockTaskOccurrence.state.in_(valid_states),
        )
        .values(
            state=e.TASK_COMPLETED,
            finalized_at=now,
            final_reason_code="completed",
            row_version=LockTaskOccurrence.row_version + 1,
            updated_at=now,
        )
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise ValueError("Task already finalized")
    await db.flush()
    occ = await db.get(LockTaskOccurrence, occurrence.id)
    if occ is None:
        raise ValueError("Task not found after complete")

    await write_audit(
        db,
        session_id=occ.session_id,
        actor_type="user",
        actor_user_id=owner_id,
        event_type="locktimer.task.completed",
        object_type="lock_task_occurrence",
        object_id=occ.id,
        from_version=occurrence.row_version,
        to_version=occ.row_version,
    )

    await db.flush()
    return occ


async def skip_task(
    db: AsyncSession,
    *,
    occurrence: LockTaskOccurrence,
    owner_id: uuid.UUID,
    now: datetime | None = None,
) -> LockTaskOccurrence:
    """Skip a scheduled/visible task (normal breach — may trigger penalty)."""
    if now is None:
        now = _now()

    valid_states = (e.TASK_SCHEDULED, e.TASK_VISIBLE)
    if occurrence.state not in valid_states:
        raise ValueError(f"Cannot skip task in state {occurrence.state}")

    stmt = (
        update(LockTaskOccurrence)
        .where(
            LockTaskOccurrence.id == occurrence.id,
            LockTaskOccurrence.state.in_(valid_states),
        )
        .values(
            state=e.TASK_SKIPPED,
            finalized_at=now,
            final_reason_code="skipped",
            row_version=LockTaskOccurrence.row_version + 1,
            updated_at=now,
        )
    )
    result = await db.execute(stmt)
    if result.rowcount == 0:
        raise ValueError("Task already finalized")
    await db.flush()
    occ = await db.get(LockTaskOccurrence, occurrence.id)
    if occ is None:
        raise ValueError("Task not found after skip")

    await write_audit(
        db,
        session_id=occ.session_id,
        actor_type="user",
        actor_user_id=owner_id,
        event_type="locktimer.task.skipped",
        object_type="lock_task_occurrence",
        object_id=occ.id,
        from_version=occurrence.row_version,
        to_version=occ.row_version,
    )

    await db.flush()
    return occ


# ============================================================================
# C5 — Penalty service
# ============================================================================


async def apply_penalty(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    penalty_type: str,
    source_kind: str,
    source_id: uuid.UUID,
    requested_value: int | None = None,
    reason_code: str = "normal_breach",
    idempotency_key: str | None = None,
    now: datetime | None = None,
) -> LockPenaltyEvent | None:
    """Apply an allowlisted penalty. Idempotent by idempotency_key."""
    if now is None:
        now = _now()

    if penalty_type not in e.PENALTY_TYPES:
        raise ValueError(f"Unknown penalty type: {penalty_type}")

    key = idempotency_key or str(uuid.uuid4())

    # Check idempotency
    existing_result = await db.execute(select(LockPenaltyEvent).where(LockPenaltyEvent.idempotency_key == key))
    if existing_result.scalars().first():
        return None  # already applied

    # Compute applied value
    applied_value = requested_value

    # Cap check: for add_time, respect max_end_at
    if penalty_type == e.PENALTY_ADD_TIME:
        session = await db.get(LockSession, session_id)
        if session and session.max_end_at and session.effective_end_at:
            new_end, applied = d.apply_extension(session.effective_end_at, requested_value or 0, session.max_end_at)
            applied_value = applied
            if applied < (requested_value or 0):
                penalty_state = e.PENALTY_CAPPED_NOOP
            elif applied == 0:
                return None  # noop
            else:
                penalty_state = e.PENALTY_APPLIED
                # Actually extend the session
                session.effective_end_at = new_end
                session.updated_at = now
        else:
            penalty_state = e.PENALTY_APPLIED
    else:
        penalty_state = e.PENALTY_APPLIED

    event = LockPenaltyEvent(
        session_id=session_id,
        source_kind=source_kind,
        source_id=source_id,
        penalty_type=penalty_type,
        requested_value=requested_value,
        applied_value=applied_value,
        state=penalty_state,
        reason_code=reason_code,
        idempotency_key=key,
        penalty_metadata={},
        created_at=now,
    )
    db.add(event)
    await db.flush()  # assign event.id before audit

    await write_audit(
        db,
        session_id=session_id,
        actor_type="system",
        actor_user_id=None,
        event_type="locktimer.penalty.applied",
        object_type="lock_penalty_event",
        object_id=event.id,
        payload={
            "penalty_type": penalty_type,
            "requested": requested_value,
            "applied": applied_value,
            "state": penalty_state,
        },
    )

    await db.flush()
    return event
