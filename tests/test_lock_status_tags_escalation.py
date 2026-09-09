"""Tests for Lock Timer Status Tags Synchronization & Loser Escalation (ADR-200)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.locktimer.services.discipline_service import send_session_to_pillory
from app.locktimer.services.drafts import create_draft
from app.locktimer.services.gamification_extensions_service import (
    complete_obedience_challenge,
    fail_obedience_challenge,
    freeze_session_timer,
    roll_dice_of_fate,
    start_obedience_challenge,
    unfreeze_session_timer,
)
from app.locktimer.services.session import safety_stop, start_session
from app.models.locktimer import LockSession
from app.models.user import User
from app.services import identity_service


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"tag_user_{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("secret123"),
        display_name="Submissive Tagged",
        timezone="UTC",
        status_tags={"permanent": [], "standing": [], "dynamic": []},
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.fixture
async def active_session(db_session: AsyncSession, test_user: User) -> LockSession:
    now = datetime.now(UTC)
    draft = await create_draft(
        db_session,
        owner_id=test_user.id,
        duration_type="fixed",
        timezone_str="UTC",
    )
    draft.original_end_at = now + timedelta(days=2)
    draft.effective_end_at = now + timedelta(days=2)
    draft.pillory_enabled = True
    await db_session.flush()

    session = await start_session(db_session, session_id=draft.id, owner_id=test_user.id)
    assert session.state == "active"
    return session


@pytest.mark.asyncio
async def test_timer_lifecycle_status_tags(db_session: AsyncSession, active_session: LockSession, test_user: User):
    """Session start, freeze, unfreeze, and stop update user status tags synchronously."""
    # 1. Start session sets #chastity_locked and #in_lock_cycle
    assert identity_service.has_status_tag(test_user, "chastity_locked", "standing")
    assert identity_service.has_status_tag(test_user, "in_lock_cycle", "standing")

    # 2. Freeze session sets #frozen_timer
    await freeze_session_timer(db_session, active_session.id, test_user.id)
    assert identity_service.has_status_tag(test_user, "frozen_timer", "standing")

    # 3. Unfreeze session removes #frozen_timer and adds #thawed
    await unfreeze_session_timer(db_session, active_session.id, test_user.id)
    assert not identity_service.has_status_tag(test_user, "frozen_timer", "standing")
    assert identity_service.has_status_tag(test_user, "thawed", "dynamic")

    # 4. Pillory sets #pilloried
    await send_session_to_pillory(db_session, active_session, reason="test pillory")
    assert identity_service.has_status_tag(test_user, "pilloried", "standing")

    # 5. Safety stop cleans locked tags and adds #broken_lock and #punished
    await safety_stop(db_session, session_id=active_session.id, owner_id=test_user.id, reason_code="user_requested")
    assert not identity_service.has_status_tag(test_user, "chastity_locked", "standing")
    assert not identity_service.has_status_tag(test_user, "in_lock_cycle", "standing")
    assert not identity_service.has_status_tag(test_user, "pilloried", "standing")
    assert identity_service.has_status_tag(test_user, "broken_lock", "dynamic")
    assert identity_service.has_status_tag(test_user, "punished", "dynamic")


@pytest.mark.asyncio
async def test_challenge_status_tags(db_session: AsyncSession, active_session: LockSession, test_user: User):
    """Starting and completing/failing obedience challenges updates status tags."""
    # Start challenge -> #under_trial
    start_res = await start_obedience_challenge(db_session, active_session.id, test_user.id)
    assert start_res["success"] is True
    assert identity_service.has_status_tag(test_user, "under_trial", "dynamic")

    code = start_res["challenge"]["verification_code"]

    # Complete challenge -> removes #under_trial, adds #obedient
    comp_res = await complete_obedience_challenge(
        db_session,
        session_id=active_session.id,
        user_id=test_user.id,
        tag_number="TAG-101",
        verification_code=code,
        photo_notes="Completed",
    )
    assert comp_res["success"] is True
    assert not identity_service.has_status_tag(test_user, "under_trial", "dynamic")
    assert identity_service.has_status_tag(test_user, "obedient", "dynamic")

    # Start and fail challenge -> adds #disobedient
    await start_obedience_challenge(db_session, active_session.id, test_user.id)
    assert identity_service.has_status_tag(test_user, "under_trial", "dynamic")

    fail_res = await fail_obedience_challenge(db_session, active_session.id, test_user.id, reason="surrender")
    assert fail_res["success"] is True
    assert not identity_service.has_status_tag(test_user, "under_trial", "dynamic")
    assert identity_service.has_status_tag(test_user, "disobedient", "dynamic")
    assert not identity_service.has_status_tag(test_user, "obedient", "dynamic")


@pytest.mark.asyncio
async def test_bad_luck_escalation_process(test_user: User):
    """Direct testing of process_game_bad_luck escalation ladder."""
    # 1 bad luck: streak = 1, no tags
    streak, tags = identity_service.process_game_bad_luck(test_user, is_bad=True, current_streak=0)
    assert streak == 1
    assert tags == []
    assert not identity_service.has_status_tag(test_user, "unlucky")

    # 2 bad lucks: streak = 2 -> #unlucky (dynamic)
    streak, tags = identity_service.process_game_bad_luck(test_user, is_bad=True, current_streak=streak)
    assert streak == 2
    assert "#unlucky" in tags
    assert identity_service.has_status_tag(test_user, "unlucky", "dynamic")

    # 3 bad lucks: streak = 3 -> #loser (standing)
    streak, tags = identity_service.process_game_bad_luck(test_user, is_bad=True, current_streak=streak)
    assert streak == 3
    assert "#loser" in tags
    assert identity_service.has_status_tag(test_user, "loser", "standing")

    # 4 bad lucks: streak = 4 -> #pathetic_loser (permanent!)
    streak, tags = identity_service.process_game_bad_luck(test_user, is_bad=True, current_streak=streak)
    assert streak == 4
    assert "#pathetic_loser" in tags
    assert identity_service.has_status_tag(test_user, "pathetic_loser", "permanent")

    # Jackpot redemption: resets streak, removes #unlucky and #loser
    streak, tags = identity_service.process_game_bad_luck(
        test_user, is_bad=False, is_jackpot=True, current_streak=streak
    )
    assert streak == 0
    assert not identity_service.has_status_tag(test_user, "unlucky", "dynamic")
    assert not identity_service.has_status_tag(test_user, "loser", "standing")
    # Note: permanent pathetic_loser remains as a lasting badge of fortune
    assert identity_service.has_status_tag(test_user, "pathetic_loser", "permanent")


@pytest.mark.asyncio
async def test_games_streak_integration(db_session: AsyncSession, active_session: LockSession, test_user: User):
    """Mini-games track bad_luck_streak in session.extensions_state."""
    # Simulate a bad dice roll (dice sum <= 5) by setting streak directly or running games
    active_session.extensions_state = {"bad_luck_streak": 2}
    await db_session.flush()

    # Call dice roll with force
    res = await roll_dice_of_fate(db_session, active_session.id, test_user.id, force=True)
    assert res["success"] is True
    assert "bad_luck_streak" in res
    assert "escalated_tags" in res
