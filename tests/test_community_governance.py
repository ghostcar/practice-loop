"""Integration tests for Community Governance: ownership transfer & moderators.

Covers transfer_community_ownership, assign_member_role / remove_member_role,
and the management-role helpers used by the agent API.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.community_agent import (
    assign_member_role,
    create_community,
    get_community_membership,
    get_member_roles,
    join_community,
    list_member_roles,
    remove_member_role,
    transfer_community_ownership,
)
from app.models.user import User


@pytest.mark.asyncio
async def test_transfer_ownership_moves_owner_role(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """Owner can transfer ownership to an active member; roles swap."""
    community = await create_community(db_session, name="Передача", slug="transfer-comm", owner_id=test_user.id)
    await db_session.flush()
    await join_community(db_session, community, second_user.id)

    status, _ = await transfer_community_ownership(db_session, community, second_user.id)
    await db_session.flush()
    assert status == "transferred"

    old_owner = await get_community_membership(db_session, community.id, test_user.id)
    new_owner = await get_community_membership(db_session, community.id, second_user.id)
    assert old_owner.role == "member"
    assert new_owner.role == "owner"
    assert community.owner_id == second_user.id


@pytest.mark.asyncio
async def test_transfer_ownership_rejects_non_member(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    community = await create_community(db_session, name="Передача2", slug="transfer-comm2", owner_id=test_user.id)
    await db_session.flush()

    status, _ = await transfer_community_ownership(db_session, community, second_user.id)
    assert status == "not_member"
    assert community.owner_id == test_user.id


@pytest.mark.asyncio
async def test_transfer_ownership_rejects_owner(
    db_session: AsyncSession,
    test_user: User,
):
    community = await create_community(db_session, name="Передача3", slug="transfer-comm3", owner_id=test_user.id)
    await db_session.flush()

    status, _ = await transfer_community_ownership(db_session, community, test_user.id)
    assert status == "already_owner"


@pytest.mark.asyncio
async def test_assign_moderator_role(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """Owner can assign co_top and tournament_organizer roles to active members."""
    community = await create_community(db_session, name="Модерация", slug="mod-comm", owner_id=test_user.id)
    await db_session.flush()
    await join_community(db_session, community, second_user.id)

    status, _ = await assign_member_role(db_session, community.id, second_user.id, "co_top")
    assert status == "assigned"
    status2, _ = await assign_member_role(db_session, community.id, second_user.id, "tournament_organizer")
    assert status2 == "assigned"

    roles = await get_member_roles(db_session, community.id, second_user.id)
    assert roles == {"co_top", "tournament_organizer"}


@pytest.mark.asyncio
async def test_assign_moderator_role_validates_role_and_member(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    community = await create_community(db_session, name="Модерация2", slug="mod-comm2", owner_id=test_user.id)
    await db_session.flush()

    # Non-member cannot get a role
    status, _ = await assign_member_role(db_session, community.id, second_user.id, "co_top")
    assert status == "not_member"

    await join_community(db_session, community, second_user.id)
    # Unknown role is rejected
    status2, _ = await assign_member_role(db_session, community.id, second_user.id, "bogus_role")
    assert status2 == "invalid_role"


@pytest.mark.asyncio
async def test_remove_moderator_role(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    community = await create_community(db_session, name="Снятие", slug="unmod-comm", owner_id=test_user.id)
    await db_session.flush()
    await join_community(db_session, community, second_user.id)
    await assign_member_role(db_session, community.id, second_user.id, "trainer")

    removed = await remove_member_role(db_session, community.id, second_user.id, "trainer")
    assert removed is True
    assert await get_member_roles(db_session, community.id, second_user.id) == set()

    # Removing a role that was never assigned returns False
    removed2 = await remove_member_role(db_session, community.id, second_user.id, "trainer")
    assert removed2 is False


@pytest.mark.asyncio
async def test_list_member_roles_only_active_members(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    community = await create_community(db_session, name="Роли", slug="roles-comm", owner_id=test_user.id)
    await db_session.flush()
    await join_community(db_session, community, second_user.id)
    await assign_member_role(db_session, community.id, second_user.id, "care_curator")

    all_roles = await list_member_roles(db_session, community.id)
    assert len(all_roles) == 1
    assert all_roles[0].role_type == "care_curator"
    assert all_roles[0].user_id == second_user.id
