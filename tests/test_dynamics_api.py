import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dynamic import DynamicDefinition, DynamicRun
from app.models.user import User


@pytest.mark.asyncio
async def test_dynamics_api_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
):
    # 1. GET /dynamics UI
    res = await async_client.get("/dynamics", headers=auth_headers)
    assert res.status_code == 200
    assert "Dynamics Engine" in res.text

    # 2. POST /dynamics/new
    new_res = await async_client.post(
        "/dynamics/new",
        data={
            "title": "7-дневный фокус-режим",
            "description": "Строгий режим таймера и рутины",
            "agency_overlay_json": '{"timer": {"max_extension_hours": 12}}',
            "granted_capabilities": "timer.extend, protocol.start",
        },
        headers=auth_headers,
        follow_redirects=False,
    )
    assert new_res.status_code == 303

    # Check definition in DB
    def_res = await db_session.execute(select(DynamicDefinition).where(DynamicDefinition.user_id == test_user.id))
    dynamic_def = def_res.scalar_one_or_none()
    assert dynamic_def is not None
    assert dynamic_def.title == "7-дневный фокус-режим"

    # 3. POST /dynamics/{id}/start
    start_res = await async_client.post(
        f"/dynamics/{dynamic_def.id}/start",
        data={"duration_days": 7},
        headers=auth_headers,
        follow_redirects=False,
    )
    assert start_res.status_code == 303

    run_res = await db_session.execute(
        select(DynamicRun).where(
            DynamicRun.user_id == test_user.id,
            DynamicRun.status == "active",
        )
    )
    run = run_res.scalar_one_or_none()
    assert run is not None
    assert run.frozen_dynamic_snapshot["title"] == "7-дневный фокус-режим"

    # 4. POST /dynamics/runs/{run_id}/end
    end_res = await async_client.post(
        f"/dynamics/runs/{run.id}/end",
        headers=auth_headers,
        follow_redirects=False,
    )
    assert end_res.status_code == 303
    await db_session.refresh(run)
    assert run.status == "completed"
