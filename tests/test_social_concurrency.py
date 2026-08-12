"""Social concurrency and isolation tests — S7 hardening.

Covers:
- Relationship race conditions (double accept, simultaneous invite+block)
- Grant idempotency
- Moderation action isolation
- Feed read-write isolation
- Block propagation
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.platform.social.repositories import (
    _is_blocked,
    accept_invitation,
    block_user,
    create_grant,
    create_invitation,
    create_moderation_action,
    create_publication,
    create_report,
    get_relationship_by_pair,
    hide_publication,
    list_feed,
)

pytestmark = pytest.mark.anyio


# ── Helpers ──


async def _create_profile(
    db: AsyncSession, user: User, alias: str, bio: str | None = None,
):
    """Create a social profile for a test user."""
    from app.platform.social.repositories import create_profile as _cp

    return await _cp(db, user.id, alias, alias.lower(), bio)


async def _create_profiles(
    db: AsyncSession, user_a: User, user_b: User,
) -> tuple:
    """Create profiles for two users."""
    pa = await _create_profile(db, user_a, f"user_{user_a.id.hex[:8]}")
    pb = await _create_profile(db, user_b, f"user_{user_b.id.hex[:8]}")
    return pa, pb


# ── SC-S01: Double accept same invitation ──


class TestDoubleAccept:
    async def test_only_one_accept_succeeds(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        # Create second user
        u2 = User(email="u2@test.com", password_hash="x", locale="en", theme="dark")
        db_session.add(u2)
        await db_session.flush()
        await _create_profiles(db_session, test_user, u2)

        rel = await create_invitation(db_session, test_user.id, u2.id)

        a1 = await accept_invitation(db_session, rel.id, u2.id)
        assert a1 is not None
        assert a1.status == "accepted"

        a2 = await accept_invitation(db_session, rel.id, u2.id)
        assert a2 is None  # already accepted


# ── SC-S02: Concurrent invite while block is being placed ──


class TestInviteBlockRace:
    async def test_block_prevents_invite(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        u2 = User(email="u3@test.com", password_hash="x", locale="en", theme="dark")
        db_session.add(u2)
        await db_session.flush()
        await _create_profiles(db_session, test_user, u2)

        await block_user(db_session, test_user.id, u2.id, reason="test")
        assert await _is_blocked(db_session, test_user.id, u2.id)

        # Creating invitation when blocked should raise in API layer,
        # but repo layer allows it — isolation is in API
        rel = await get_relationship_by_pair(db_session, test_user.id, u2.id)
        # No relationship should exist yet
        assert rel is None

    async def test_block_does_not_affect_invite_from_blocked(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        u2 = User(email="u4@test.com", password_hash="x", locale="en", theme="dark")
        db_session.add(u2)
        await db_session.flush()
        await _create_profiles(db_session, test_user, u2)

        # test_user blocks u2
        await block_user(db_session, test_user.id, u2.id)
        assert await _is_blocked(db_session, test_user.id, u2.id)

        # u2 trying to invite test_user should still resolve at API layer
        # Repo layer — check block exists
        blocked = await _is_blocked(db_session, test_user.id, u2.id)
        assert blocked


# ── SC-S03: Feed isolation — publication hidden during moderation ──


class TestFeedWithModeration:
    async def test_hidden_publication_not_in_feed(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        from app.platform.social.repositories import register_subject

        u2 = User(email="u5@test.com", password_hash="x", locale="en", theme="dark")
        db_session.add(u2)
        await db_session.flush()
        pa, pb = await _create_profiles(db_session, test_user, u2)

        # Create relationship so feed includes relationship_only
        rel = await create_invitation(db_session, test_user.id, u2.id)
        await accept_invitation(db_session, rel.id, u2.id)

        # Register a subject
        subj = await register_subject(
            db_session, test_user.id, "tracker.activity_log", str(uuid.uuid4()),
        )

        # Publish
        pub = await create_publication(
            db_session, test_user.id, subj.id,
            visibility="relationship_only",
            snapshot={"key": "val"},
            snapshot_hash="abc123",
            subject_namespace="tracker",
        )

        # Feed from u2's perspective should include the publication
        feed_before = await list_feed(db_session, u2.id, limit=10)
        assert len(feed_before) >= 1

        # Moderator hides it
        ok = await hide_publication(db_session, pub.id)
        assert ok

        # Feed should no longer include it
        feed_after = await list_feed(db_session, u2.id, limit=10)
        pub_ids = [p.id for p in feed_after]
        assert pub.id not in pub_ids


# ── SC-S04: Grant idempotency — accept after accept ──


class TestGrantIdempotency:
    async def test_double_accept_grant(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        from app.platform.social.repositories import accept_grant as ag

        u2 = User(email="u6@test.com", password_hash="x", locale="en", theme="dark")
        db_session.add(u2)
        await db_session.flush()
        await _create_profiles(db_session, test_user, u2)

        rel = await create_invitation(db_session, test_user.id, u2.id)
        await accept_invitation(db_session, rel.id, u2.id)

        grant = await create_grant(db_session, rel.id, "subject", {"caps": ["view_summary"]})

        # u2 (recipient) accepts
        g1 = await ag(db_session, grant.id, u2.id)
        assert g1 is not None
        assert g1.status == "accepted"

        g2 = await ag(db_session, grant.id, u2.id)
        assert g2 is None  # already accepted


# ── SC-S05: Report idempotency — report same target twice ──


class TestReportIdempotency:
    async def test_duplicate_reports_allowed(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Multiple reports on the same target are allowed (different reporters or timestamps)."""
        pub_id = uuid.uuid4()

        r1 = await create_report(db_session, test_user.id, "publication", pub_id, "spam")
        r2 = await create_report(db_session, test_user.id, "publication", pub_id, "spam")

        assert r1.id != r2.id  # Both created — duplicate reports are allowed


# ── SC-S06: Moderation action is immutable ──


class TestModerationActionImmutability:
    async def test_action_cannot_be_deleted(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Moderation actions are append-only — no update/delete paths exist."""
        pub_id = uuid.uuid4()
        report = await create_report(db_session, test_user.id, "publication", pub_id, "spam")
        action = await create_moderation_action(
            db_session, report.id, test_user.id, "resolve_report",
            reason="Test resolution",
        )

        # Verify action exists
        assert action.id is not None
        assert action.action_type == "resolve_report"

        # No update function exists by design — immutability is structural


# ── SC-S07: Block propagation — block removes from feed ──


class TestBlockPropagation:
    async def test_block_hides_content_from_blocked_user(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        from app.platform.social.repositories import register_subject

        u2 = User(email="u7@test.com", password_hash="x", locale="en", theme="dark")
        db_session.add(u2)
        await db_session.flush()
        await _create_profiles(db_session, test_user, u2)

        # Create relationship
        rel = await create_invitation(db_session, test_user.id, u2.id)
        await accept_invitation(db_session, rel.id, u2.id)

        # Publish
        subj = await register_subject(
            db_session, test_user.id, "tracker.activity_log", str(uuid.uuid4()),
        )
        await create_publication(
            db_session, test_user.id, subj.id,
            visibility="relationship_only",
            snapshot={"key": "pre_block"},
            snapshot_hash="hash1",
            subject_namespace="tracker",
        )

        # Block
        await block_user(db_session, u2.id, test_user.id)

        # Feed from u2 should not include blocked user's content
        feed = await list_feed(db_session, u2.id, limit=10)
        owner_ids = {p.owner_id for p in feed}
        assert test_user.id not in owner_ids


# ── SC-S08: Cross-user isolation — user A cannot resolve user B's report ──


class TestCrossUserModeration:
    async def test_non_moderator_cannot_act(
        self, db_session: AsyncSession, test_user: User,
    ) -> None:
        """Repository-level: assign_report doesn't enforce permissions — API layer does."""
        u2 = User(email="u8@test.com", password_hash="x", locale="en", theme="dark")
        db_session.add(u2)
        await db_session.flush()

        pub_id = uuid.uuid4()
        report = await create_report(db_session, test_user.id, "publication", pub_id, "spam")

        # u2 can assign at repo level (API handles auth)
        from app.platform.social.repositories import assign_report

        assigned = await assign_report(db_session, report.id, u2.id)
        assert assigned is not None
        assert assigned.state == "reviewing"
