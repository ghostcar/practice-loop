"""Tests for LockSession Permanent Timer Freeze & Unfreeze (ADR-199)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_access_token, hash_password
from app.locktimer.repositories import get_session
from app.locktimer.services.drafts import create_draft
from app.locktimer.services.gamification_extensions_service import (
    complete_obedience_challenge,
    freeze_session_timer,
    get_game_actions_history,
    start_obedience_challenge,
    unfreeze_session_timer,
)
from app.locktimer.services.session import start_session
from app.main import app
from app.models.locktimer import LockSession
from app.models.user import User


@pytest.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        email=f"freeze_user_{uuid.uuid4().hex[:6]}@example.com",
        password_hash=hash_password("secret123"),
        display_name="Submissive Ice",
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
    draft.original_end_at = now + timedelta(days=3)
    draft.effective_end_at = now + timedelta(days=3)
    await db_session.flush()

    session = await start_session(db_session, session_id=draft.id, owner_id=test_user.id)
    assert session.state == "active"
    return session


@pytest.mark.asyncio
async def test_freeze_session_timer(db_session: AsyncSession, active_session: LockSession, test_user: User):
    """Freezing an active session halts the clock and records remaining seconds."""
    res = await freeze_session_timer(db_session, active_session.id, test_user.id, reason="manual")
    assert res["success"] is True
    assert res["is_frozen"] is True
    assert res["frozen_remaining_seconds"] > 0

    # Reload session
    session = await get_session(db_session, active_session.id, test_user.id)
    assert session.is_frozen is True
    assert session.frozen_at is not None
    assert session.frozen_remaining_seconds == res["frozen_remaining_seconds"]

    # History logged
    history = await get_game_actions_history(db_session, active_session.id, limit=5)
    assert any(a.extension_type == "timer_freeze" for a in history)

    # Freezing again reports already_frozen
    res_repeat = await freeze_session_timer(db_session, active_session.id, test_user.id)
    assert res_repeat["success"] is True
    assert res_repeat.get("already_frozen") is True


@pytest.mark.asyncio
async def test_unfreeze_session_timer(db_session: AsyncSession, active_session: LockSession, test_user: User):
    """Unfreezing a session resumes countdown from the recorded remaining duration."""
    # First freeze
    freeze_res = await freeze_session_timer(db_session, active_session.id, test_user.id, reason="manual")
    assert freeze_res["success"] is True
    frozen_seconds = freeze_res["frozen_remaining_seconds"]

    # Now unfreeze
    unfreeze_res = await unfreeze_session_timer(db_session, active_session.id, test_user.id)
    assert unfreeze_res["success"] is True
    assert unfreeze_res["is_frozen"] is False
    assert "effective_end_at" in unfreeze_res

    # Verify session state
    session = await get_session(db_session, active_session.id, test_user.id)
    assert session.is_frozen is False
    assert session.frozen_at is None
    assert session.frozen_remaining_seconds is None

    # Verify new effective_end_at roughly matches now + frozen_seconds
    now = datetime.now(UTC)
    delta = (session.effective_end_at.replace(tzinfo=UTC) - now).total_seconds()
    assert abs(delta - frozen_seconds) < 5

    # Check unfreeze action in history
    history = await get_game_actions_history(db_session, active_session.id, limit=5)
    assert any(a.extension_type == "timer_unfreeze" for a in history)

    # Unfreezing an already ticking session reports already_unfrozen
    unfreeze_again = await unfreeze_session_timer(db_session, active_session.id, test_user.id)
    assert unfreeze_again["success"] is True
    assert unfreeze_again.get("already_unfrozen") is True


@pytest.mark.asyncio
async def test_obedience_challenge_lifts_freeze(db_session: AsyncSession, active_session: LockSession, test_user: User):
    """Completing an obedience challenge automatically unfreezes a frozen timer."""
    # Freeze session
    await freeze_session_timer(db_session, active_session.id, test_user.id)
    session = await get_session(db_session, active_session.id, test_user.id)
    assert session.is_frozen is True

    # Start obedience challenge
    start_res = await start_obedience_challenge(db_session, active_session.id, test_user.id)
    assert start_res["success"] is True
    code = start_res["challenge"]["verification_code"]

    # Complete obedience challenge
    comp_res = await complete_obedience_challenge(
        db_session,
        session_id=active_session.id,
        user_id=test_user.id,
        tag_number="TAG-001",
        verification_code=code,
        photo_notes="Proof submitted",
    )
    assert comp_res["success"] is True

    # Check session unfreezed
    session = await get_session(db_session, active_session.id, test_user.id)
    assert session.is_frozen is False
    assert session.frozen_at is None


@pytest.mark.asyncio
async def test_freeze_unfreeze_api_endpoints(db_session: AsyncSession, active_session: LockSession, test_user: User):
    """HTTP API endpoints for freeze and unfreeze return correct responses for Bearer and Cookie clients."""
    token = create_access_token(test_user.id)
    csrf = secrets.token_hex(32)
    cookies = {"access_token": token, "csrf_token": csrf}

    # 1. Bearer Client -> JSON 200
    bearer_headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", headers=bearer_headers) as ac:
        # Freeze
        r_freeze = await ac.post(f"/api/v2/locktimer/sessions/{active_session.id}/freeze")
        assert r_freeze.status_code == 200
        data_f = r_freeze.json()
        assert data_f["success"] is True
        assert data_f["is_frozen"] is True

        # Unfreeze
        r_unfreeze = await ac.post(f"/api/v2/locktimer/sessions/{active_session.id}/unfreeze")
        assert r_unfreeze.status_code == 200
        data_u = r_unfreeze.json()
        assert data_u["success"] is True
        assert data_u["is_frozen"] is False

    # 2. Cookie Client -> 303 Redirect to session detail
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test", cookies=cookies) as ac:
        r_cookie_freeze = await ac.post(
            f"/api/v2/locktimer/sessions/{active_session.id}/freeze",
            data={"csrf_token": csrf},
            headers={"X-CSRF-Token": csrf},
        )
        assert r_cookie_freeze.status_code == 303
        assert r_cookie_freeze.headers["location"].endswith(f"/locktimer/sessions/{active_session.id}")
