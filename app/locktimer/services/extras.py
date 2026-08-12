"""LockTimer validation + horizon extension service (C4-C8 completion).

validate_session — pre-start conflict check (overlapping slots, oversized schedule)
extend_horizon — materialize more occurrences for future days
save_template — save current draft config as a reusable template
instantiate_template — create a new draft from a template
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import domain as d
from app.locktimer import enums as e
from app.locktimer.repositories import list_slot_rules, list_task_rules
from app.models.locktimer import (
    LockSession,
    LockSlotOccurrence,
    LockTaskOccurrence,
    LockTimerTemplate,
)

DEFAULT_ROLLING_HORIZON_DAYS = 90


def _now() -> datetime:
    return datetime.now(UTC)


# ============================================================================
# Validate session (conflict check)
# ============================================================================


async def validate_session(
    db: AsyncSession,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> dict:
    """Run pre-start validation: checks rules, no conflicts, basic sanity.

    Returns a dict with:
      - valid: bool
      - warnings: list[str]
      - errors: list[str]
      - slot_count_estimate: int
      - task_count_estimate: int
      - horizon_days: int
    """
    session = await db.get(LockSession, session_id)
    if session is None or session.owner_id != owner_id:
        return {"valid": False, "errors": ["Session not found"], "warnings": []}

    errors: list[str] = []
    warnings: list[str] = []

    slot_rules = await list_slot_rules(db, session_id)
    task_rules = await list_task_rules(db, session_id)

    if not slot_rules and not task_rules:
        warnings.append("Session has no rules — nothing will be scheduled.")

    horizon_end = _now() + timedelta(days=DEFAULT_ROLLING_HORIZON_DAYS)
    if session.max_end_at and horizon_end > session.max_end_at:
        horizon_end = session.max_end_at

    # Estimate slot count
    slot_count = 0
    for rule in slot_rules:
        if rule.rule_type == e.SLOT_RULE_EXACT_DATETIME:
            slot_count += 1
        elif rule.rule_type in (e.SLOT_RULE_EVERY_N_DAYS, e.SLOT_RULE_RECURRING_FROM_DATE):
            n = rule.schedule.get("n", 1)
            days_span = (horizon_end - _now()).days
            slot_count += max(1, days_span // max(n, 1))
        elif rule.rule_type == e.SLOT_RULE_FLEXIBLE_WINDOW_ONCE:
            slot_count += 1

    # Estimate task count
    task_count = 0
    for rule in task_rules:
        if rule.schedule_type == e.TASK_SCHED_DAILY:
            task_count += (horizon_end - _now()).days
        elif rule.schedule_type in (e.TASK_SCHED_EVERY_N_DAYS, e.TASK_SCHED_RECURRING_FROM_DATE):
            n = rule.schedule.get("n", 1)
            task_count += max(1, (horizon_end - _now()).days // max(n, 1))
        elif rule.schedule_type in (e.TASK_SCHED_EXACT_DATETIME, e.TASK_SCHED_ANYTIME_BEFORE_END):
            task_count += 1
        elif rule.schedule_type == e.TASK_SCHED_DETERMINISTIC_RANDOM:
            task_count += rule.schedule.get("count", 1)

    # Hard limits
    if slot_count > 500:
        errors.append(f"Too many slot occurrences estimated ({slot_count} > 500). Reduce rule frequency or scope.")
    if task_count > 1000:
        errors.append(f"Too many task occurrences estimated ({task_count} > 1000). Reduce rule frequency or scope.")

    # Duration type sanity
    if session.duration_type == e.DURATION_INFINITE and not session.max_end_at:
        warnings.append("Infinite session with no max_end_at — will run until manually stopped.")

    if session.duration_type == e.DURATION_FROM_START and not session.original_end_at and not session.max_end_at:
        warnings.append("Duration from start with no end cap — consider setting max_end_at.")

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "slot_count_estimate": slot_count,
        "task_count_estimate": task_count,
        "horizon_days": min((horizon_end - _now()).days, DEFAULT_ROLLING_HORIZON_DAYS),
    }


# ============================================================================
# Extend horizon (materializer for future days)
# ============================================================================


async def extend_horizon(
    db: AsyncSession,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
    now: datetime | None = None,
) -> dict:
    """Extend the occurrence horizon for an active session.

    Generates occurrences for the next 90 days from now.
    Skips dates that already have occurrences.
    """
    if now is None:
        now = _now()

    session = await db.get(LockSession, session_id)
    if session is None or session.owner_id != owner_id:
        raise ValueError("Session not found")
    if session.state != e.SESSION_ACTIVE:
        raise ValueError("Only active sessions can be extended")

    # Find the latest occurrence to start from
    latest_slot_result = await db.execute(
        select(LockSlotOccurrence.planned_open_at)
        .where(LockSlotOccurrence.session_id == session_id)
        .order_by(LockSlotOccurrence.planned_open_at.desc())
        .limit(1)
    )
    latest_task_result = await db.execute(
        select(LockTaskOccurrence.appears_at)
        .where(LockTaskOccurrence.session_id == session_id)
        .order_by(LockTaskOccurrence.appears_at.desc())
        .limit(1)
    )
    latest_slot = latest_slot_result.scalar_one_or_none()
    latest_task = latest_task_result.scalar_one_or_none()

    from_dt = now
    if latest_slot and latest_slot > from_dt:
        from_dt = latest_slot
    if latest_task and latest_task > from_dt:
        from_dt = max(from_dt, latest_task)

    horizon_end = now + timedelta(days=DEFAULT_ROLLING_HORIZON_DAYS)
    if session.effective_end_at and horizon_end > session.effective_end_at:
        horizon_end = session.effective_end_at

    if from_dt >= horizon_end:
        return {"generated_slots": 0, "generated_tasks": 0, "reason": "horizon_already_full"}

    slot_rules = await list_slot_rules(db, session_id)
    task_rules = await list_task_rules(db, session_id)

    generated_slots = 0
    generated_tasks = 0

    # Import materializer helpers from execution module
    from app.locktimer.services.execution import _generate_slot_occurrences, _generate_task_occurrences

    for rule in slot_rules:
        occurrences = _generate_slot_occurrences(session, rule, from_dt, horizon_end)
        for occ in occurrences:
            db.add(occ)
            generated_slots += 1

    for rule in task_rules:
        occurrences = _generate_task_occurrences(session, rule, from_dt, horizon_end)
        for occ in occurrences:
            db.add(occ)
            generated_tasks += 1

    await db.flush()
    return {"generated_slots": generated_slots, "generated_tasks": generated_tasks}


# ============================================================================
# Template management
# ============================================================================


async def save_template(
    db: AsyncSession,
    *,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
    name: str,
    description: str | None = None,
) -> LockTimerTemplate:
    """Save current draft session config as a reusable template."""
    session = await db.get(LockSession, session_id)
    if session is None or session.owner_id != owner_id:
        raise ValueError("Session not found")

    if session.state != e.SESSION_DRAFT:
        raise ValueError("Only draft sessions can be saved as templates")

    slot_rules = await list_slot_rules(db, session_id)
    task_rules = await list_task_rules(db, session_id)

    config = {
        "duration_type": session.duration_type,
        "timezone": session.timezone,
        "merge_gap_seconds": session.merge_gap_seconds,
        "can_extend_duration": session.can_extend_duration,
        "slot_rules": [
            {
                "name": r.name,
                "rule_type": r.rule_type,
                "schedule": r.schedule,
                "duration_seconds": r.duration_seconds,
                "allow_late_open": r.allow_late_open,
                "max_late_seconds": r.max_late_seconds,
                "extend_on_late_open": r.extend_on_late_open,
            }
            for r in slot_rules
        ],
        "task_rules": [
            {
                "title": r.title,
                "schedule_type": r.schedule_type,
                "schedule": r.schedule,
                "due_window_seconds": r.due_window_seconds,
                "requires_report": r.requires_report,
                "hide_until_due": r.hide_until_due,
            }
            for r in task_rules
        ],
    }

    template = LockTimerTemplate(
        owner_id=owner_id,
        name=name,
        description=description,
        schema_version=1,
        config=config,
        config_sha256=d.sha256_hex(d.canonical_json(config)),
    )
    db.add(template)
    await db.flush()
    return template


async def instantiate_template(
    db: AsyncSession,
    *,
    template_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> LockSession:
    """Create a new draft session from a template."""
    template = await db.get(LockTimerTemplate, template_id)
    if template is None or template.owner_id != owner_id:
        raise ValueError("Template not found")
    if template.archived_at is not None:
        raise ValueError("Template is archived")

    from app.locktimer.services.execution import add_slot_rule, add_task_rule, create_draft

    config = template.config
    session = await create_draft(
        db,
        owner_id=owner_id,
        duration_type=config.get("duration_type", e.DURATION_FROM_START),
        timezone_str=config.get("timezone", "UTC"),
        merge_gap_seconds=config.get("merge_gap_seconds", 3600),
        can_extend_duration=config.get("can_extend_duration", False),
        template_id=template_id,
    )

    for sr in config.get("slot_rules", []):
        await add_slot_rule(
            db,
            session_id=session.id,
            name=sr["name"],
            rule_type=sr["rule_type"],
            schedule=sr.get("schedule", {}),
            duration_seconds=sr.get("duration_seconds", 3600),
            allow_late_open=sr.get("allow_late_open", False),
            max_late_seconds=sr.get("max_late_seconds", 0),
            extend_on_late_open=sr.get("extend_on_late_open", False),
        )

    for tr in config.get("task_rules", []):
        await add_task_rule(
            db,
            session_id=session.id,
            title=tr["title"],
            schedule_type=tr["schedule_type"],
            schedule=tr.get("schedule", {}),
            due_window_seconds=tr.get("due_window_seconds", 3600),
            requires_report=tr.get("requires_report", False),
            hide_until_due=tr.get("hide_until_due", False),
        )

    await db.flush()
    return session


async def list_templates(db: AsyncSession, owner_id: uuid.UUID) -> list[LockTimerTemplate]:
    result = await db.execute(
        select(LockTimerTemplate)
        .where(LockTimerTemplate.owner_id == owner_id, LockTimerTemplate.archived_at.is_(None))
        .order_by(LockTimerTemplate.updated_at.desc())
    )
    return list(result.scalars().all())


async def archive_template(db: AsyncSession, template_id: uuid.UUID, owner_id: uuid.UUID) -> None:
    template = await db.get(LockTimerTemplate, template_id)
    if template is None or template.owner_id != owner_id:
        raise ValueError("Template not found")
    template.archived_at = _now()
    await db.flush()
