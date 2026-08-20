"""Tests for D/s Command Center Portal & Managed Submissive Suite (Steps 62-74)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ds_suite import CapabilityGrant, CapabilityGrantClaimAttempt, ChastityLockLog, ManagedSubmissive


@pytest.mark.asyncio
async def test_ds_portal_page(auth_client: AsyncClient):
    """GET /ds/portal — Command Center Cockpit Page."""
    response = await auth_client.get("/ds/portal")
    assert response.status_code == 200
    assert "D/s Command Center" in response.text


@pytest.mark.asyncio
async def test_ds_checkins_hub(auth_client: AsyncClient):
    """GET /ds/checkins — Tag Seals & Wear Check-Ins Hub."""
    response = await auth_client.get("/ds/checkins")
    assert response.status_code == 200
    assert "Инспекция Номерных Пломб" in response.text


@pytest.mark.asyncio
async def test_ai_keyholder_bot_spin(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """POST /ds/submissive/{sub_id}/ai-keyholder-spin — Spin AI Keyholder wheel."""
    sub = ManagedSubmissive(
        top_user_id=test_user.id,
        name="Test Submissive",
        chastity_status="locked",
    )
    db_session.add(sub)
    await db_session.commit()

    response = await auth_client.post(
        f"/ds/submissive/{sub.id}/ai-keyholder-spin",
        follow_redirects=False,
    )
    assert response.status_code == 303

    logs = (
        (await db_session.execute(select(ChastityLockLog).where(ChastityLockLog.managed_sub_id == sub.id)))
        .scalars()
        .all()
    )
    assert len(logs) > 0


@pytest.mark.asyncio
async def test_telegram_linking_code(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """POST /ds/submissive/{sub_id}/telegram-code — Generate SUB-XXXXXX link code."""
    sub = ManagedSubmissive(
        top_user_id=test_user.id,
        name="Offline Sub",
        chastity_status="unlocked",
    )
    db_session.add(sub)
    await db_session.commit()

    response = await auth_client.post(
        f"/ds/submissive/{sub.id}/telegram-code",
        follow_redirects=False,
    )
    assert response.status_code == 303

    await db_session.refresh(sub)
    assert sub.telegram_link_code is not None
    assert sub.telegram_link_code.startswith("SUB-")


@pytest.mark.asyncio
async def test_grant_requires_explicit_scope_and_expires(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    missing_scope = await auth_client.post("/ds/grant/create", follow_redirects=False)
    assert missing_scope.status_code == 400

    created = await auth_client.post(
        "/ds/grant/create",
        data={"scope_tasks": "true", "scope_health_view": "true"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    grant = (await db_session.execute(select(CapabilityGrant))).scalar_one()
    assert grant.scope_tasks is True
    assert grant.scope_health_view is True
    assert grant.scope_chastity is False
    assert grant.expires_at > grant.created_at


@pytest.mark.asyncio
async def test_grant_claim_attempts_are_audited_and_rate_limited(
    auth_client: AsyncClient, db_session: AsyncSession, test_user
):
    for _ in range(10):
        response = await auth_client.post(
            "/ds/grant/claim", data={"invite_code": "DS-DOESNOTEXIST"}, follow_redirects=False
        )
        assert response.status_code == 404

    limited = await auth_client.post("/ds/grant/claim", data={"invite_code": "DS-DOESNOTEXIST"}, follow_redirects=False)
    assert limited.status_code == 429
    attempts = (await db_session.execute(select(CapabilityGrantClaimAttempt))).scalars().all()
    assert len(attempts) == 10
    assert all(a.actor_id == test_user.id and len(a.invite_code_hash) == 64 for a in attempts)
