"""Tests for numbered tag mechanics — close_tag_number, require_tag, verify_tag.

Covers:
- close_slot with tag_number (happy path, optional, required)
- duplicate tag rejection
- require_tag enforcement
- verify_tag (match vs mismatch → violation)
- lookup_tag
- list_tag_violations
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import enums as e
from app.locktimer.services.execution import (
    add_slot_rule,
    close_slot,
    create_draft,
    list_tag_violations,
    lookup_tag,
    open_slot,
    start_session,
    verify_tag,
)
from app.models.locktimer import (
    LockSlotOccurrence,
    LockSlotRule,
    LockTagViolation,
)
from app.models.user import User

pytestmark = pytest.mark.anyio

FIXED_NOW = datetime(2026, 8, 1, 12, 0, 0, tzinfo=UTC)


async def _draft_with_slot_rule(
    db_session: AsyncSession,
    user: User,
    *,
    require_tag: bool = False,
    allow_late_open: bool = True,
    rule_type: str = e.SLOT_RULE_EVERY_N_DAYS,
    schedule: dict | None = None,
) -> tuple:
    """Create a draft with a slot rule, return (session, rule)."""
    if schedule is None:
        schedule = {"n": 1, "time_of_day": "12:00", "start_date": "2026-08-01T00:00:00+00:00"}
    session = await create_draft(db_session, owner_id=user.id)
    rule = await add_slot_rule(
        db_session,
        session_id=session.id,
        name="Test slot",
        rule_type=rule_type,
        schedule=schedule,
        duration_seconds=1800,
        allow_late_open=allow_late_open,
    )
    if require_tag:
        stmt = sa_update(LockSlotRule).where(LockSlotRule.id == rule.id).values(require_tag=True)
        await db_session.execute(stmt)
        await db_session.flush()
        rule = await db_session.get(LockSlotRule, rule.id)
    return session, rule


async def _started_with_open_slot(
    db_session: AsyncSession,
    user: User,
    *,
    require_tag: bool = False,
) -> tuple:
    """Create a session, start it, open the first slot. Returns (session, open_occ)."""
    session, _rule = await _draft_with_slot_rule(db_session, user, require_tag=require_tag)
    await start_session(db_session, session_id=session.id, owner_id=user.id, now=FIXED_NOW)

    result = await db_session.execute(
        select(LockSlotOccurrence).where(
            LockSlotOccurrence.session_id == session.id,
            LockSlotOccurrence.state == e.SLOT_PENDING,
        )
    )
    occ = result.scalars().first()
    assert occ is not None, "Expected at least one pending slot"
    opened = await open_slot(db_session, occurrence=occ, owner_id=user.id, now=occ.planned_open_at)
    return session, opened


# ---------------------------------------------------------------------------
# Close with tag_number
# ---------------------------------------------------------------------------


class TestCloseWithTag:
    async def test_close_with_tag_stores_number(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await _started_with_open_slot(db_session, test_user)
        closed = await close_slot(db_session, occurrence=occ, owner_id=test_user.id, tag_number="A-0042")
        assert closed.state == e.SLOT_CLOSED
        assert closed.close_tag_number == "A-0042"

    async def test_close_without_tag_when_not_required(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await _started_with_open_slot(db_session, test_user, require_tag=False)
        closed = await close_slot(db_session, occurrence=occ, owner_id=test_user.id)
        assert closed.state == e.SLOT_CLOSED
        assert closed.close_tag_number is None

    async def test_close_without_tag_when_required_raises(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await _started_with_open_slot(db_session, test_user, require_tag=True)
        with pytest.raises(ValueError, match="Tag number is required"):
            await close_slot(db_session, occurrence=occ, owner_id=test_user.id)

    async def test_close_with_tag_when_required(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await _started_with_open_slot(db_session, test_user, require_tag=True)
        closed = await close_slot(db_session, occurrence=occ, owner_id=test_user.id, tag_number="R-001")
        assert closed.state == e.SLOT_CLOSED
        assert closed.close_tag_number == "R-001"

    async def test_close_allows_numeric_tag(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await _started_with_open_slot(db_session, test_user)
        closed = await close_slot(db_session, occurrence=occ, owner_id=test_user.id, tag_number="042")
        assert closed.close_tag_number == "042"

    async def test_close_allows_alphanumeric_tag(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await _started_with_open_slot(db_session, test_user)
        closed = await close_slot(db_session, occurrence=occ, owner_id=test_user.id, tag_number="AB-007-X")
        assert closed.close_tag_number == "AB-007-X"


# ---------------------------------------------------------------------------
# Duplicate tag rejection
# ---------------------------------------------------------------------------


class TestDuplicateTag:
    async def test_duplicate_tag_in_same_session_raises(self, db_session: AsyncSession, test_user: User) -> None:
        session, _rule = await _draft_with_slot_rule(db_session, test_user, rule_type=e.SLOT_RULE_EVERY_N_DAYS)
        await add_slot_rule(
            db_session,
            session_id=session.id,
            name="Second slot",
            rule_type=e.SLOT_RULE_EVERY_N_DAYS,
            schedule={"n": 1, "time_of_day": "14:00", "start_date": "2026-08-01T00:00:00+00:00"},
            duration_seconds=1800,
        )
        await start_session(db_session, session_id=session.id, owner_id=test_user.id, now=FIXED_NOW)

        result = await db_session.execute(
            select(LockSlotOccurrence)
            .where(LockSlotOccurrence.session_id == session.id, LockSlotOccurrence.state == e.SLOT_PENDING)
            .order_by(LockSlotOccurrence.planned_open_at)
            .limit(2)
        )
        occs = list(result.scalars().all())
        assert len(occs) >= 2

        occ1 = await open_slot(db_session, occurrence=occs[0], owner_id=test_user.id, now=occs[0].planned_open_at)
        await close_slot(db_session, occurrence=occ1, owner_id=test_user.id, tag_number="DUP-001")

        occ2 = await open_slot(db_session, occurrence=occs[1], owner_id=test_user.id, now=occs[1].planned_open_at)
        with pytest.raises(ValueError, match="already been used"):
            await close_slot(db_session, occurrence=occ2, owner_id=test_user.id, tag_number="DUP-001")

    async def test_same_tag_different_sessions_allowed(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ1 = await _started_with_open_slot(db_session, test_user)
        sess1_id = occ1.session_id
        await close_slot(db_session, occurrence=occ1, owner_id=test_user.id, tag_number="SAME-001")

        # Mark first session as completed so we can start a new one
        from app.locktimer.services.execution import safety_stop
        await safety_stop(db_session, session_id=sess1_id, owner_id=test_user.id)

        _, occ2 = await _started_with_open_slot(db_session, test_user)
        closed2 = await close_slot(db_session, occurrence=occ2, owner_id=test_user.id, tag_number="SAME-001")
        assert closed2.close_tag_number == "SAME-001"


# ---------------------------------------------------------------------------
# verify_tag
# ---------------------------------------------------------------------------


class TestVerifyTag:
    async def test_verify_tag_match(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await _started_with_open_slot(db_session, test_user)
        closed = await close_slot(db_session, occurrence=occ, owner_id=test_user.id, tag_number="V-001")
        result = await verify_tag(db_session, occurrence=closed, provided_tag="V-001", owner_id=test_user.id)
        assert result["matched"] is True
        assert result["violation_id"] is None

    async def test_verify_tag_mismatch_creates_violation(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await _started_with_open_slot(db_session, test_user)
        closed = await close_slot(db_session, occurrence=occ, owner_id=test_user.id, tag_number="ORIGINAL")
        result = await verify_tag(db_session, occurrence=closed, provided_tag="WRONG", owner_id=test_user.id)
        assert result["matched"] is False
        assert result["expected_tag"] == "ORIGINAL"
        assert result["provided_tag"] == "WRONG"
        assert result["violation_id"] is not None

        violation_id = uuid.UUID(result["violation_id"])
        violation = await db_session.get(LockTagViolation, violation_id)
        assert violation is not None
        assert violation.expected_tag == "ORIGINAL"
        assert violation.provided_tag == "WRONG"
        assert violation.reason == "mismatch"

    async def test_verify_tag_no_tag_on_slot_mismatch(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await _started_with_open_slot(db_session, test_user)
        closed = await close_slot(db_session, occurrence=occ, owner_id=test_user.id)
        result = await verify_tag(db_session, occurrence=closed, provided_tag="ANY", owner_id=test_user.id)
        assert result["matched"] is False
        assert result["expected_tag"] is None

    async def test_verify_tag_cross_user_denied(self, db_session: AsyncSession, test_user: User) -> None:
        _, occ = await _started_with_open_slot(db_session, test_user)
        closed = await close_slot(db_session, occurrence=occ, owner_id=test_user.id, tag_number="TAG")
        other_id = uuid.uuid4()
        with pytest.raises(ValueError, match="Session not found"):
            await verify_tag(db_session, occurrence=closed, provided_tag="TAG", owner_id=other_id)


# ---------------------------------------------------------------------------
# lookup_tag
# ---------------------------------------------------------------------------


class TestLookupTag:
    async def test_lookup_existing_tag(self, db_session: AsyncSession, test_user: User) -> None:
        session, occ = await _started_with_open_slot(db_session, test_user)
        closed = await close_slot(db_session, occurrence=occ, owner_id=test_user.id, tag_number="LKP-001")
        result = await lookup_tag(db_session, tag_number="LKP-001", session_id=session.id, owner_id=test_user.id)
        assert result is not None
        assert result["close_tag_number"] == "LKP-001"
        assert result["slot_occurrence_id"] == str(closed.id)

    async def test_lookup_nonexistent_tag_returns_none(self, db_session: AsyncSession, test_user: User) -> None:
        session, _occ = await _started_with_open_slot(db_session, test_user)
        result = await lookup_tag(db_session, tag_number="NONEXIST", session_id=session.id, owner_id=test_user.id)
        assert result is None

    async def test_lookup_tag_cross_user_denied(self, db_session: AsyncSession, test_user: User) -> None:
        session, occ = await _started_with_open_slot(db_session, test_user)
        await close_slot(db_session, occurrence=occ, owner_id=test_user.id, tag_number="TAG")
        other_id = uuid.uuid4()
        with pytest.raises(ValueError, match="Session not found"):
            await lookup_tag(db_session, tag_number="TAG", session_id=session.id, owner_id=other_id)


# ---------------------------------------------------------------------------
# list_tag_violations
# ---------------------------------------------------------------------------


class TestListViolations:
    async def test_list_violations(self, db_session: AsyncSession, test_user: User) -> None:
        session, occ = await _started_with_open_slot(db_session, test_user)
        closed = await close_slot(db_session, occurrence=occ, owner_id=test_user.id, tag_number="ORIG")
        await verify_tag(db_session, occurrence=closed, provided_tag="WRONG", owner_id=test_user.id)
        violations = await list_tag_violations(db_session, session.id, test_user.id)
        assert len(violations) == 1
        assert violations[0].expected_tag == "ORIG"
        assert violations[0].provided_tag == "WRONG"

    async def test_list_violations_empty(self, db_session: AsyncSession, test_user: User) -> None:
        session, occ = await _started_with_open_slot(db_session, test_user)
        closed = await close_slot(db_session, occurrence=occ, owner_id=test_user.id, tag_number="OK")
        await verify_tag(db_session, occurrence=closed, provided_tag="OK", owner_id=test_user.id)
        violations = await list_tag_violations(db_session, session.id, test_user.id)
        assert len(violations) == 0

    async def test_list_violations_cross_user_denied(self, db_session: AsyncSession, test_user: User) -> None:
        session, occ = await _started_with_open_slot(db_session, test_user)
        await close_slot(db_session, occurrence=occ, owner_id=test_user.id, tag_number="ORIG")
        await verify_tag(db_session, occurrence=occ, provided_tag="WRONG", owner_id=test_user.id)
        other_id = uuid.uuid4()
        with pytest.raises(ValueError, match="Session not found"):
            await list_tag_violations(db_session, session.id, other_id)


# ---------------------------------------------------------------------------
# require_tag on slot rule
# ---------------------------------------------------------------------------


class TestRequireTagRule:
    async def test_require_tag_set_on_rule(self, db_session: AsyncSession, test_user: User) -> None:
        _, rule = await _draft_with_slot_rule(db_session, test_user, require_tag=True)
        assert rule.require_tag is True

    async def test_require_tag_default_false(self, db_session: AsyncSession, test_user: User) -> None:
        _, rule = await _draft_with_slot_rule(db_session, test_user)
        assert rule.require_tag is False
