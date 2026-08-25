"""Tests for Social Safety & Abuse Prevention (v1.0 Stage H).

Covers: invite rate-limit + cooldown, block-filtered comments, report creation.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.platform.social.repositories import (
    block_user,
    create_comment,
    create_invitation,
    create_report,
    list_comments,
    list_reports,
)


@pytest.mark.asyncio
async def test_invite_rate_limit(
    db_session: AsyncSession,
    test_user: User,
    monkeypatch,
):
    """Sending more than the daily invite limit raises ValueError."""
    # Lower the limit for the test
    monkeypatch.setattr(
        "app.platform.social.repositories.relationships.INVITE_DAILY_LIMIT",
        3,
    )

    sent = 0
    with pytest.raises(ValueError, match="Daily invite limit"):
        for i in range(4):
            # Real recipient users (FK to users.id)
            recipient = User(
                email=f"recipient{i}@example.com",
                password_hash="x",
                locale="en",
                theme="dark",
            )
            db_session.add(recipient)
            await db_session.flush()
            await create_invitation(db_session, test_user.id, recipient.id, display_role="viewer")
            sent += 1
    assert sent == 3


@pytest.mark.asyncio
async def test_invite_duplicate_pending_rejected(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """A pending invite to the same recipient raises ValueError."""
    await create_invitation(db_session, test_user.id, second_user.id, display_role="viewer")
    with pytest.raises(ValueError, match="already pending"):
        await create_invitation(db_session, test_user.id, second_user.id, display_role="viewer")


@pytest.mark.asyncio
async def test_list_comments_hides_blocked_authors(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """Comments from blocked authors are hidden from the viewer."""
    from app.platform.social.models import SocialPublication, SocialSubject

    subj = SocialSubject(
        owner_id=test_user.id,
        subject_type="activity_log",
        domain_object_id=str(test_user.id),
        projection_version=1,
    )
    db_session.add(subj)
    await db_session.flush()

    pub = SocialPublication(
        owner_id=test_user.id,
        subject_id=subj.id,
        subject_namespace="tracker",
        visibility="public",
        snapshot={},
        snapshot_hash="x" * 64,
    )
    db_session.add(pub)
    await db_session.flush()

    # second_user comments
    await create_comment(db_session, second_user.id, "publication", pub.id, "hello")
    # test_user (viewer) sees it
    visible = await list_comments(db_session, "publication", pub.id, viewer_id=test_user.id)
    assert len(visible) == 1

    # test_user blocks second_user → hidden
    await block_user(db_session, test_user.id, second_user.id)
    await db_session.flush()
    hidden = await list_comments(db_session, "publication", pub.id, viewer_id=test_user.id)
    assert len(hidden) == 0


@pytest.mark.asyncio
async def test_create_report_flow(
    db_session: AsyncSession,
    test_user: User,
    second_user: User,
):
    """A report can be filed and appears in the moderation list."""
    await create_report(
        db_session,
        test_user.id,
        "profile",
        second_user.id,
        "harassment",
        "offensive bio",
    )
    reports = await list_reports(db_session, state=None)
    assert len(reports) == 1
    assert reports[0].reason_code == "harassment"
    assert str(reports[0].target_id) == str(second_user.id)
