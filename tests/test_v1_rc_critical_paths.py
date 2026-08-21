"""Master E2E Regression Suite for Critical Paths (Revision 2 / Release Candidate v1.0).

Tests the complete integrated lifecycle:
1. Fork-on-Opt-In Catalog Personalization
2. Agency V2 Policy & Hard Constraint Validation
3. Capability Authorizer & Actor Context
4. Dynamic Mode Execution & Frozen Snapshot Immutability
5. Multi-Step Protocol Engine with Timed Anchor
6. Pluggable Payment Gateways & Notification Dispatcher
7. Dead Man's Switch Deadline Check
"""

import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.agency import AgencyLevel
from app.models.dead_mans_switch import DeadMansSwitchRule
from app.models.entity import Entity
from app.models.protocol import ProtocolStepType, TimingSpecType
from app.models.user import User
from app.reminders.dms_worker import check_dead_mans_switches
from app.services.adapters.health import get_health_context_provider
from app.services.adapters.notifications import dispatch_notification
from app.services.adapters.payment_gateways import get_payment_gateway
from app.services.adapters.proposal_pipeline import submit_ai_proposal
from app.services.agency import set_user_agency_policy
from app.services.capability import ActorContext, CapabilityAuthorizer
from app.services.dynamic import (
    create_dynamic_definition,
    end_dynamic_run,
    get_active_dynamic_run,
    start_dynamic_run,
)
from app.services.protocol import (
    create_protocol_definition,
    execute_protocol_step,
    start_protocol_run,
)


@pytest.mark.asyncio
async def test_full_v1_rc_critical_path(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
):
    actor = ActorContext(actor_id=test_user.id, actor_type="owner_manual", source="web")

    # -------------------------------------------------------------------------
    # Step 1: Fork-on-Opt-In Catalog Personalization
    # -------------------------------------------------------------------------
    base_entity = Entity(
        type="task",
        category="general",
        real_name="Эталонная планка",
        owner_id=None,
        is_public=True,
        params_schema={"min_sec": 30, "max_sec": 120},
    )
    db_session.add(base_entity)
    await db_session.flush()

    pers_res = await async_client.post(
        f"/entities/{base_entity.id}/personalize",
        data={
            "custom_name": "Моя персональная планка",
            "duration_min": 10,
            "duration_max": 25,
            "is_opted_in": "true",
        },
        headers=auth_headers,
        follow_redirects=False,
    )
    assert pers_res.status_code == 303
    # Verify customized entity in DB
    fork_res = await db_session.execute(
        select(Entity).where(Entity.owner_id == test_user.id, Entity.parent_id == base_entity.id)
    )
    fork = fork_res.scalar_one_or_none()
    assert fork is not None
    assert fork.params_schema["duration_min"]["min"] == 10
    assert fork.params_schema["duration_min"]["max"] == 25

    # -------------------------------------------------------------------------
    # Step 2: Agency Policy & User Sovereignty
    # -------------------------------------------------------------------------
    await set_user_agency_policy(
        db=db_session,
        user_id=test_user.id,
        domain="sessions",
        default_level=AgencyLevel.PROPOSE_AND_CONFIRM.value,
        constraints={"max_duration_min": 30, "forbidden_tags": ["dangerous"]},
    )
    await db_session.flush()

    # Proposal within bounds -> proposed_pending_confirmation
    valid_prop = await submit_ai_proposal(
        db=db_session,
        user_id=test_user.id,
        domain="sessions",
        operation="start_session",
        action_payload={"duration_min": 25, "tags": ["routine"]},
    )
    assert valid_prop.approved is True
    assert valid_prop.status == "proposed_pending_confirmation"

    # Proposal violating hard bounds -> rejected by gate
    invalid_prop = await submit_ai_proposal(
        db=db_session,
        user_id=test_user.id,
        domain="sessions",
        operation="start_session",
        action_payload={"duration_min": 45, "tags": ["dangerous"]},
    )
    assert invalid_prop.approved is False
    assert invalid_prop.status == "rejected"

    # -------------------------------------------------------------------------
    # Step 3: Capability Authorizer
    # -------------------------------------------------------------------------
    allowed, reason = await CapabilityAuthorizer.can_act(
        db=db_session,
        actor=actor,
        issuer_user_id=test_user.id,
        capability_code="sessions.manage",
    )
    assert allowed is True

    # -------------------------------------------------------------------------
    # Step 4: Multi-Step Protocol Engine
    # -------------------------------------------------------------------------
    proto = await create_protocol_definition(
        db=db_session,
        user_id=test_user.id,
        title="RC Протокол вечерней подготовки",
        description="Гидратация и разминка",
        category="prep",
        anchor_type="session_bound",
        steps=[
            {
                "title": "Гидратация 500мл",
                "step_type": ProtocolStepType.MEDICATION.value,
                "timing_spec": {"type": TimingSpecType.REL_ANCHOR_BEFORE.value, "offset_seconds": 1800},
                "custom_params": {"amount": "500ml"},
            },
            {
                "title": "Персональная разминка",
                "step_type": ProtocolStepType.ACTIVITY.value,
                "reference_id": str(base_entity.id),
                "timing_spec": {"type": TimingSpecType.REL_ANCHOR_BEFORE.value, "offset_seconds": 600},
                "custom_params": {"duration_sec": 45},
            },
        ],
    )
    await db_session.flush()

    anchor = datetime.datetime.now(datetime.UTC) + datetime.timedelta(hours=1)
    run = await start_protocol_run(
        db=db_session,
        user_id=test_user.id,
        protocol_id=proto.id,
        anchor_time=anchor,
    )
    assert run.status == "active"

    from app.models.protocol import ProtocolStepLog

    logs_res = await db_session.execute(
        select(ProtocolStepLog).where(ProtocolStepLog.run_id == run.id).order_by(ProtocolStepLog.planned_at)
    )
    step_logs = logs_res.scalars().all()
    assert len(step_logs) == 2

    # Execute both steps
    await execute_protocol_step(db=db_session, step_log_id=step_logs[0].id, actor=actor)
    await execute_protocol_step(
        db=db_session,
        step_log_id=step_logs[1].id,
        actor=actor,
        result_payload={"custom_params": {"duration_sec": 45}},
    )

    # Verify ActivityLog was recorded
    act_res = await db_session.execute(
        select(ActivityLog).where(
            ActivityLog.user_id == test_user.id,
            ActivityLog.selected_entity_name.ilike("%Персональная разминка%"),
        )
    )
    assert act_res.scalar_one_or_none() is not None

    # ProtocolRun is completed
    await db_session.refresh(run)
    assert run.status == "completed"

    # -------------------------------------------------------------------------
    # Step 5: Dynamic Mode Orchestration & Frozen Snapshot
    # -------------------------------------------------------------------------
    dyn_def = await create_dynamic_definition(
        db=db_session,
        user_id=test_user.id,
        title="RC Марафон дисциплины",
        agency_overlay={"sessions": {"max_duration_min": 20}},
        included_protocol_ids=[str(proto.id)],
        granted_capabilities=["protocols.execute"],
    )
    await db_session.flush()

    dyn_run = await start_dynamic_run(
        db=db_session,
        user_id=test_user.id,
        dynamic_id=dyn_def.id,
        duration_days=7,
    )
    assert dyn_run.status == "active"
    assert dyn_run.frozen_dynamic_snapshot["title"] == "RC Марафон дисциплины"

    active_dyn = await get_active_dynamic_run(db=db_session, user_id=test_user.id)
    assert active_dyn is not None

    await end_dynamic_run(db=db_session, run_id=dyn_run.id)
    active_after = await get_active_dynamic_run(db=db_session, user_id=test_user.id)
    assert active_after is None

    # -------------------------------------------------------------------------
    # Step 6: Health Context Provider & Pluggable Adapters
    # -------------------------------------------------------------------------
    health_prov = get_health_context_provider()
    readiness = await health_prov.get_user_readiness(db=db_session, user_id=test_user.id)
    assert readiness["recovery_score"] == 80

    # Payment Gateway
    gw = get_payment_gateway("mock")
    sess = await gw.create_checkout_session(
        db=db_session,
        user_id=test_user.id,
        amount_cents=2990,
        currency="RUB",
        item_description="RC Tier Subscription",
        return_url="/billing/success",
    )
    assert "mock_sess_" in sess["session_id"]

    # Notification Dispatch
    notif_res = await dispatch_notification(
        db=db_session,
        user_id=test_user.id,
        event_type="rc_test",
        title="Release Candidate Alert",
        message="All critical paths are operational.",
    )
    assert notif_res["in_app"] is True

    # -------------------------------------------------------------------------
    # Step 7: Dead Man's Switch Check
    # -------------------------------------------------------------------------
    dms_rule = DeadMansSwitchRule(
        user_id=test_user.id,
        title="RC Daily DMS",
        switch_type="wear_checkin",
        interval_hours=24,
        status="active",
        is_enabled=True,
        next_deadline_at=datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=5),
    )
    db_session.add(dms_rule)
    await db_session.flush()

    triggered = await check_dead_mans_switches(db_session)
    assert any(t["rule_id"] == str(dms_rule.id) and t["status"] == "triggered_penalty" for t in triggered)
    assert dms_rule.status == "triggered_penalty"
