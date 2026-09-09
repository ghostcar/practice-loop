"""Tests for LockSession Gamification Extensions & Mini-Games (ADR-198)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password
from app.locktimer.repositories import get_session
from app.locktimer.services.drafts import create_draft
from app.locktimer.services.gamification_extensions_service import (
    complete_obedience_challenge,
    fail_obedience_challenge,
    get_game_actions_history,
    roll_dice_of_fate,
    spin_wheel_of_fortune,
    start_obedience_challenge,
    trigger_time_jump,
)
from app.locktimer.services.session import start_session
from app.main import app
from app.models.locktimer import LockGameAction, LockSession
from app.models.user import User


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"game_user_{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("secret123"),
        display_name="Submissive Gamer",
        timezone="UTC",
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
async def test_wheel_of_fortune_spin(db_session: AsyncSession, active_session: LockSession, test_user: User):
    """Wheel spin adjusts time or XP, logs action, and activates cooldown."""
    orig_end = active_session.effective_end_at

    res = await spin_wheel_of_fortune(db_session, active_session.id, test_user.id, force=True)
    assert res["success"] is True
    assert "sector" in res
    assert "result_display" in res

    # Check game action logged
    history = await get_game_actions_history(db_session, active_session.id, limit=5)
    assert len(history) >= 1
    assert any(a.extension_type == "wheel_of_fortune" for a in history)

    # Check cooldown rejected without force
    res_cooldown = await spin_wheel_of_fortune(db_session, active_session.id, test_user.id, force=False)
    assert res_cooldown["success"] is False
    assert "перезаряжается" in res_cooldown["error"]


@pytest.mark.asyncio
async def test_dice_of_fate_roll(db_session: AsyncSession, active_session: LockSession, test_user: User):
    """Dice of fate rolls 2d6 and persists result action."""
    res = await roll_dice_of_fate(db_session, active_session.id, test_user.id, force=True)
    assert res["success"] is True
    assert 1 <= res["dice_1"] <= 6
    assert 1 <= res["dice_2"] <= 6
    assert 2 <= res["sum"] <= 12
    assert "result_display" in res

    history = await get_game_actions_history(db_session, active_session.id, limit=5)
    assert any(a.extension_type == "dice_of_fate" for a in history)


@pytest.mark.asyncio
async def test_obedience_challenge_lifecycle_success(
    db_session: AsyncSession, active_session: LockSession, test_user: User
):
    """Full lifecycle: start challenge -> verify photo code -> claim reward."""
    start_res = await start_obedience_challenge(
        db_session, active_session.id, test_user.id, challenge_type="kneeling_repentance"
    )
    assert start_res["success"] is True
    ch = start_res["challenge"]
    assert ch["type"] == "kneeling_repentance"
    code = ch["verification_code"]
    assert len(code) == 6

    # Complete challenge with correct code
    comp_res = await complete_obedience_challenge(
        db_session,
        session_id=active_session.id,
        user_id=test_user.id,
        tag_number="TAG-777",
        verification_code=code,
        photo_notes="Поза покаяния выполнена",
    )
    assert comp_res["success"] is True
    assert comp_res["reward_xp"] == 50
    assert comp_res["time_applied_seconds"] < 0  # reduced time

    # Challenge cleared from active state
    refreshed = await get_session(db_session, active_session.id, test_user.id)
    assert refreshed.extensions_state.get("active_challenge") is None


@pytest.mark.asyncio
async def test_obedience_challenge_surrender_penalty(
    db_session: AsyncSession, active_session: LockSession, test_user: User
):
    """Surrendering active challenge applies time penalty and logs failure."""
    start_res = await start_obedience_challenge(
        db_session, active_session.id, test_user.id, challenge_type="sissy_pet_gear"
    )
    assert start_res["success"] is True

    fail_res = await fail_obedience_challenge(
        db_session, active_session.id, test_user.id, reason="refusal"
    )
    assert fail_res["success"] is True
    assert fail_res["time_applied_seconds"] > 0  # time added
    assert fail_res["penalty_xp"] == -100

    history = await get_game_actions_history(db_session, active_session.id, limit=5)
    assert any(a.result_code == "challenge_failed" for a in history)


@pytest.mark.asyncio
async def test_time_jump(db_session: AsyncSession, active_session: LockSession, test_user: User):
    """AI Keyholder time jump shifts clock and records action."""
    res = await trigger_time_jump(db_session, active_session.id, test_user.id)
    assert res["success"] is True
    assert "Временная аномалия" in res["result_display"]


@pytest.mark.asyncio
async def test_api_games_endpoints(db_session: AsyncSession, active_session: LockSession, test_user: User):
    """HTTP API endpoints for wheel-spin and dice-roll return successful responses."""
    import secrets
    from app.auth import create_access_token

    token = create_access_token(test_user.id)
    csrf = secrets.token_hex(32)
    cookies = {"access_token": token, "csrf_token": csrf}
    headers = {"Accept": "application/json", "X-CSRF-Token": csrf}

    # 1. Bearer client gets JSONResponse
    bearer_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=bearer_headers) as ac:
        r_wheel = await ac.post(
            f"/api/v2/locktimer/sessions/{active_session.id}/games/wheel-spin",
            data={"force": "true"},
        )
        assert r_wheel.status_code == 200
        data = r_wheel.json()
        assert data["success"] is True

        r_dice = await ac.post(
            f"/api/v2/locktimer/sessions/{active_session.id}/games/dice-roll",
            data={"force": "true"},
        )
        assert r_dice.status_code == 200
        assert r_dice.json()["success"] is True

    # 2. Cookie client gets 303 Redirect to session detail
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies=cookies) as ac:
        r_cookie = await ac.post(
            f"/api/v2/locktimer/sessions/{active_session.id}/games/wheel-spin",
            data={"force": "true", "csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert r_cookie.status_code == 303
        assert r_cookie.headers["location"].endswith("#games")
