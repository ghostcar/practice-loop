"""Tests for Community Feed posts and ban/unban moderation (v1.0 Stage G)."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.community_agent import (
    ban_community_member,
    create_community,
    create_community_post,
    get_community_membership,
    join_community,
    unban_community_member,
)
from app.models.user import User


@pytest.mark.asyncio
async def test_create_post_requires_active_member(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """Non-member cannot post; active member can."""
    community = await create_community(db_session, name="Feed", slug="feed-comm", owner_id=test_user.id)
    await db_session.flush()

    # Non-member (second_user not joined) → error
    with pytest.raises(ValueError):
        await create_community_post(db_session, community.id, second_user.id, title="No", content="nope")

    # Owner posts fine
    post = await create_community_post(db_session, community.id, test_user.id, title="Привет", content="Мир")
    await db_session.flush()
    assert post.title == "Привет"
    assert post.content == "Мир"
    assert post.user_id == test_user.id


@pytest.mark.asyncio
async def test_ban_and_unban_member(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """Ban revokes membership; unban restores it."""
    community = await create_community(db_session, name="Mod", slug="mod-comm", owner_id=test_user.id)
    await db_session.flush()
    await join_community(db_session, community, second_user.id)

    # Ban
    status = await ban_community_member(db_session, community.id, second_user.id)
    await db_session.flush()
    assert status == "banned"
    member = await get_community_membership(db_session, community.id, second_user.id)
    assert member.status == "revoked"

    # Ban again → already_banned
    assert await ban_community_member(db_session, community.id, second_user.id) == "already_banned"

    # Owner cannot be banned
    assert await ban_community_member(db_session, community.id, test_user.id) == "is_owner"

    # Unban
    assert await unban_community_member(db_session, community.id, second_user.id) == "unbanned"
    member = await get_community_membership(db_session, community.id, second_user.id)
    assert member.status == "active"


@pytest.mark.asyncio
async def test_banned_member_cannot_post(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """Revoked membership blocks posting."""
    community = await create_community(db_session, name="Ban", slug="ban-comm", owner_id=test_user.id)
    await db_session.flush()
    await join_community(db_session, community, second_user.id)
    await ban_community_member(db_session, community.id, second_user.id)
    await db_session.flush()

    with pytest.raises(ValueError):
        await create_community_post(db_session, community.id, second_user.id, title="Post", content="blocked")
