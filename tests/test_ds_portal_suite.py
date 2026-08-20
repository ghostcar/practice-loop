"""Tests for D/s Command Center Portal & Managed Submissive Suite (Steps 62-74)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ds_suite import ChastityLockLog, ManagedSubmissive


@pytest.mark.asyncio
async def test_ds_portal_page(auth_client: AsyncClient):
    """GET /ds/portal — Command Center Cockpit Page."""
    response = await auth_client.get("/ds/portal")
    assert response.status_code == 200
    assert "Центр Управления D/s" in response.text


@pytest.mark.asyncio
async def test_ds_checkins_hub(auth_client: AsyncClient):
    """GET /ds/checkins — Tag Seals & Wear Check-Ins Hub."""
    response = await auth_client.get("/ds/checkins")
    assert response.status_code == 200
    assert "Инспекции Номерных Пломб" in response.text


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
        follow_redirects=True,
    )
    assert response.status_code == 200

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
        follow_redirects=True,
    )
    assert response.status_code == 200

    await db_session.refresh(sub)
    assert sub.telegram_link_code is not None
    assert sub.telegram_link_code.startswith("SUB-")
