"""Protocol Execution Engine & Step Handlers (Ports & Adapters / Revision 2).

Orchestrates multi-step routines (preparation, recovery, care sequences, routines)
connecting activities, medications, and care routines with typed timing schemas.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.protocol import (
    ProtocolAnchorType,
    ProtocolDefinition,
    ProtocolRun,
    ProtocolStep,
    ProtocolStepLog,
    ProtocolStepType,
    TimingSpecType,
)
from app.services.capability import ActorContext

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Ports & Adapters: Step Handler Interface & Registry
# ─────────────────────────────────────────────────────────────────────────────


class ProtocolStepHandler(Protocol):
    """Port for handling execution of a specific step type."""

    async def execute(
        self,
        db: AsyncSession,
        step_log: ProtocolStepLog,
        step_params: dict[str, Any],
        actor: ActorContext,
    ) -> dict[str, Any]:
        """Execute step and return result payload."""
        ...


class ActivityStepHandler:
    """Adapter creating an ActivityLog entry when a protocol activity step executes."""

    async def execute(
        self,
        db: AsyncSession,
        step_log: ProtocolStepLog,
        step_params: dict[str, Any],
        actor: ActorContext,
    ) -> dict[str, Any]:
        from app.models.activity_log import ActivityLog
        from app.models.task_status import COMPLETED

        # Create activity log record
        log = ActivityLog(
            user_id=actor.actor_id,
            entity_id=step_params.get("reference_id"),
            status=COMPLETED,
            selected_entity_name=step_log.step_title,
            selected_params=step_params.get("custom_params", {}),
            user_prompt=f"Protocol Step: {step_log.step_title}",
        )
        db.add(log)
        await db.flush()
        return {"activity_log_id": str(log.id), "status": "completed"}


class MedicationStepHandler:
    """Adapter logging medication intake when a protocol step executes."""

    async def execute(
        self,
        db: AsyncSession,
        step_log: ProtocolStepLog,
        step_params: dict[str, Any],
        actor: ActorContext,
    ) -> dict[str, Any]:
        from app.models.activity_log import ActivityLog
        from app.models.task_status import COMPLETED

        custom_params = step_params.get("custom_params", {})
        log = ActivityLog(
            user_id=actor.actor_id,
            status=COMPLETED,
            selected_entity_name=f"Медикамент: {step_log.step_title}",
            selected_params={"dosage": custom_params.get("amount", "standard"), "protocol_step": step_log.step_title},
            user_prompt=f"Protocol Med Step: {step_log.step_title}",
        )
        db.add(log)
        await db.flush()
        return {"medication_log_id": str(log.id), "status": "completed", "amount": custom_params.get("amount")}


class CareStepHandler:
    """Adapter logging body care / skincare routines when executed."""

    async def execute(
        self,
        db: AsyncSession,
        step_log: ProtocolStepLog,
        step_params: dict[str, Any],
        actor: ActorContext,
    ) -> dict[str, Any]:
        from app.models.activity_log import ActivityLog
        from app.models.task_status import COMPLETED

        custom_params = step_params.get("custom_params", {})
        log = ActivityLog(
            user_id=actor.actor_id,
            status=COMPLETED,
            selected_entity_name=f"Уход: {step_log.step_title}",
            selected_params={"duration": custom_params.get("duration_sec", 300), "notes": custom_params.get("notes")},
            user_prompt=f"Protocol Care Step: {step_log.step_title}",
        )
        db.add(log)
        await db.flush()
        return {"care_log_id": str(log.id), "status": "completed"}


class MeasurementStepHandler:
    """Adapter recording physiological or body measurements."""

    async def execute(
        self,
        db: AsyncSession,
        step_log: ProtocolStepLog,
        step_params: dict[str, Any],
        actor: ActorContext,
    ) -> dict[str, Any]:
        from app.models.activity_log import ActivityLog
        from app.models.task_status import COMPLETED

        custom_params = step_params.get("custom_params", {})
        log = ActivityLog(
            user_id=actor.actor_id,
            status=COMPLETED,
            selected_entity_name=f"Замер: {step_log.step_title}",
            selected_params={"metric_value": custom_params.get("value"), "unit": custom_params.get("unit", "cm")},
            user_prompt=f"Protocol Measurement Step: {step_log.step_title}",
        )
        db.add(log)
        await db.flush()
        return {"measurement_log_id": str(log.id), "status": "completed"}


class PhotoCheckinHandler:
    """Adapter recording media verification drop."""

    async def execute(
        self,
        db: AsyncSession,
        step_log: ProtocolStepLog,
        step_params: dict[str, Any],
        actor: ActorContext,
    ) -> dict[str, Any]:
        from app.models.activity_log import ActivityLog
        from app.models.task_status import COMPLETED

        custom_params = step_params.get("custom_params", {})
        log = ActivityLog(
            user_id=actor.actor_id,
            status=COMPLETED,
            selected_entity_name=f"Фото-верификация: {step_log.step_title}",
            selected_params={"media_type": custom_params.get("media_type", "checkin_photo")},
            user_prompt=f"Protocol Photo Checkin: {step_log.step_title}",
        )
        db.add(log)
        await db.flush()
        return {"photo_checkin_id": str(log.id), "status": "completed"}


class TimerActionHandler:
    """Adapter executing timer or chastity lock commands."""

    async def execute(
        self,
        db: AsyncSession,
        step_log: ProtocolStepLog,
        step_params: dict[str, Any],
        actor: ActorContext,
    ) -> dict[str, Any]:
        from app.models.activity_log import ActivityLog
        from app.models.task_status import COMPLETED

        custom_params = step_params.get("custom_params", {})
        log = ActivityLog(
            user_id=actor.actor_id,
            status=COMPLETED,
            selected_entity_name=f"Таймер / Замок: {step_log.step_title}",
            selected_params={
                "action": custom_params.get("action", "checkin"),
                "duration_min": custom_params.get("duration_min", 0),
            },
            user_prompt=f"Protocol Timer Step: {step_log.step_title}",
        )
        db.add(log)
        await db.flush()
        return {"timer_log_id": str(log.id), "status": "completed"}


class GenericStepHandler:
    """Default fallback handler for informational and manual steps."""

    async def execute(
        self,
        db: AsyncSession,
        step_log: ProtocolStepLog,
        step_params: dict[str, Any],
        actor: ActorContext,
    ) -> dict[str, Any]:
        return {"status": "completed", "executed_by": str(actor.actor_id)}


# Registry mapping step types to handler adapters
STEP_HANDLERS: dict[str, ProtocolStepHandler] = {
    ProtocolStepType.ACTIVITY.value: ActivityStepHandler(),
    ProtocolStepType.MEDICATION.value: MedicationStepHandler(),
    ProtocolStepType.CARE.value: CareStepHandler(),
    ProtocolStepType.MEASUREMENT.value: MeasurementStepHandler(),
    ProtocolStepType.PHOTO_CHECKIN.value: PhotoCheckinHandler(),
    ProtocolStepType.TIMER_ACTION.value: TimerActionHandler(),
}


def register_step_handler(step_type: str, handler: ProtocolStepHandler) -> None:
    """Pluggable adapter registration for custom protocol step types."""
    STEP_HANDLERS[step_type] = handler


# ─────────────────────────────────────────────────────────────────────────────
# Protocol Engine Services
# ─────────────────────────────────────────────────────────────────────────────


def compute_step_planned_time(
    anchor_time: datetime.datetime,
    timing_spec: dict[str, Any],
    prev_time: datetime.datetime | None = None,
) -> datetime.datetime:
    """Compute exact planned execution datetime based on typed timing spec."""
    spec_type = timing_spec.get("type", TimingSpecType.REL_ANCHOR_BEFORE.value)
    offset_seconds = int(timing_spec.get("offset_seconds", 0))

    if spec_type == TimingSpecType.REL_ANCHOR_BEFORE.value:
        return anchor_time - datetime.timedelta(seconds=offset_seconds)
    elif spec_type == TimingSpecType.REL_ANCHOR_AFTER.value:
        return anchor_time + datetime.timedelta(seconds=offset_seconds)
    elif spec_type == TimingSpecType.AFTER_PREV_STEP.value and prev_time is not None:
        return prev_time + datetime.timedelta(seconds=offset_seconds)
    elif spec_type == TimingSpecType.DAILY.value:
        hour = int(timing_spec.get("hour", 9))
        minute = int(timing_spec.get("minute", 0))
        return anchor_time.replace(hour=hour, minute=minute, second=0, microsecond=0)
    elif spec_type == TimingSpecType.ABSOLUTE.value and "datetime" in timing_spec:
        return datetime.datetime.fromisoformat(timing_spec["datetime"])

    return anchor_time


async def create_protocol_definition(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    description: str | None = None,
    category: str = "prep",
    anchor_type: str = "session_bound",
    steps: list[dict[str, Any]] | None = None,
) -> ProtocolDefinition:
    """Create a new reusable protocol definition with ordered steps."""
    step_objs: list[ProtocolStep] = []
    if steps:
        for idx, s in enumerate(steps, start=1):
            ref_id = uuid.UUID(s["reference_id"]) if s.get("reference_id") else None
            step = ProtocolStep(
                step_order=idx,
                title=s["title"],
                step_type=s.get("step_type", ProtocolStepType.ACTIVITY.value),
                reference_id=ref_id,
                timing_spec=s.get("timing_spec", {}),
                custom_params=s.get("custom_params", {}),
            )
            step_objs.append(step)

    proto = ProtocolDefinition(
        user_id=user_id,
        title=title,
        description=description,
        category=category,
        anchor_type=anchor_type,
        steps=step_objs,
    )
    db.add(proto)
    await db.flush()
    return proto


async def start_protocol_run(
    db: AsyncSession,
    user_id: uuid.UUID,
    protocol_id: uuid.UUID,
    anchor_time: datetime.datetime,
    session_id: uuid.UUID | None = None,
    lock_session_id: uuid.UUID | None = None,
) -> ProtocolRun:
    """Launch an active protocol run with frozen step rules snapshot and planned timestamps."""
    res = await db.execute(select(ProtocolDefinition).where(ProtocolDefinition.id == protocol_id))
    proto = res.scalar_one_or_none()
    if proto is None:
        raise ValueError(f"ProtocolDefinition {protocol_id} not found")

    # Load steps in order
    steps_res = await db.execute(
        select(ProtocolStep).where(ProtocolStep.protocol_id == protocol_id).order_by(ProtocolStep.step_order)
    )
    steps = steps_res.scalars().all()

    # Create immutable snapshot of steps
    snapshot = [
        {
            "id": str(s.id),
            "step_order": s.step_order,
            "title": s.title,
            "step_type": s.step_type,
            "reference_id": str(s.reference_id) if s.reference_id else None,
            "timing_spec": s.timing_spec,
            "custom_params": s.custom_params,
        }
        for s in steps
    ]

    run = ProtocolRun(
        user_id=user_id,
        protocol_id=protocol_id,
        session_id=session_id,
        lock_session_id=lock_session_id,
        anchor_time=anchor_time,
        status="active",
        frozen_steps_snapshot=snapshot,
        started_at=datetime.datetime.now(datetime.UTC),
    )
    db.add(run)
    await db.flush()

    # Generate planned StepLogs
    prev_time: datetime.datetime | None = None
    for s in steps:
        planned_dt = compute_step_planned_time(anchor_time, s.timing_spec, prev_time)
        prev_time = planned_dt

        step_log = ProtocolStepLog(
            run_id=run.id,
            step_id=s.id,
            step_title=s.title,
            step_type=s.step_type,
            planned_at=planned_dt,
            status="pending",
        )
        db.add(step_log)

    await db.flush()
    return run


async def execute_protocol_step(
    db: AsyncSession,
    step_log_id: uuid.UUID,
    actor: ActorContext,
    result_payload: dict[str, Any] | None = None,
) -> ProtocolStepLog:
    """Execute and verify a protocol step via its registered handler adapter."""
    res = await db.execute(select(ProtocolStepLog).where(ProtocolStepLog.id == step_log_id))
    step_log = res.scalar_one_or_none()
    if step_log is None:
        raise ValueError(f"ProtocolStepLog {step_log_id} not found")

    handler = STEP_HANDLERS.get(step_log.step_type, GenericStepHandler())
    step_params = result_payload or {}

    exec_result = await handler.execute(db, step_log, step_params, actor)

    step_log.executed_at = datetime.datetime.now(datetime.UTC)
    step_log.status = "completed"
    step_log.result_payload = exec_result
    step_log.actor_context = {
        "actor_id": str(actor.actor_id),
        "actor_type": actor.actor_type,
        "source": actor.source,
    }

    # Check if all steps in this run are completed
    run_res = await db.execute(select(ProtocolRun).where(ProtocolRun.id == step_log.run_id))
    run = run_res.scalar_one_or_none()
    if run is not None:
        all_logs_res = await db.execute(select(ProtocolStepLog).where(ProtocolStepLog.run_id == run.id))
        all_logs = all_logs_res.scalars().all()
        if all(log.status == "completed" for log in all_logs):
            run.status = "completed"
            run.completed_at = datetime.datetime.now(datetime.UTC)

    await db.flush()
    return step_log


# ─────────────────────────────────────────────────────────────────────────────
# Timer ↔ Protocol bridge (R5.4 / ADR-155)
# ─────────────────────────────────────────────────────────────────────────────


async def create_protocol_runs_for_timer_event(
    db: AsyncSession,
    user_id: uuid.UUID,
    lock_session_id: uuid.UUID,
    anchor_time: datetime.datetime,
    *,
    category_filter: str = "prep",
) -> list[ProtocolRun]:
    """Launch all active timer_bound protocols matching the event category.

    Called when a timer session starts (prep) or completes/stops (recovery).
    Does nothing if no matching protocols exist — timer operates unchanged.
    """
    result = await db.execute(
        select(ProtocolDefinition).where(
            ProtocolDefinition.user_id == user_id,
            ProtocolDefinition.anchor_type == ProtocolAnchorType.TIMER_BOUND.value,
            ProtocolDefinition.category == category_filter,
            ProtocolDefinition.is_active.is_(True),
        )
    )
    definitions = result.scalars().all()

    runs: list[ProtocolRun] = []
    for proto in definitions:
        run = await start_protocol_run(
            db=db,
            user_id=user_id,
            protocol_id=proto.id,
            anchor_time=anchor_time,
            lock_session_id=lock_session_id,
        )
        runs.append(run)
        logger.info(
            "Protocol '%s' (%s) started for timer session %s",
            proto.title, category_filter, lock_session_id,
        )

    return runs


async def complete_runs_for_timer_event(
    db: AsyncSession,
    lock_session_id: uuid.UUID,
) -> list[ProtocolRun]:
    """Finish all active protocol runs attached to this timer session.

    Active runs → aborted (timer stopped before completion).
    Completed runs are left alone.
    """
    result = await db.execute(
        select(ProtocolRun).where(
            ProtocolRun.lock_session_id == lock_session_id,
            ProtocolRun.status.in_(["active", "scheduled"]),
        )
    )
    runs = result.scalars().all()

    for run in runs:
        run.status = "aborted"
        run.completed_at = datetime.datetime.now(datetime.UTC)
        # Mark any pending step logs as skipped
        step_res = await db.execute(
            select(ProtocolStepLog).where(
                ProtocolStepLog.run_id == run.id,
                ProtocolStepLog.status == "pending",
            )
        )
        for log in step_res.scalars().all():
            log.status = "skipped"

    if runs:
        await db.flush()
        logger.info("Aborted %d protocol run(s) for timer session %s", len(runs), lock_session_id)

    return runs
