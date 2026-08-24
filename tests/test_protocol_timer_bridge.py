"""Integration tests: Protocol ↔ Timer bridge (R5.4 / ADR-155)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.locktimer import LockSession
from app.models.protocol import (
    ProtocolAnchorType,
    ProtocolDefinition,
    ProtocolRun,
    ProtocolStep,
    ProtocolStepType,
)
from app.models.user import User
from app.services.protocol import (
    complete_runs_for_timer_event,
    create_protocol_runs_for_timer_event,
)


@pytest.mark.asyncio
async def test_create_prep_protocol_on_timer_start(db_session: AsyncSession, test_user: User):
    """Prep protocols are launched when a timer session starts."""
    now = datetime.now(UTC)

    # Create timer session
    session = LockSession(
        owner_id=test_user.id,
        state="active",
        timezone="UTC",
        random_seed_encrypted="test",
        random_seed_commitment="test",
        started_at=now,
    )
    db_session.add(session)
    await db_session.flush()

    # Create a timer_bound prep protocol
    proto = ProtocolDefinition(
        user_id=test_user.id,
        title="Pre-Session Prep",
        category="prep",
        anchor_type=ProtocolAnchorType.TIMER_BOUND.value,
        is_active=True,
    )
    db_session.add(proto)
    await db_session.flush()

    # Add a step
    step = ProtocolStep(
        protocol_id=proto.id,
        step_order=1,
        title="Apply gel",
        step_type=ProtocolStepType.CARE.value,
        timing_spec={"type": "rel_before", "offset_seconds": 900},
    )
    db_session.add(step)
    await db_session.flush()

    # Trigger the bridge
    runs = await create_protocol_runs_for_timer_event(
        db=db_session,
        user_id=test_user.id,
        lock_session_id=session.id,
        anchor_time=now,
        category_filter="prep",
    )

    assert len(runs) == 1
    run = runs[0]
    assert run.status == "active"
    assert run.lock_session_id == session.id
    assert len(run.frozen_steps_snapshot) == 1


@pytest.mark.asyncio
async def test_create_recovery_protocol_on_timer_stop(db_session: AsyncSession, test_user: User):
    """Recovery protocols are launched when a timer session stops."""
    now = datetime.now(UTC)

    session = LockSession(
        owner_id=test_user.id,
        state="safety_stopped",
        timezone="UTC",
        random_seed_encrypted="test",
        random_seed_commitment="test",
        started_at=now - timedelta(hours=4),
        safety_stopped_at=now,
    )
    db_session.add(session)
    await db_session.flush()

    proto = ProtocolDefinition(
        user_id=test_user.id,
        title="Post-Session Recovery",
        category="recovery",
        anchor_type=ProtocolAnchorType.TIMER_BOUND.value,
        is_active=True,
    )
    db_session.add(proto)
    await db_session.flush()

    step = ProtocolStep(
        protocol_id=proto.id,
        step_order=1,
        title="Hydrate",
        step_type=ProtocolStepType.CARE.value,
        timing_spec={"type": "rel_after", "offset_seconds": 300},
    )
    db_session.add(step)
    await db_session.flush()

    runs = await create_protocol_runs_for_timer_event(
        db=db_session,
        user_id=test_user.id,
        lock_session_id=session.id,
        anchor_time=now,
        category_filter="recovery",
    )

    assert len(runs) == 1
    assert runs[0].status == "active"
    assert runs[0].lock_session_id == session.id


@pytest.mark.asyncio
async def test_no_protocols_silently_skipped(db_session: AsyncSession, test_user: User):
    """When no timer_bound protocols exist, bridge does nothing."""
    now = datetime.now(UTC)

    session = LockSession(
        owner_id=test_user.id,
        state="active",
        timezone="UTC",
        random_seed_encrypted="test",
        random_seed_commitment="test",
        started_at=now,
    )
    db_session.add(session)
    await db_session.flush()

    # No protocols exist — should return empty list, not error
    runs = await create_protocol_runs_for_timer_event(
        db=db_session,
        user_id=test_user.id,
        lock_session_id=session.id,
        anchor_time=now,
        category_filter="prep",
    )
    assert runs == []


@pytest.mark.asyncio
async def test_complete_runs_aborts_active(db_session: AsyncSession, test_user: User):
    """complete_runs_for_timer_event aborts active runs on safety stop."""
    now = datetime.now(UTC)

    session = LockSession(
        owner_id=test_user.id,
        state="safety_stopped",
        timezone="UTC",
        random_seed_encrypted="test",
        random_seed_commitment="test",
        started_at=now - timedelta(hours=2),
        safety_stopped_at=now,
    )
    db_session.add(session)
    await db_session.flush()

    proto = ProtocolDefinition(
        user_id=test_user.id,
        title="Prep",
        category="prep",
        anchor_type=ProtocolAnchorType.TIMER_BOUND.value,
    )
    db_session.add(proto)
    await db_session.flush()

    db_session.add(ProtocolStep(protocol_id=proto.id, step_order=1, title="S1", timing_spec={}))
    await db_session.flush()

    # Manually create an active run (simulating it was started on session start)
    run = ProtocolRun(
        user_id=test_user.id,
        protocol_id=proto.id,
        lock_session_id=session.id,
        anchor_time=now - timedelta(hours=2),
        status="active",
        frozen_steps_snapshot=[{"id": "s1", "step_order": 1, "title": "S1"}],
        started_at=now - timedelta(hours=2),
    )
    db_session.add(run)
    await db_session.flush()

    # Bridge: complete active runs
    completed = await complete_runs_for_timer_event(
        db=db_session,
        lock_session_id=session.id,
    )
    assert len(completed) == 1
    assert completed[0].status == "aborted"