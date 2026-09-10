"""Tests for Universal Omni-Pillory and disciplinary hold (ADR-206 Stage 4)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.locktimer import LockSession
from app.models.pillory import PilloryEntry
from app.models.user import User
from app.services.discipline_engine import record_violation
from app.services.identity_service import get_active_tags
from app.services.pillory_service import (
    create_pillory_entry,
    extend_pillory_entry,
    get_pillory_entry,
    list_active_pillory_entries,
    soften_pillory_entry,
    submit_repentance,
)


@pytest.mark.asyncio
async def test_create_pillory_entry_multi_triggers(db_session: AsyncSession, test_user: User):
    """Verify independent pillory entries per trigger with disciplinary multiplier scaling."""
    test_user.prefs = {
        "discipline_level": 2,  # Level 2 => mult = 3.0
        "base_severity_multiplier": 2.0,  # Effective multiplier = 2.0 * 3.0 = 6.0
    }
    db_session.add(test_user)
    await db_session.flush()

    # Trigger 1: Late check
    e1 = await create_pillory_entry(
        db_session,
        test_user,
        trigger="late_check",
        title="Опоздание с фотоотчетом",
        reason="Таймер инспекции истек",
        duration_minutes=30,
        freeze_lock_timer=False,
    )
    assert e1.trigger == "late_check"
    assert e1.status == "active"
    # 30 min * 6.0 = 180 min
    assert e1.initial_duration_minutes == 180
    assert e1.current_duration_minutes == 180

    # Trigger 2: Wheel spin
    e2 = await create_pillory_entry(
        db_session,
        test_user,
        trigger="wheel_spin",
        title="Колесо фортуны",
        reason="Сектор Позорный столб",
        duration_minutes=60,
        freeze_lock_timer=False,
    )
    assert e2.trigger == "wheel_spin"
    # 60 min * 6.0 = 360 min
    assert e2.initial_duration_minutes == 360

    active = await list_active_pillory_entries(db_session, test_user.id)
    assert len(active) == 2
    triggers = {e.trigger for e in active}
    assert triggers == {"late_check", "wheel_spin"}

    tags = get_active_tags(test_user)
    assert "#pilloried" in tags


@pytest.mark.asyncio
async def test_pillory_freeze_escalation_at_four_extensions(db_session: AsyncSession, test_user: User):
    """Verify extensions increase duration and trigger timer freeze escalation at >= 4 extensions."""
    test_user.prefs = {
        "discipline_level": 0,
        "base_severity_multiplier": 1.0,  # multiplier = 1.0
    }
    db_session.add(test_user)
    await db_session.flush()

    # Active lock session
    now = datetime.now(UTC)
    session = LockSession(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        state="active",
        mode="scheduled",
        effective_end_at=now + timedelta(hours=24),
        random_seed_encrypted="dummy_enc",
        random_seed_commitment="dummy_com",
        is_frozen=False,
    )
    db_session.add(session)
    await db_session.flush()

    entry = await create_pillory_entry(
        db_session,
        test_user,
        trigger="manual",
        title="Дисциплинарное взыскание",
        reason="Тест эскалации заморозки",
        duration_minutes=60,
        lock_session=session,
        freeze_lock_timer=True,
    )
    assert session.is_frozen is True
    initial_frozen = session.frozen_remaining_seconds or 0

    # Extensions 1, 2, 3: no extra freeze escalation yet
    for i in range(1, 4):
        res = await extend_pillory_entry(db_session, entry, test_user)
        assert res["extensions_count"] == i
        assert res["freeze_added_minutes"] == 0

    assert entry.freeze_timer_minutes == 0

    # 4th extension: threshold reached -> freeze penalty connected!
    res4 = await extend_pillory_entry(db_session, entry, test_user)
    assert res4["extensions_count"] == 4
    assert res4["freeze_added_minutes"] == 15
    assert entry.freeze_timer_minutes == 15
    # Check that lock session freeze penalty increased
    assert (session.frozen_remaining_seconds or 0) >= initial_frozen + (15 * 60)

    # 5th extension: escalation step added (15 + 5 = 20 min)
    res5 = await extend_pillory_entry(db_session, entry, test_user)
    assert res5["extensions_count"] == 5
    assert res5["freeze_added_minutes"] == 20
    assert entry.freeze_timer_minutes == 35


@pytest.mark.asyncio
async def test_pillory_soften(db_session: AsyncSession, test_user: User):
    """Verify softening reduces duration with lower bounds."""
    test_user.prefs = {"discipline_level": 0, "base_severity_multiplier": 1.0}
    entry = await create_pillory_entry(
        db_session,
        test_user,
        trigger="manual",
        title="Наказание",
        reason="Смягчение",
        duration_minutes=30,
        freeze_lock_timer=False,
    )
    res = await soften_pillory_entry(db_session, entry, test_user)
    assert res["softens_count"] == 1
    assert res["subtracted_minutes"] == 10
    assert entry.current_duration_minutes == 20

    # Soften down to minimum
    await soften_pillory_entry(db_session, entry, test_user)
    await soften_pillory_entry(db_session, entry, test_user)
    assert entry.current_duration_minutes == 5


@pytest.mark.asyncio
async def test_pillory_repentance_and_timer_unfreeze(db_session: AsyncSession, test_user: User):
    """Verify repentance completes pillory entry, removes #pilloried tag and unfreezes timer."""
    now = datetime.now(UTC)
    session = LockSession(
        id=uuid.uuid4(),
        owner_id=test_user.id,
        state="active",
        mode="scheduled",
        effective_end_at=now + timedelta(hours=24),
        random_seed_encrypted="dummy_enc",
        random_seed_commitment="dummy_com",
        is_frozen=False,
    )
    db_session.add(session)
    await db_session.flush()

    entry = await create_pillory_entry(
        db_session,
        test_user,
        trigger="late_check",
        title="Опоздание",
        reason="Пропуск проверки",
        duration_minutes=60,
        lock_session=session,
        freeze_lock_timer=True,
    )
    assert session.is_frozen is True
    assert "#pilloried" in get_active_tags(test_user)

    # Submit repentance
    rep_res = await submit_repentance(
        db_session,
        entry,
        test_user,
        photo_url="https://media.local/repent.jpg",
        notes="Искреннее раскаяние",
    )
    assert rep_res["status"] == "completed"
    assert rep_res["remaining_pillory_count"] == 0
    assert rep_res["unfrozen_timer"] is True

    # Lock session should be unfrozen
    assert session.is_frozen is False
    assert "#pilloried" not in get_active_tags(test_user)


@pytest.mark.asyncio
async def test_pillory_autonomous_mode_without_belt(db_session: AsyncSession, test_user: User):
    """Verify autonomous pillory operates normally when no chastity session exists."""
    entry = await create_pillory_entry(
        db_session,
        test_user,
        trigger="medication_missed",
        title="Пропуск медикаментов",
        reason="Курс антибиотиков нарушен",
        duration_minutes=45,
        freeze_lock_timer=False,
    )
    assert entry.lock_session_id is None
    assert entry.status == "active"
    assert entry.config.get("media_shame") is True
    assert "#pilloried" in get_active_tags(test_user)

    fetched = await get_pillory_entry(db_session, entry.id, test_user.id)
    assert fetched is not None
    assert fetched.trigger == "medication_missed"
