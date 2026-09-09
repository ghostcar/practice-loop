"""Tests for LockSession discipline protocol, verification challenges, and Pillory integration (ADR-197)."""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer import enums as e
from app.locktimer.services.discipline_service import (
    apply_pillory_vote_to_session,
    create_session_verification_challenge,
    get_active_session_challenge,
    send_session_to_pillory,
    verify_session_photo_submission,
)
from app.locktimer.services.drafts import create_draft, update_draft
from app.models.locktimer import LockSession
from app.models.user import User


@pytest.fixture
async def sample_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email=f"test_lock_{secrets.token_hex(4)}@example.com",
        password_hash="testpasshash",
        locale="ru",
        theme="dark",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def draft_session(db_session: AsyncSession, sample_user: User) -> LockSession:
    session = await create_draft(
        db_session,
        owner_id=sample_user.id,
        duration_type="duration_from_start",
        timezone_str="Europe/Moscow",
    )
    return session


@pytest.mark.asyncio
async def test_draft_update_discipline_and_verification_fields(
    db_session: AsyncSession,
    draft_session: LockSession,
):
    """Test updating discipline policy, verification protocol and Pillory settings in draft."""
    policy = {
        "penalty_points": 75,
        "penalty_time_minutes": 90,
        "penalty_tasks_enabled": True,
        "escalation_multiplier": 1.5,
    }
    updated = await update_draft(
        db_session,
        draft_session,
        mode="open_ended",
        current_tag_number="TAG-7712",
        discipline_policy=policy,
        verification_required=True,
        verification_frequency_hours=12,
        verification_mode="community",
        pillory_enabled=True,
        pillory_auto_extend=True,
    )

    assert updated.mode == "open_ended"
    assert updated.current_tag_number == "TAG-7712"
    assert updated.discipline_policy["penalty_points"] == 75
    assert updated.discipline_policy["penalty_time_minutes"] == 90
    assert updated.discipline_policy["penalty_tasks_enabled"] is True
    assert updated.verification_required is True
    assert updated.verification_frequency_hours == 12
    assert updated.verification_mode == "community"
    assert updated.pillory_enabled is True
    assert updated.pillory_auto_extend is True


@pytest.mark.asyncio
async def test_verification_challenge_lifecycle(
    db_session: AsyncSession,
    draft_session: LockSession,
    sample_user: User,
):
    """Test generation and constant-time verification of one-time challenge code."""
    challenge, code = await create_session_verification_challenge(
        db_session,
        session_id=draft_session.id,
        owner_id=sample_user.id,
        ttl_minutes=30,
        code_length=6,
    )
    assert len(code) == 6
    assert challenge.state == "active"

    # Active lookup
    active = await get_active_session_challenge(db_session, draft_session.id, sample_user.id)
    assert active is not None
    assert active.id == challenge.id

    # Wrong code attempt
    res_wrong = await verify_session_photo_submission(
        db_session,
        session_id=draft_session.id,
        owner_id=sample_user.id,
        tag_number="TAG-001",
        verification_code="000000",
    )
    assert res_wrong["success"] is False
    assert "Неверный проверочный код" in res_wrong["error"]

    # Valid code attempt
    res_valid = await verify_session_photo_submission(
        db_session,
        session_id=draft_session.id,
        owner_id=sample_user.id,
        tag_number="TAG-001",
        verification_code=code,
    )
    assert res_valid["success"] is True
    assert res_valid["tag_number"] == "TAG-001"

    # Challenge consumed
    await db_session.refresh(challenge)
    assert challenge.state == "consumed"


@pytest.mark.asyncio
async def test_pillory_auto_extend_effects(
    db_session: AsyncSession,
    sample_user: User,
):
    """Test community votes extending or reducing active session timer."""
    now = datetime.now(UTC)
    session = LockSession(
        id=uuid.uuid4(),
        owner_id=sample_user.id,
        state=e.SESSION_ACTIVE,
        duration_type="duration_from_start",
        timezone="UTC",
        effective_end_at=now + timedelta(hours=2),
        pillory_enabled=True,
        pillory_auto_extend=True,
        random_seed_encrypted="seed",
        random_seed_commitment="seed",
        created_at=now,
        updated_at=now,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    from app.timeutils import as_utc

    init_end = as_utc(session.effective_end_at)

    # Vote add_15m
    res_15m = await apply_pillory_vote_to_session(db_session, session, "add_15m")
    assert res_15m["applied"] is True
    assert session.effective_end_at == init_end + timedelta(minutes=15)

    # Vote add_1h
    res_1h = await apply_pillory_vote_to_session(db_session, session, "add_1h")
    assert res_1h["applied"] is True
    assert session.effective_end_at == init_end + timedelta(minutes=75)

    # Vote sub_15m
    res_sub = await apply_pillory_vote_to_session(db_session, session, "sub_15m")
    assert res_sub["applied"] is True
    assert session.effective_end_at == init_end + timedelta(minutes=60)


@pytest.mark.asyncio
async def test_send_to_pillory_publishes_social_item(
    db_session: AsyncSession,
    sample_user: User,
):
    """Test send_session_to_pillory creates a public SocialPublication under tracker.pillory."""
    now = datetime.now(UTC)
    session = LockSession(
        id=uuid.uuid4(),
        owner_id=sample_user.id,
        state=e.SESSION_ACTIVE,
        duration_type="duration_from_start",
        timezone="UTC",
        pillory_enabled=True,
        current_tag_number="TAG-PILLORY-1",
        random_seed_encrypted="seed",
        random_seed_commitment="seed",
        created_at=now,
        updated_at=now,
    )
    db_session.add(session)
    await db_session.commit()
    await db_session.refresh(session)

    published = await send_session_to_pillory(
        db_session,
        session,
        reason="Срыв ношения",
        details="Зафиксировано снятие пояса",
    )
    assert published is True

    from app.platform.social.models import SocialPublication

    pub_res = await db_session.execute(
        select(SocialPublication).where(
            SocialPublication.owner_id == sample_user.id,
            SocialPublication.subject_namespace == "tracker.pillory",
            SocialPublication.is_active.is_(True),
        )
    )
    pub = pub_res.scalar_one_or_none()
    assert pub is not None
    assert "Нарушение регламента: Срыв ношения" in pub.snapshot["title"]
    assert pub.snapshot["tag_number"] == "TAG-PILLORY-1"
