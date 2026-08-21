"""Integration tests for Community Registry & Membership workflow.

Covers creation, open/private/invite-code joining, approval flow, leaving,
and owner-only guards.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.community_agent import (
    approve_community_member,
    create_community,
    get_community_membership,
    join_community,
    leave_community,
    rotate_community_invite_code,
)
from app.models.user import User


@pytest.mark.asyncio
async def test_create_community_registers_owner_member(
    db_session: AsyncSession,
    test_user: User,
):
    """Owner becomes the first active owner-member of the new community."""
    community = await create_community(
        db_session,
        name="Хранители Согласия",
        slug="keepers-of-consent",
        description="Тестовая группа",
        owner_id=test_user.id,
    )
    await db_session.flush()

    membership = await get_community_membership(db_session, community.id, test_user.id)
    assert membership is not None
    assert membership.role == "owner"
    assert membership.status == "active"

    # Top agent persona is auto-created
    from app.models.community_agent import CommunityTopAgent

    agent = (
        await db_session.execute(select(CommunityTopAgent).where(CommunityTopAgent.community_id == community.id))
    ).scalar_one_or_none()
    assert agent is not None


@pytest.mark.asyncio
async def test_join_public_community_instant(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """Public community without approval: joining is instant and active."""
    community = await create_community(db_session, name="Публичная", slug="public-comm", owner_id=test_user.id)
    await db_session.flush()

    status, member = await join_community(db_session, community, second_user.id)
    assert status == "joined"
    assert member.status == "active"


@pytest.mark.asyncio
async def test_join_public_community_requires_approval(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """Public community with require_approval: joining creates a pending request."""
    community = await create_community(
        db_session,
        name="С Одобрением",
        slug="approval-comm",
        owner_id=test_user.id,
        require_approval=True,
    )
    await db_session.flush()

    status, member = await join_community(db_session, community, second_user.id)
    assert status == "pending"
    assert member.status == "pending"

    # Owner approves
    result = await approve_community_member(db_session, community.id, member.id, approve=True)
    assert result == "approved"
    assert member.status == "active"


@pytest.mark.asyncio
async def test_join_private_community_needs_invite_code(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """Private community: wrong/missing code is rejected, correct code joins."""
    community = await create_community(
        db_session,
        name="Приватная",
        slug="private-comm",
        owner_id=test_user.id,
        visibility="private",
    )
    code = await rotate_community_invite_code(db_session, community)
    await db_session.flush()
    assert code

    # Wrong code
    status, _ = await join_community(db_session, community, second_user.id, invite_code="WRONG")
    assert status == "invalid_code"

    # Correct code
    status, member = await join_community(db_session, community, second_user.id, invite_code=code)
    assert status == "joined"
    assert member.status == "active"


@pytest.mark.asyncio
async def test_duplicate_join_returns_already_member(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """Second join attempt is idempotent."""
    community = await create_community(db_session, name="Дубликаты", slug="dup-comm", owner_id=test_user.id)
    await db_session.flush()

    await join_community(db_session, community, second_user.id)
    status, _ = await join_community(db_session, community, second_user.id)
    assert status == "already_member"


@pytest.mark.asyncio
async def test_leave_community_removes_membership(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """Member can leave; owner cannot."""
    community = await create_community(db_session, name="Уход", slug="leave-comm", owner_id=test_user.id)
    await db_session.flush()

    await join_community(db_session, community, second_user.id)
    removed = await leave_community(db_session, community.id, second_user.id)
    assert removed is True
    assert await get_community_membership(db_session, community.id, second_user.id) is None

    # Owner cannot leave
    removed_owner = await leave_community(db_session, community.id, test_user.id)
    assert removed_owner is False
    assert await get_community_membership(db_session, community.id, test_user.id) is not None


@pytest.mark.asyncio
async def test_reject_pending_membership_deletes_record(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """Rejecting a pending request removes the membership row."""
    community = await create_community(
        db_session,
        name="Отказы",
        slug="reject-comm",
        owner_id=test_user.id,
        require_approval=True,
    )
    await db_session.flush()

    _, member = await join_community(db_session, community, second_user.id)
    result = await approve_community_member(db_session, community.id, member.id, approve=False)
    assert result == "rejected"
    assert await get_community_membership(db_session, community.id, second_user.id) is None


@pytest.mark.asyncio
async def test_community_visibility_defaults_public(
    db_session: AsyncSession,
    test_user: User,
):
    community = await create_community(db_session, name="По умолчанию", slug="default-vis", owner_id=test_user.id)
    await db_session.flush()
    assert community.visibility == "public"
    assert community.require_approval is False
