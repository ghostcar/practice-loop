"""LockTimer materializer — C4: occurrence generation for slot and task rules."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import domain as d
from app.locktimer import enums as e
from app.models.locktimer import (
    LockSession,
    LockSlotOccurrence,
    LockSlotRule,
    LockTaskOccurrence,
    LockTaskRule,
)
from app.timeutils import as_utc


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


async def _materialize_session(
    db: AsyncSession,
    session: LockSession,
    slot_rules: list[LockSlotRule],
    task_rules: list[LockTaskRule],
    now: datetime,
) -> None:
    """Generate initial occurrence window for all rules (C4 — rolling horizon)."""
    now = as_utc(now)
    effective_end = as_utc(session.effective_end_at) if session.effective_end_at is not None else None
    horizon_end = now + timedelta(days=d.DEFAULT_ROLLING_HORIZON_DAYS)
    if effective_end is not None and horizon_end > effective_end:
        horizon_end = effective_end

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
    effective_end = as_utc(session.effective_end_at) if session.effective_end_at is not None else None
    idx = 0

    if rule.rule_type == e.SLOT_RULE_EVERY_N_DAYS:
        n = schedule.get("n", 1)
        start_date = _parse_date(schedule.get("start_date"), from_dt)
        time_of_day = schedule.get("time_of_day", "12:00")
        current = _combine_date_time(start_date, time_of_day)
        while current < from_dt:
            current += timedelta(days=n)
        while current < to_dt and (effective_end is None or current < effective_end):
            if _in_progress_check(current, from_dt, effective_end):
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
        while current < to_dt and (effective_end is None or current < effective_end):
            if _in_progress_check(current, from_dt, effective_end):
                occ = _make_slot_occ(session, rule, idx, current, current + timedelta(seconds=rule.duration_seconds))
                occurrences.append(occ)
                idx += 1
            current += timedelta(days=n)

    elif rule.rule_type == e.SLOT_RULE_FLEXIBLE_WINDOW_ONCE:
        window_start = as_utc(_parse_date(schedule.get("window_start"), from_dt))
        window_end = as_utc(_parse_date(schedule.get("window_end"), to_dt))
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
    effective_end = as_utc(session.effective_end_at) if session.effective_end_at is not None else None
    idx = 0

    if rule.schedule_type == e.TASK_SCHED_DAILY:
        time_of_day = schedule.get("time_of_day", "09:00")
        current = _combine_date_time(from_dt.date(), time_of_day)
        while current < to_dt and (effective_end is None or current < effective_end):
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
        while current < to_dt and (effective_end is None or current < effective_end):
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
        end = effective_end or to_dt
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
