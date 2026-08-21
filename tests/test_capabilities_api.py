import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.capability import CapabilityGrantV2
from app.models.user import User


@pytest.mark.asyncio
async def test_capabilities_api_endpoints(
    async_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
    auth_headers: dict[str, str],
):
    # Create a second user as recipient
    recipient = User(
        email="partner@example.com",
        password_hash="fakehash",
    )
    db_session.add(recipient)
    await db_session.flush()

    # 1. GET /capabilities UI
    res = await async_client.get("/capabilities", headers=auth_headers)
    assert res.status_code == 200
    assert "Capabilities Grants" in res.text

    # 2. POST /capabilities HTML form
    post_res = await async_client.post(
        "/capabilities",
        data={
            "recipient_email": "partner@example.com",
            "capability_code": "timer.extend",
            "duration_days": 14,
        },
        headers=auth_headers,
        follow_redirects=False,
    )
    assert post_res.status_code == 303

    # Check grant in DB
    grant_res = await db_session.execute(select(CapabilityGrantV2).where(CapabilityGrantV2.issuer_id == test_user.id))
    grant = grant_res.scalar_one_or_none()
    assert grant is not None
    assert grant.capability_code == "timer.extend"
    assert grant.status == "active"

    # 3. POST /capabilities/{id}/revoke
    revoke_res = await async_client.post(
        f"/capabilities/{grant.id}/revoke",
        headers=auth_headers,
        follow_redirects=False,
    )
    assert revoke_res.status_code == 303
    await db_session.refresh(grant)
    assert grant.status == "revoked"
