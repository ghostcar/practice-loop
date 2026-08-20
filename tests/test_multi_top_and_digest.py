"""Integration tests for Multi-Top Co-Governance, Weekly AI Digest, and iCal Feed."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.community_agent import create_community_tournament
from app.agent.community_roles import assign_community_role, get_community_user_roles
from app.agent.weekly_digest import generate_weekly_user_digest
from app.models.community_agent import Community
from app.models.user import User


@pytest.mark.asyncio
async def test_assign_community_role_and_permissions(db_session: AsyncSession, test_user: User):
    """Verify assigning granular co-governance roles in community."""
    community = Community(name="Role Comm", slug="role-comm", owner_id=test_user.id)
    db_session.add(community)
    await db_session.flush()

    user2 = User(email="trainer@test.com", password_hash="hash")
    db_session.add(user2)
    await db_session.flush()

    res = await assign_community_role(db_session, community.id, user2.id, role_type="trainer")
    assert res["status"] == "success"

    roles = await get_community_user_roles(db_session, community.id, user2.id)
    assert "trainer" in roles


@pytest.mark.asyncio
async def test_generate_weekly_user_digest(db_session: AsyncSession, test_user: User):
    """Verify weekly AI digest generates predictive completion scores."""
    digest = await generate_weekly_user_digest(db_session, test_user)
    assert digest["status"] == "success"
    assert digest["predicted_next_week_goal"] >= 75.0
    assert "Еженедельный ИИ-Дайджест" in digest["summary_markdown"]


@pytest.mark.asyncio
async def test_calendar_ical_feed_endpoint(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    """GET /calendar/feed.ics returns valid RFC 5545 iCalendar feed."""
    community = Community(name="Cal Comm", slug="cal-comm", owner_id=test_user.id)
    db_session.add(community)
    await db_session.flush()

    await create_community_tournament(db_session, community.id, title="Календарный Турнир", metric_type="all", days=14)
    await db_session.commit()

    resp = await auth_client.get("/calendar/feed.ics")
    assert resp.status_code == 200
    assert "BEGIN:VCALENDAR" in resp.text
    assert "Календарный Турнир" in resp.text
