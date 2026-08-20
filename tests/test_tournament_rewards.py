"""Integration tests for Tournament Rewards & Badges Awarding Engine."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.community_agent import create_community_tournament, join_community_tournament
from app.agent.tournament_rewards import award_tournament_prizes, get_or_create_tournament_badge
from app.models.achievement import UserAchievement
from app.models.community_agent import Community
from app.models.user import User


@pytest.mark.asyncio
async def test_get_or_create_tournament_badge(db_session: AsyncSession):
    """Verify badges for top 3 ranks are created correctly."""
    b1 = await get_or_create_tournament_badge(db_session, rank=1)
    b2 = await get_or_create_tournament_badge(db_session, rank=2)
    b3 = await get_or_create_tournament_badge(db_session, rank=3)

    assert b1.code == "tournament_gold_champion"
    assert b2.code == "tournament_silver_runner_up"
    assert b3.code == "tournament_bronze_podium"


@pytest.mark.asyncio
async def test_award_tournament_prizes_top_participants(db_session: AsyncSession, test_user: User):
    """Verify awarding tournament prizes assigns UserAchievement badges to winners."""
    community = Community(name="Comm Award", slug="comm-award", owner_id=test_user.id)
    db_session.add(community)
    await db_session.flush()

    tournament = await create_community_tournament(
        db_session, community.id, title="Финал Года", metric_type="all", days=30
    )

    entry1 = await join_community_tournament(db_session, tournament.id, test_user.id)
    entry1.points = 150.0

    user2 = User(email="winner2@test.com", password_hash="hash")
    db_session.add(user2)
    await db_session.flush()
    entry2 = await join_community_tournament(db_session, tournament.id, user2.id)
    entry2.points = 300.0  # Gold winner

    await db_session.commit()

    res = await award_tournament_prizes(db_session, tournament.id)
    assert res["status"] == "success"
    assert res["awarded_winners_count"] == 2

    # Verify Gold Badge for User 2
    ua_res = await db_session.execute(select(UserAchievement).where(UserAchievement.user_id == user2.id))
    user2_achievements = ua_res.scalars().all()
    assert len(user2_achievements) == 1
