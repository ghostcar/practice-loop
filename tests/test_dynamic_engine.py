import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.services.dynamic import (
    create_dynamic_definition,
    end_dynamic_run,
    get_active_dynamic_run,
    start_dynamic_run,
)


@pytest.mark.asyncio
async def test_dynamic_definition_and_run_lifecycle(
    db_session: AsyncSession,
    test_user: User,
):
    # 1. Create a DynamicDefinition with agency overlay
    dynamic_def = await create_dynamic_definition(
        db=db_session,
        user_id=test_user.id,
        title="Строгий 14-дневный дисциплинарный режим",
        description="Включает протокол утренней разминки и строгий таймер",
        agency_overlay={"timer": {"max_extension_hours": 48}},
        included_protocol_ids=["11111111-1111-1111-1111-111111111111"],
        granted_capabilities=["timer.extend", "protocol.start"],
    )
    assert dynamic_def.id is not None
    assert dynamic_def.agency_overlay["timer"]["max_extension_hours"] == 48

    # 2. Start dynamic run
    run = await start_dynamic_run(
        db=db_session,
        user_id=test_user.id,
        dynamic_id=dynamic_def.id,
        duration_days=14,
    )
    assert run.id is not None
    assert run.status == "active"
    assert run.expires_at is not None
    # Frozen snapshot captures exact rules
    assert run.frozen_dynamic_snapshot["title"] == "Строгий 14-дневный дисциплинарный режим"
    assert "timer.extend" in run.frozen_dynamic_snapshot["granted_capabilities"]

    # 3. Verify get_active_dynamic_run returns the active run
    active_run = await get_active_dynamic_run(db=db_session, user_id=test_user.id)
    assert active_run is not None
    assert active_run.id == run.id

    # 4. Conclude dynamic run
    ended = await end_dynamic_run(db=db_session, run_id=run.id)
    assert ended.status == "completed"
    assert ended.ended_at is not None

    # Verify no active run remains
    active_after = await get_active_dynamic_run(db=db_session, user_id=test_user.id)
    assert active_after is None
