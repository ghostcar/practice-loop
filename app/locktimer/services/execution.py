"""LockTimer application services — C3 draft/start, C4 materializer, C5 execution.

All services operate within a SQLAlchemy AsyncSession and are owner-scoped.
Domain logic (enums, domain.py) is called but never duplicated here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import domain as d
from app.locktimer import enums as e
from app.locktimer import repositories as repos
from app.locktimer.repositories import (
    get_active_session,
    get_session,
    write_audit,
)
from app.models.locktimer import (
    LockJobReceipt,
    LockOutboxEvent,
    LockPenaltyEvent,
    LockSession,
    LockSessionSnapshot,
    LockSlotOccurrence,
    LockSlotRule,
    LockTagViolation,
    LockTaskOccurrence,
    LockTaskRule,
)

# ============================================================================
# Helpers
# ============================================================================


def _now() -> datetime:
    return datetime.now(UTC)


_NOW = _now()  # snapshot for deterministic materialization in a single call


# ============================================================================
# C3 — Draft Service
# ============================================================================


async def create_draft(
    db: AsyncSession,
    *,
    owner_id: uuid.UUID,
    duration_type: str = e.DURATION_FROM_START,
    timezone_str: str = "UTC",
    merge_gap_seconds: int = d.DEFAULT_MERGE_GAP_SECONDS,
    can_extend_duration: bool = False,
    template_id: uuid.UUID | None = None,
) -> LockSession:
    """Create a new draft session. One active session per owner enforced at start time."""
    now = _now()
    seed = d.generate_random_seed()

    session = LockSession(
        owner_id=owner_id,
        template_id=template_id,
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

    session.updated_at = _now()
    await db.flush()
    return session


# ============================================================================
# C3 — Rule management (slots & tasks in draft)
# ============================================================================


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
    rule = LockSlotRule(
        session_id=session_id,
        client_key=uuid.uuid4(),
        inner_period_id=inner_period_id,
        name=name,
        rule_type=rule_type,
        schedule=schedule,
        duration_seconds=duration_seconds,
        allow_late_open=extra.get("allow_late_open", False),
        max_late_seconds=extra.get("max_late_seconds", 0),
        extend_on_late_open=extra.get("extend_on_late_open", False),
        require_close_media=extra.get("require_close_media", False),
        close_grace_seconds=extra.get("close_grace_seconds", 0),
        late_close_policy=extra.get("late_close_policy"),
        llm_flags=extra.get("llm_flags", {}),
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
    rule = LockTaskRule(
        session_id=session_id,
        client_key=uuid.uuid4(),
        inner_period_id=inner_period_id,
        source_entity_id=source_entity_id,
        title=title,
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


async def delete_slot_rule(db: AsyncSession, rule: LockSlotRule) -> None:
    await db.delete(rule)
    await db.flush()


async def delete_task_rule(db: AsyncSession, rule: LockTaskRule) -> None:
    await db.delete(rule)
    await db.flush()


# ============================================================================
# C3 — Start Service (freeze + snapshot + atomic start)
# ============================================================================


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


def _compute_initial_end(session: LockSession, started_at: datetime) -> datetime | None:
    """Compute effective_end_at from duration_type and original_end_at."""
    if session.original_end_at:
        end = session.original_end_at
        if session.max_end_at and end > session.max_end_at:
            end = session.max_end_at
        return end

    if session.duration_type == e.DURATION_INFINITE:
        return session.max_end_at

    # duration_from_start without original_end_at: use max_end_at as cap
    return session.max_end_at


# ============================================================================
# C4 — Materializer
# ============================================================================


async def _materialize_session(
    db: AsyncSession,
    session: LockSession,
    slot_rules: list[LockSlotRule],
    task_rules: list[LockTaskRule],
    now: datetime,
) -> None:
    """Generate initial occurrence window for all rules (C4 — rolling horizon)."""
    horizon_end = now + timedelta(days=d.DEFAULT_ROLLING_HORIZON_DAYS)
    if session.effective_end_at and horizon_end > session.effective_end_at:
        horizon_end = session.effective_end_at

    for rule in slot_rules:
        occurrences = _generate_slot_occurrences(session, rule, now, horizon_end)
        for occ in occurrences:
            db.add(occ)

    for rule in task_rules:
        occurrences = _generate_task_occurrences(session, rule, now, horizon_end)
        for occ in occurrences:
            db.add(occ)

    await db.flush()


def _generate_slot_occurrences(
    session: LockSession,
    rule: LockSlotRule,
    from_dt: datetime,
    to_dt: datetime,
) -> list[LockSlotOccurrence]:
    """Generate slot occurrences from a rule between from_dt and to_dt."""
    occurrences: list[LockSlotOccurrence] = []
    schedule = rule.schedule
    idx = 0

    if rule.rule_type == e.SLOT_RULE_EVERY_N_DAYS:
        n = schedule.get("n", 1)
        start_date = _parse_date(schedule.get("start_date"), from_dt)
        time_of_day = schedule.get("time_of_day", "12:00")
        current = _combine_date_time(start_date, time_of_day)
        while current < from_dt:
            current += timedelta(days=n)
        while current < to_dt and (session.effective_end_at is None or current < session.effective_end_at):
            if _in_progress_check(current, from_dt, session.effective_end_at):
                occ = _make_slot_occ(session, rule, idx, current, current + timedelta(seconds=rule.duration_seconds))
                occurrences.append(occ)
                idx += 1
            current += timedelta(days=n)

    elif rule.rule_type == e.SLOT_RULE_EXACT_DATETIME:
        dt_str = schedule.get("datetime")
        if dt_str:
            dt = datetime.fromisoformat(dt_str)
            occ = _make_slot_occ(session, rule, idx, dt, dt + timedelta(seconds=rule.duration_seconds))
            occurrences.append(occ)

    elif rule.rule_type == e.SLOT_RULE_RECURRING_FROM_DATE:
        n = schedule.get("n", 1)
        start_date = _parse_date(schedule.get("start_date"), from_dt)
        time_of_day = schedule.get("time_of_day", "12:00")
        current = _combine_date_time(start_date, time_of_day)
        while current < from_dt:
            current += timedelta(days=n)
        while current < to_dt and (session.effective_end_at is None or current < session.effective_end_at):
            if _in_progress_check(current, from_dt, session.effective_end_at):
                occ = _make_slot_occ(session, rule, idx, current, current + timedelta(seconds=rule.duration_seconds))
                occurrences.append(occ)
                idx += 1
            current += timedelta(days=n)

    elif rule.rule_type == e.SLOT_RULE_FLEXIBLE_WINDOW_ONCE:
        window_start = _parse_date(schedule.get("window_start"), from_dt)
        window_end = _parse_date(schedule.get("window_end"), to_dt)
        if window_start < to_dt and window_end > from_dt:
            occ = _make_slot_occ(session, rule, idx, window_start, None)
            occ.eligible_from = window_start
            occ.eligible_until = window_end
            occurrences.append(occ)

    elif rule.rule_type == e.SLOT_RULE_AFTER_PREVIOUS_CLOSE:
        # Placeholder — requires previous occurrence tracking (C4 full impl)
        pass

    return occurrences


def _generate_task_occurrences(
    session: LockSession,
    rule: LockTaskRule,
    from_dt: datetime,
    to_dt: datetime,
) -> list[LockTaskOccurrence]:
    """Generate task occurrences from a rule between from_dt and to_dt."""
    occurrences: list[LockTaskOccurrence] = []
    schedule = rule.schedule
    idx = 0

    if rule.schedule_type == e.TASK_SCHED_DAILY:
        time_of_day = schedule.get("time_of_day", "09:00")
        current = _combine_date_time(from_dt.date(), time_of_day)
        while current < to_dt and (session.effective_end_at is None or current < session.effective_end_at):
            due_at = current + timedelta(seconds=rule.due_window_seconds)
            occ = _make_task_occ(session, rule, idx, current, due_at)
            occurrences.append(occ)
            idx += 1
            current += timedelta(days=1)

    elif rule.schedule_type == e.TASK_SCHED_EVERY_N_DAYS or rule.schedule_type == e.TASK_SCHED_RECURRING_FROM_DATE:
        n = schedule.get("n", 1)
        start_date = _parse_date(schedule.get("start_date"), from_dt)
        time_of_day = schedule.get("time_of_day", "09:00")
        current = _combine_date_time(start_date, time_of_day)
        while current < from_dt:
            current += timedelta(days=n)
        while current < to_dt and (session.effective_end_at is None or current < session.effective_end_at):
            due_at = current + timedelta(seconds=rule.due_window_seconds)
            occ = _make_task_occ(session, rule, idx, current, due_at)
            occurrences.append(occ)
            idx += 1
            current += timedelta(days=n)

    elif rule.schedule_type == e.TASK_SCHED_EXACT_DATETIME:
        dt_str = schedule.get("datetime")
        if dt_str:
            appears = datetime.fromisoformat(dt_str)
            due_at = appears + timedelta(seconds=rule.due_window_seconds)
            occ = _make_task_occ(session, rule, idx, appears, due_at)
            occurrences.append(occ)

    elif rule.schedule_type == e.TASK_SCHED_ANYTIME_BEFORE_END:
        # One task that can be done anytime before session end
        end = session.effective_end_at or to_dt
        due_at = end
        occ = _make_task_occ(session, rule, idx, from_dt, due_at)
        occurrences.append(occ)

    elif rule.schedule_type == e.TASK_SCHED_DETERMINISTIC_RANDOM:
        count = schedule.get("count", 1)
        from_time = schedule.get("from_time", "09:00")
        for i in range(count):
            r = d.deterministic_random(session.random_seed_encrypted, str(rule.id), i)
            day_offset = int(r * (schedule.get("max_days", 7)))
            day = from_dt.date() + timedelta(days=day_offset)
            time_offset = int(r * 3600 * 12)  # spread over 12h window
            appears = datetime.combine(day, datetime.strptime(from_time, "%H:%M").time(), tzinfo=UTC) + timedelta(
                seconds=time_offset
            )
            if appears < from_dt:
                appears = from_dt
            due_at = appears + timedelta(seconds=rule.due_window_seconds)
            occ = _make_task_occ(session, rule, idx, appears, due_at)
            occurrences.append(occ)
            idx += 1

    return occurrences


# ---- Materializer helpers ----


def _parse_date(val, default):
    if val is None:
        return (
            default
            if isinstance(default, datetime)
            else datetime.fromisoformat(str(default))
            if isinstance(default, str)
            else default
        )
    if isinstance(val, str):
        return datetime.fromisoformat(val)
    return val


def _combine_date_time(dt: datetime | datetime.date, time_str: str) -> datetime:
    """Combine a date with a HH:MM time string, returning timezone-aware datetime."""
    h, m = map(int, time_str.split(":"))
    tz = dt.tzinfo or UTC if isinstance(dt, datetime) else UTC
    return datetime(dt.year, dt.month, dt.day, h, m, 0, tzinfo=tz)


def _in_progress_check(occ_start: datetime, now: datetime, end: datetime | None) -> bool:
    """Exclude occurrences that ended before 'now' (catch-up on start)."""
    return end is None or occ_start < end


def _make_slot_occ(
    session: LockSession,
    rule: LockSlotRule,
    idx: int,
    planned_open: datetime,
    planned_close: datetime | None,
) -> LockSlotOccurrence:
    key = d.make_occurrence_key(str(session.id), str(rule.id), idx)
    eligible_until = planned_open + timedelta(seconds=rule.max_late_seconds) if rule.allow_late_open else planned_open
    return LockSlotOccurrence(
        session_id=session.id,
        rule_id=rule.id,
        occurrence_key=key,
        planned_open_at=planned_open,
        planned_close_at=planned_close,
        eligible_from=planned_open,
        eligible_until=eligible_until,
        state=e.SLOT_PENDING,
    )


def _make_task_occ(
    session: LockSession,
    rule: LockTaskRule,
    idx: int,
    appears_at: datetime,
    due_at: datetime,
) -> LockTaskOccurrence:
    key = d.make_occurrence_key(str(session.id), str(rule.id), idx)
    return LockTaskOccurrence(
        session_id=session.id,
        rule_id=rule.id,
        occurrence_key=key,
        appears_at=appears_at,
        due_at=due_at,
        state=e.TASK_SCHEDULED,
        content_visible=not rule.hide_until_due,
        occurrence_snapshot={
            "title": rule.title,
            "description": rule.description,
            "requires_report": rule.requires_report,
        },
    )


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


# ============================================================================
# C5 — Safety Stop
# ============================================================================


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


# ============================================================================
# C5 — Outbox dispatcher
# ============================================================================


async def emit_outbox_event(
    db: AsyncSession,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    event_type: str,
    payload: dict | None = None,
    available_at: datetime | None = None,
) -> LockOutboxEvent:
    """Write a domain event to the outbox (same transaction)."""
    event = LockOutboxEvent(
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        event_type=event_type,
        payload=payload or {},
        state="pending",
        attempts=0,
        available_at=available_at or _now(),
    )
    db.add(event)
    await db.flush()
    return event


# ============================================================================
# C4 — Job runner (PostgreSQL lease-based)
# ============================================================================


async def enqueue_job(
    db: AsyncSession,
    *,
    job_key: str,
    job_type: str,
    payload: dict | None = None,
    run_after: datetime | None = None,
) -> LockJobReceipt:
    """Enqueue a background job (idempotent by job_key)."""
    existing_result = await db.execute(select(LockJobReceipt).where(LockJobReceipt.job_key == job_key))
    existing = existing_result.scalars().first()
    if existing:
        return existing

    job = LockJobReceipt(
        job_key=job_key,
        job_type=job_type,
        payload=payload or {},
        run_after=run_after or _now(),
        state="pending",
    )
    db.add(job)
    await db.flush()
    return job


async def claim_jobs(
    db: AsyncSession,
    *,
    worker_id: str,
    job_types: list[str],
    limit: int = 10,
    lease_seconds: int = 60,
    now: datetime | None = None,
) -> list[LockJobReceipt]:
    """Claim pending jobs using SELECT FOR UPDATE SKIP LOCKED."""
    if now is None:
        now = _now()

    lease_until = now + timedelta(seconds=lease_seconds)

    result = await db.execute(
        select(LockJobReceipt)
        .where(
            LockJobReceipt.state == "pending",
            LockJobReceipt.job_type.in_(job_types),
            LockJobReceipt.run_after <= now,
        )
        .order_by(LockJobReceipt.run_after)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    jobs = list(result.scalars().all())

    for job in jobs:
        job.state = "running"
        job.lease_owner = worker_id
        job.lease_until = lease_until
        job.attempts += 1
        job.updated_at = now

    await db.flush()
    return jobs


# ============================================================================
# Tag verification (numbered tags)
# ============================================================================


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
