import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agency import AgencyLevel
from app.models.user import User
from app.services.agency import evaluate_agency_permission, set_user_agency_policy


@pytest.mark.asyncio
async def test_default_agency_is_manual_unless_set(db_session: AsyncSession, test_user: User):
    # Without policy, default is manual -> automated action rejected
    allowed, reason = await evaluate_agency_permission(
        db=db_session,
        user_id=test_user.id,
        domain="training",
        operation="generate",
        proposed_level=AgencyLevel.AUTOMATED_WITHIN_POLICY.value,
    )
    assert not allowed
    assert "Agency policy violation" in reason


@pytest.mark.asyncio
async def test_user_can_grant_automated_with_constraints(db_session: AsyncSession, test_user: User):
    # Set policy: domain=sessions, default=assisted, overrides={"generate": "automated"}, max_duration=30m
    await set_user_agency_policy(
        db=db_session,
        user_id=test_user.id,
        domain="sessions",
        default_level=AgencyLevel.ASSISTED.value,
        operation_overrides={"generate": AgencyLevel.AUTOMATED_WITHIN_POLICY.value},
        constraints={"max_duration_min": 30, "forbidden_tags": ["impact"]},
    )
    await db_session.flush()

    # 1. Operation within bounds is permitted
    allowed, _ = await evaluate_agency_permission(
        db=db_session,
        user_id=test_user.id,
        domain="sessions",
        operation="generate",
        proposed_level=AgencyLevel.AUTOMATED_WITHIN_POLICY.value,
        payload={"duration_min": 25, "tags": ["cardio"]},
    )
    assert allowed

    # 2. Exceeding max duration constraint is blocked (Hard System Gate)
    allowed, reason = await evaluate_agency_permission(
        db=db_session,
        user_id=test_user.id,
        domain="sessions",
        operation="generate",
        proposed_level=AgencyLevel.AUTOMATED_WITHIN_POLICY.value,
        payload={"duration_min": 45, "tags": ["cardio"]},
    )
    assert not allowed
    assert "exceeds user limit 30m" in reason

    # 3. Forbidden tag is blocked (Hard System Gate)
    allowed, reason = await evaluate_agency_permission(
        db=db_session,
        user_id=test_user.id,
        domain="sessions",
        operation="generate",
        proposed_level=AgencyLevel.AUTOMATED_WITHIN_POLICY.value,
        payload={"duration_min": 15, "tags": ["impact"]},
    )
    assert not allowed
    assert "contains forbidden tags" in reason
