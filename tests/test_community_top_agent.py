"""Integration tests for Autonomous Community Top Agent & Public Tournaments."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.community_agent import (
    create_community_tournament,
    get_or_create_community_top_agent,
    join_community_tournament,
    recalculate_tournament_standings,
    run_community_quest_generation,
)
from app.models.community_agent import Community, CommunityPost
from app.models.user import User


@pytest.mark.asyncio
async def test_community_top_agent_creation_and_config(
    db_session: AsyncSession,
    test_user: User,
):
    """Verify initialization of CommunityTopAgent persona settings."""
    community = Community(
        name="Тестовое Сообщество ИИ-Верхнего",
        slug="test-ai-top-comm",
        owner_id=test_user.id,
    )
    db_session.add(community)
    await db_session.flush()

    agent = await get_or_create_community_top_agent(db_session, community.id)
    assert agent.persona_name == "Domina Veritas"
    assert agent.strictness_level == 3


@pytest.mark.asyncio
async def test_community_quest_generation_and_feed_post(
    db_session: AsyncSession,
    test_user: User,
):
    """Verify run_community_quest_generation posts an announcement to Community Feed."""
    community = Community(
        name="Сообщество Квестов",
        slug="test-quest-comm",
        owner_id=test_user.id,
    )
    db_session.add(community)
    await db_session.flush()

    result = await run_community_quest_generation(db_session, community.id)
    assert result["status"] == "success"

    # Verify post in DB
    post_res = await db_session.execute(select(CommunityPost).where(CommunityPost.community_id == community.id))
    posts = post_res.scalars().all()
    assert len(posts) >= 1
    assert "Групповой Челлендж" in posts[0].title


@pytest.mark.asyncio
async def test_public_tournament_lifecycle(
    db_session: AsyncSession,
    test_user: User,
):
    """Verify creation, joining, and standings recalculation of a public tournament."""
    community = Community(
        name="Сообщество Турниров",
        slug="test-tourney-comm",
        owner_id=test_user.id,
    )
    db_session.add(community)
    await db_session.flush()

    tournament = await create_community_tournament(
        db_session, community.id, title="Кубок Ухода 2026", metric_type="care", days=7
    )
    assert tournament.title == "Кубок Ухода 2026"

    entry = await join_community_tournament(db_session, tournament.id, test_user.id)
    assert entry.rank == 1

    standings = await recalculate_tournament_standings(db_session, tournament.id)
    assert len(standings) == 1
    assert standings[0]["rank"] == 1


@pytest.mark.asyncio
async def test_community_agent_dashboard_page(
    auth_client: AsyncClient,
    db_session: AsyncSession,
    test_user: User,
):
    """GET /communities/{id}/agent renders Community Agent cockpit."""
    community = Community(
        name="Dashboard Community",
        slug="dash-comm",
        owner_id=test_user.id,
    )
    db_session.add(community)
    await db_session.commit()

    resp = await auth_client.get(f"/communities/{community.id}/agent")
    assert resp.status_code == 200
    assert "ИИ-Верхний Сообщества" in resp.text
