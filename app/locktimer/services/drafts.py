"""LockTimer draft service — C3: create/update draft sessions, rule management (slots & tasks)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import domain as d
from app.locktimer import enums as e
from app.locktimer.repositories import get_session, write_audit
from app.models.locktimer import LockSession, LockSlotRule, LockTaskRule


def _now() -> datetime:
    return datetime.now(UTC)


async def _next_rule_sort_order(
    db: AsyncSession, model: type[LockSlotRule] | type[LockTaskRule], session_id: uuid.UUID
) -> int:
    """Return max(sort_order)+1 for rules of a session — new rules append at the end."""
    from sqlalchemy import func

    result = await db.execute(select(func.max(model.sort_order)).where(model.session_id == session_id))
    current_max = result.scalar_one_or_none()
    return (current_max if current_max is not None else -1) + 1


async def create_draft(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    duration_type: str = e.DURATION_FROM_START,
    timezone_str: str = "UTC",
    merge_gap_seconds: int = d.DEFAULT_MERGE_GAP_SECONDS,
    can_extend_duration: bool = False,
    template_id: uuid.UUID | None = None,
    device_id: uuid.UUID | None = None,
) -> LockSession:
    """Create a new draft session. One active session per owner enforced at start time."""
    now = _now()
    seed = d.generate_random_seed()

    if device_id is not None:
        from app.locktimer.services.device import get_device

        if await get_device(db, device_id, owner_id) is None:
            raise ValueError("Device not found or not owned by you")

    session = LockSession(
        owner_id=owner_id,
        template_id=template_id,
        device_id=device_id,
        state=e.SESSION_DRAFT,
        duration_type=duration_type,
        timezone=timezone_str,
        merge_gap_seconds=merge_gap_seconds,
        can_extend_duration=can_extend_duration,
        random_seed_encrypted=seed,
        random_seed_commitment=d.compute_seed_commitment(seed),
        privacy_mode="private",
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    await db.flush()
    return session


async def update_draft(
    db: AsyncSession,
    session: LockSession,
    **fields,
) -> LockSession:
    """Update draft fields. Only allowed in draft state."""
    if session.state != e.SESSION_DRAFT:
        raise ValueError("Only draft sessions can be edited")

    allowed = {
        "duration_type",
        "timezone",
        "requested_start_at",
        "original_end_at",
        "max_end_at",
        "can_extend_duration",
        "merge_gap_seconds",
    }
    for key, value in fields.items():
        if key in allowed and value is not None:
            setattr(session, key, value)

    # device_id may be set to None explicitly to unbind the device.
    if "device_id" in fields:
        device_id = fields["device_id"]
        if device_id is not None:
            from app.locktimer.services.device import get_device

            if await get_device(db, device_id, session.owner_id) is None:
                raise ValueError("Device not found or not owned by you")
        session.device_id = device_id

    session.updated_at = _now()
    await db.flush()
    return session


async def add_slot_rule(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    name: str,
    rule_type: str,
    schedule: dict,
    duration_seconds: int,
    inner_period_id: uuid.UUID | None = None,
    **extra,
) -> LockSlotRule:
    next_order = await _next_rule_sort_order(db, LockSlotRule, session_id)
    rule = LockSlotRule(
        session_id=session_id,
        client_key=uuid.uuid4(),
        inner_period_id=inner_period_id,
        name=name,
        rule_type=rule_type,
        schedule=schedule,
        duration_seconds=duration_seconds,
        sort_order=next_order,
        allow_late_open=extra.get("allow_late_open", False),
        max_late_seconds=extra.get("max_late_seconds", 0),
        extend_on_late_open=extra.get("extend_on_late_open", False),
        require_close_media=extra.get("require_close_media", False),
        close_grace_seconds=extra.get("close_grace_seconds", 0),
        late_close_policy=extra.get("late_close_policy"),
        llm_flags=extra.get("llm_flags", {}),
        journal_auto=extra.get("journal_auto", False),
        catalog_item_id=extra.get("catalog_item_id"),
        care_product_ids=extra.get("care_product_ids") or None,
        schema_version=1,
    )
    db.add(rule)
    await db.flush()
    return rule


async def add_task_rule(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    title: str,
    schedule_type: str,
    schedule: dict,
    due_window_seconds: int,
    inner_period_id: uuid.UUID | None = None,
    source_entity_id: uuid.UUID | None = None,
    **extra,
) -> LockTaskRule:
    next_order = await _next_rule_sort_order(db, LockTaskRule, session_id)
    rule = LockTaskRule(
        session_id=session_id,
        client_key=uuid.uuid4(),
        inner_period_id=inner_period_id,
        source_entity_id=source_entity_id,
        title=title,
        sort_order=next_order,
        description=extra.get("description"),
        category=extra.get("category", "general"),
        schedule_type=schedule_type,
        schedule=schedule,
        due_window_seconds=due_window_seconds,
        duration_seconds=extra.get("duration_seconds"),
        hide_until_due=extra.get("hide_until_due", False),
        requires_report=extra.get("requires_report", False),
        media_policy=extra.get("media_policy", {}),
        verification_policy=extra.get("verification_policy", {}),
        penalty_policy=extra.get("penalty_policy"),
        availability_policy=extra.get("availability_policy", {}),
        llm_flags=extra.get("llm_flags", {}),
        schema_version=1,
    )
    db.add(rule)
    await db.flush()
    return rule


async def add_medication_task_rule(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    med_schedule_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> LockTaskRule:
    """Create a relief task rule from a medication schedule (ADR-085).

    A medication relief task is a LockTimer task that represents an on-time
    medication dose. It is **relief-only**: ``penalty_policy`` stays None so
    skipping it never triggers a penalty (Health must not be gamified
    negatively). The rule is marked in ``availability_policy`` with
    ``{"relief": "medication", "med_schedule_id": ...}`` for honest UI.
    """
    from app.models.medication import MedSchedule

    sched = (
        await db.execute(
            select(MedSchedule).where(MedSchedule.id == med_schedule_id, MedSchedule.user_id == owner_id)
        )
    ).scalar_one_or_none()
    if sched is None:
        raise ValueError("Medication schedule not found")

    med = sched.medication
    dose = f"{sched.dose_quantity:g} {sched.dose_unit or ''}".strip()
    title = f"{med.name}" + (f" ({dose})" if dose else "")

    schedule = (
        {"time_of_day": sched.times_of_day[0]} if sched.times_of_day else {"time_of_day": "09:00"}
    )

    return await add_task_rule(
        db,
        session_id=session_id,
        title=title,
        schedule_type="daily",
        schedule=schedule,
        due_window_seconds=3600,
        category="medication",
        description=f"Medication relief — {sched.frequency_type} schedule",
        penalty_policy=None,  # relief-only: never penalize a skipped dose
        availability_policy={"relief": "medication", "med_schedule_id": str(sched.id)},
        llm_flags={"relief": "medication"},
    )


async def delete_slot_rule(db: AsyncSession, rule: LockSlotRule) -> None:
    await db.delete(rule)
    await db.flush()


async def delete_task_rule(db: AsyncSession, rule: LockTaskRule) -> None:
    await db.delete(rule)
    await db.flush()


async def reorder_rules(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
    kind: str,  # "slot" or "task"
    rule_ids: list[uuid.UUID],
) -> None:
    """Reorder slot/task rules of a draft session by the given id order.

    Validates that every provided id belongs to the session and that the set
    of ids matches the current rules exactly, then rewrites sort_order to
    match the requested sequence. Writes an audit event.
    """
    session = await get_session(db, session_id, owner_id)
    if session is None:
        raise ValueError("Session not found")
    if session.state != e.SESSION_DRAFT:
        raise ValueError("Only draft sessions can be reordered")

    if kind == "slot":
        model = LockSlotRule
        object_type = "lock_slot_rule"
        event_type = "locktimer.slot_rules.reordered"
    elif kind == "task":
        model = LockTaskRule
        object_type = "lock_task_rule"
        event_type = "locktimer.task_rules.reordered"
    else:
        raise ValueError(f"Unknown rule kind: {kind}")

    result = await db.execute(select(model).where(model.session_id == session_id))
    existing = list(result.scalars().all())
    existing_ids = {rule.id for rule in existing}

    if not rule_ids:
        raise ValueError("Rule list must not be empty")
    if len(rule_ids) != len(set(rule_ids)):
        raise ValueError("Duplicate rule ids in reorder request")
    if set(rule_ids) != existing_ids:
        raise ValueError("Rule list must contain exactly the session's current rules")

    by_id = {rule.id: rule for rule in existing}
    for position, rule_id in enumerate(rule_ids):
        by_id[rule_id].sort_order = position

    await write_audit(
        db,
        session_id=session_id,
        actor_type="user",
        actor_user_id=owner_id,
        event_type=event_type,
        object_type=object_type,
        object_id=session_id,
        payload={"rule_ids": [str(r) for r in rule_ids]},
    )
    await db.flush()
