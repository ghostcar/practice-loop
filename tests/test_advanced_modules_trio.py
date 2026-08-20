"""Integration tests for Community Cockpit, Chastity Keyholder v2, and Care Engine v2."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.care_engine import record_aftercare_recovery_protocol
from app.agent.community_agent import get_or_create_community_top_agent
from app.agent.lock_keyholder import generate_random_unlock_combination, verify_wear_checkin_photo
from app.models.community_agent import Community
from app.models.user import User


@pytest.mark.asyncio
async def test_community_cockpit_page_rendering(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    """GET /communities/{id}/cockpit returns 200 OK for owner."""
    community = Community(name="Cockpit Comm", slug="cockpit-comm", owner_id=test_user.id)
    db_session.add(community)
    await db_session.flush()
    await get_or_create_community_top_agent(db_session, community.id)
    await db_session.commit()

    resp = await auth_client.get(f"/communities/{community.id}/cockpit")
    assert resp.status_code == 200
    assert "Панель Управления ИИ-Верхним" in resp.text


@pytest.mark.asyncio
async def test_chastity_keyholder_v2_combination_and_checkin(db_session: AsyncSession, test_user: User):
    """Verify combination generation and wear checkin verification."""
    combo_res = await generate_random_unlock_combination(db_session, test_user, lock_id="lock_123")
    assert combo_res["status"] == "success"
    assert len(combo_res["combination_code"]) == 8

    verify_res = await verify_wear_checkin_photo(
        db_session, test_user, lock_id="lock_123", photo_url="/uploads/wear.jpg"
    )
    assert verify_res["status"] == "verified"
    assert verify_res["compliance_boost"] == 5.0


@pytest.mark.asyncio
async def test_care_aftercare_protocol_v2_recommendations(db_session: AsyncSession, test_user: User):
    """Verify aftercare protocol logs entry and generates adaptive recommendations."""
    res = await record_aftercare_recovery_protocol(
        db_session, test_user, comfort_level=4, stress_score=8, notes="Интенсивная сессия"
    )
    assert res["status"] == "success"
    assert len(res["recommendations"]) >= 3
    assert "Протокол Заботы" in res["summary_markdown"]
