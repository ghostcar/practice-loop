import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capability import CapabilityGrantV2
from app.models.ds_suite import CapabilityGrant as DsCapabilityGrant
from app.models.user import User
from app.services.capability import ActorContext, CapabilityAuthorizer


@pytest.mark.asyncio
async def test_owner_always_has_full_capability(db_session: AsyncSession, test_user: User):
    actor = ActorContext(actor_id=test_user.id)
    allowed, reason = await CapabilityAuthorizer.can_act(
        db=db_session,
        actor=actor,
        issuer_user_id=test_user.id,
        capability_code="protocol.edit_definition",
    )
    assert allowed
    assert "Owner" in reason


@pytest.mark.asyncio
async def test_direct_capability_grant_v2(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    actor = ActorContext(actor_id=second_user.id)

    # 1. Without grant -> denied
    allowed, reason = await CapabilityAuthorizer.can_act(
        db=db_session,
        actor=actor,
        issuer_user_id=test_user.id,
        capability_code="protocol.start",
    )
    assert not allowed
    assert "denied" in reason

    # 2. Add CapabilityGrantV2
    grant = CapabilityGrantV2(
        issuer_id=test_user.id,
        recipient_id=second_user.id,
        capability_code="protocol.start",
        status="active",
    )
    db_session.add(grant)
    await db_session.flush()

    # 3. With active grant -> allowed
    allowed, reason = await CapabilityAuthorizer.can_act(
        db=db_session,
        actor=actor,
        issuer_user_id=test_user.id,
        capability_code="protocol.start",
    )
    assert allowed
    assert "direct CapabilityGrantV2" in reason


@pytest.mark.asyncio
async def test_legacy_ds_grant_adapter(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    import datetime

    actor = ActorContext(actor_id=second_user.id)

    # Add legacy D/s grant with scope_medication=True
    ds_grant = DsCapabilityGrant(
        sub_user_id=test_user.id,
        top_user_id=second_user.id,
        invite_code="TESTINVITE1234567890123456789012",
        scope_medication=True,
        scope_chastity=False,
        status="active",
        expires_at=datetime.datetime.now(datetime.UTC) + datetime.timedelta(days=7),
    )
    db_session.add(ds_grant)
    await db_session.flush()

    # Medication operation allowed via adapter
    allowed_med, reason_med = await CapabilityAuthorizer.can_act(
        db=db_session,
        actor=actor,
        issuer_user_id=test_user.id,
        capability_code="medication.confirm",
    )
    assert allowed_med
    assert "legacy D/s" in reason_med

    # Timer operation denied
    allowed_timer, reason_timer = await CapabilityAuthorizer.can_act(
        db=db_session,
        actor=actor,
        issuer_user_id=test_user.id,
        capability_code="timer.extend",
    )
    assert not allowed_timer
