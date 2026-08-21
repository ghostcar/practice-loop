import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.protocol import (
    ProtocolRun,
    ProtocolStep,
    ProtocolStepLog,
    ProtocolStepType,
    TimingSpecType,
)
from app.models.user import User
from app.services.capability import ActorContext
from app.services.protocol import (
    create_protocol_definition,
    execute_protocol_step,
    start_protocol_run,
)


@pytest.mark.asyncio
async def test_protocol_lifecycle_and_step_execution(
    db_session: AsyncSession,
    test_user: User,
):
    actor = ActorContext(actor_id=test_user.id)

    # 1. Create a preparation protocol with 3 steps
    proto = await create_protocol_definition(
        db=db_session,
        user_id=test_user.id,
        title="Протокол подготовки к вечерней сессии",
        description="Гидратация, уход за кожей, разминка",
        category="prep",
        anchor_type="session_bound",
        steps=[
            {
                "title": "Принять витаминный комплекс и воду",
                "step_type": ProtocolStepType.MEDICATION.value,
                "timing_spec": {"type": TimingSpecType.REL_ANCHOR_BEFORE.value, "offset_seconds": 3600},
                "custom_params": {"dose": "500ml water"},
            },
            {
                "title": "Уход за кожей и подготовка зон",
                "step_type": ProtocolStepType.CARE.value,
                "timing_spec": {"type": TimingSpecType.REL_ANCHOR_BEFORE.value, "offset_seconds": 1800},
                "custom_params": {"duration_min": 10},
            },
            {
                "title": "Разминочная планка",
                "step_type": ProtocolStepType.ACTIVITY.value,
                "timing_spec": {"type": TimingSpecType.REL_ANCHOR_BEFORE.value, "offset_seconds": 600},
                "custom_params": {"duration_min": 5},
            },
        ],
    )
    assert proto.id is not None
    steps_check = await db_session.execute(select(ProtocolStep).where(ProtocolStep.protocol_id == proto.id))
    assert len(steps_check.scalars().all()) == 3

    # 2. Start protocol run anchored at T (session start in 2 hours)
    anchor_time = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=2)
    run = await start_protocol_run(
        db=db_session,
        user_id=test_user.id,
        protocol_id=proto.id,
        anchor_time=anchor_time,
    )
    assert run.id is not None
    assert run.status == "active"
    assert len(run.frozen_steps_snapshot) == 3

    # 3. Verify planned step logs
    logs_res = await db_session.execute(
        select(ProtocolStepLog).where(ProtocolStepLog.run_id == run.id).order_by(ProtocolStepLog.planned_at)
    )
    step_logs = logs_res.scalars().all()
    assert len(step_logs) == 3

    # Step 1 should be planned 3600s before anchor
    expected_step1_time = anchor_time - datetime.timedelta(seconds=3600)
    planned_dt = (
        step_logs[0].planned_at.replace(tzinfo=datetime.UTC)
        if step_logs[0].planned_at.tzinfo is None
        else step_logs[0].planned_at
    )
    assert abs((planned_dt - expected_step1_time).total_seconds()) < 2
    assert step_logs[0].status == "pending"

    # 4. Execute Step 1 and Step 2
    await execute_protocol_step(db=db_session, step_log_id=step_logs[0].id, actor=actor)
    await execute_protocol_step(db=db_session, step_log_id=step_logs[1].id, actor=actor)

    # Run is still active
    run_res = await db_session.execute(select(ProtocolRun).where(ProtocolRun.id == run.id))
    current_run = run_res.scalar_one()
    assert current_run.status == "active"

    # 5. Execute Step 3 (Activity step creates ActivityLog)
    await execute_protocol_step(
        db=db_session,
        step_log_id=step_logs[2].id,
        actor=actor,
        result_payload={"custom_params": {"duration_min": 5}},
    )

    # Verify ActivityLog was created by ActivityStepHandler adapter
    act_res = await db_session.execute(
        select(ActivityLog).where(
            ActivityLog.user_id == test_user.id,
            ActivityLog.selected_entity_name.ilike("%Разминочная планка%"),
        )
    )
    act_log = act_res.scalar_one_or_none()
    assert act_log is not None
    assert "Разминочная планка" in act_log.selected_entity_name

    # Verify entire ProtocolRun is now marked completed
    run_res = await db_session.execute(select(ProtocolRun).where(ProtocolRun.id == run.id))
    completed_run = run_res.scalar_one()
    assert completed_run.status == "completed"
    assert completed_run.completed_at is not None
