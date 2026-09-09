"""Tests for Open-Ended Wear Mode & Reactive Engine (ADR-195)."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.pipeline.keyholder import classify_wear_unlock_reason
from app.models.journal import JournalEntry
from app.models.points import PointsTransaction
from app.models.user import User
from app.services import wear_reactive_service as wear_svc


@pytest.mark.asyncio
async def test_open_ended_session_lifecycle_and_timer(db_session: AsyncSession, test_user: User):
    """Verifies get_or_create_open_ended_session, status seconds, and unlock/relock lifecycle."""
    # 1. Ensure active open-ended session
    session = await wear_svc.get_or_create_open_ended_session(db_session, test_user.id)
    assert session is not None
    assert session.mode == "open_ended"
    assert session.is_currently_locked is True

    # 2. Get wear status
    status = await wear_svc.get_wear_status(db_session, test_user.id)
    assert status["is_locked"] is True
    assert "Заперт" in status["time_text"]
    assert "сек." in status["time_text"]

    # 3. Record unlock event (hygiene quick)
    open_log, reactions = await wear_svc.record_unlock_event(
        db_session,
        test_user.id,
        event_code="hygiene_quick",
        duration_minutes=10,
        user_comment="Быстрый душ",
    )
    assert open_log.state_before == "locked"
    assert open_log.state_after == "unlocked"
    assert open_log.expected_relock_at is not None

    status_after_open = await wear_svc.get_wear_status(db_session, test_user.id)
    assert status_after_open["is_locked"] is False
    assert "Снят" in status_after_open["time_text"]
    assert "⏳ До закрытия" in status_after_open["deadline_text"]

    # 4. Record relock on time (no penalty)
    relock_log, relock_reactions = await wear_svc.record_relock_event(
        db_session,
        test_user.id,
        tag_number="SEAL-1234",
        comfort_score=5,
    )
    assert relock_log.state_after == "locked"
    assert relock_log.tag_number == "SEAL-1234"
    assert relock_log.comfort_score == 5
    assert "delay_penalty" not in relock_reactions

    status_after_relock = await wear_svc.get_wear_status(db_session, test_user.id)
    assert status_after_relock["is_locked"] is True
    assert status_after_relock["current_tag"] == "SEAL-1234"
    assert status_after_relock["last_comfort"] == 5


@pytest.mark.asyncio
async def test_strict_delay_penalty(db_session: AsyncSession, test_user: User):
    """Verifies that any second past expected_relock_at triggers a strict penalty."""
    # 1. Unlock with past deadline
    now = datetime.now(UTC)
    open_log, _ = await wear_svc.record_unlock_event(
        db_session,
        test_user.id,
        event_code="hygiene_quick",
        duration_minutes=5,
    )
    # Simulate past expected deadline by 15 seconds
    open_log.expected_relock_at = now - timedelta(seconds=15)
    await db_session.commit()

    # 2. Check overdue status
    status = await wear_svc.get_wear_status(db_session, test_user.id)
    assert status["is_overdue"] is True
    assert "ПРОСРОЧЕНО" in status["deadline_text"]

    # 3. Relock with overdue -> strict penalty
    relock_log, relock_reactions = await wear_svc.record_relock_event(
        db_session,
        test_user.id,
        tag_number="SEAL-9999",
    )
    assert "delay_penalty" in relock_reactions
    dp = relock_reactions["delay_penalty"]
    assert dp["overdue_seconds"] >= 15
    assert dp["amount"] < 0  # penalty is negative

    # Verify transaction in database
    txs = (
        await db_session.execute(
            select(PointsTransaction).where(
                PointsTransaction.user_id == test_user.id,
                PointsTransaction.transaction_type == "penalty",
            )
        )
    ).scalars().all()
    assert len(txs) >= 1
    assert any("опоздание" in (tx.reason or "").lower() for tx in txs)


@pytest.mark.asyncio
async def test_sex_unlock_creates_sexual_journal_entry(db_session: AsyncSession, test_user: User):
    """Verifies that unlocking for sex triggers a draft JournalEntry in Sexual Journal."""
    open_log, reactions = await wear_svc.record_unlock_event(
        db_session,
        test_user.id,
        event_code="sex_activity",
        duration_minutes=90,
        user_comment="Близость с партнером",
    )
    assert "sexual_journal_id" in reactions
    journal_id = uuid.UUID(reactions["sexual_journal_id"])

    journal_entry = (
        await db_session.execute(select(JournalEntry).where(JournalEntry.id == journal_id))
    ).scalar_one_or_none()
    assert journal_entry is not None
    assert journal_entry.activity_type == "Секс (снятие пояса)"
    assert journal_entry.status == "draft"


@pytest.mark.asyncio
async def test_seal_inspection_without_unlock(db_session: AsyncSession, test_user: User):
    """Verifies that seal inspection verifies tag without unlocking the device."""
    session = await wear_svc.get_or_create_open_ended_session(db_session, test_user.id)
    assert session.is_currently_locked is True

    inspection_log = await wear_svc.record_seal_inspection(
        db_session,
        test_user.id,
        tag_number="INSPECT-4444",
        comfort_score=4,
        notes="Пломба целая, натяжение в норме",
    )
    assert inspection_log.event_code == "seal_inspection"
    assert inspection_log.state_before == "locked"
    assert inspection_log.state_after == "locked"
    assert inspection_log.tag_number == "INSPECT-4444"

    status = await wear_svc.get_wear_status(db_session, test_user.id)
    assert status["is_locked"] is True
    assert status["current_tag"] == "INSPECT-4444"
    assert status["last_comfort"] == 4


@pytest.mark.asyncio
async def test_orgasm_event_records_in_journal(db_session: AsyncSession, test_user: User):
    """Verifies that orgasm release is logged independently into Sexual Journal."""
    orgasm_log, reactions = await wear_svc.record_orgasm_event(
        db_session,
        test_user.id,
        orgasms_count=2,
        notes="Разрешенный оргазм",
    )
    assert orgasm_log.event_code == "orgasm_release"
    assert "sexual_journal_id" in reactions

    journal_id = uuid.UUID(reactions["sexual_journal_id"])
    journal_entry = (
        await db_session.execute(select(JournalEntry).where(JournalEntry.id == journal_id))
    ).scalar_one_or_none()
    assert journal_entry is not None
    assert journal_entry.orgasms == 2


@pytest.mark.asyncio
async def test_wear_reason_classifier_fallback():
    """Verifies heuristic classification when LLM is unavailable."""
    res_pain = await classify_wear_unlock_reason("Очень болит и натерло шов", llm_config=None)
    assert res_pain["event_code"] == "force_majeure"

    res_sex = await classify_wear_unlock_reason("Хотим заняться сексом", llm_config=None)
    assert res_sex["event_code"] == "sex_activity"
    assert res_sex["duration_minutes"] == 90

    res_sport = await classify_wear_unlock_reason("Иду на тренировку в зал", llm_config=None)
    assert res_sport["event_code"] == "sport_workout"

    res_hygiene = await classify_wear_unlock_reason("Хочу помыться", llm_config=None)
    assert res_hygiene["event_code"] == "hygiene_quick"
    assert res_hygiene["duration_minutes"] == 10


@pytest.mark.asyncio
async def test_no_active_session_initially(db_session: AsyncSession, test_user: User):
    """Verifies that user without active session is reported as inactive and can start wear."""
    status = await wear_svc.get_wear_status(db_session, test_user.id)
    assert status["is_active"] is False
    assert status["is_locked"] is False
    assert status["session"] is None

    # Start wear
    session, initial_log = await wear_svc.start_open_ended_session(
        db_session, test_user.id, tag_number="START-1111"
    )
    assert session.state == "active"
    assert session.is_currently_locked is True
    assert session.current_tag_number == "START-1111"

    status_started = await wear_svc.get_wear_status(db_session, test_user.id)
    assert status_started["is_active"] is True
    assert status_started["is_locked"] is True
    assert status_started["current_tag"] == "START-1111"

    # Finish wear
    finished_session = await wear_svc.finish_open_ended_session(db_session, test_user.id)
    assert finished_session.state == "completed"

    status_finished = await wear_svc.get_wear_status(db_session, test_user.id)
    assert status_finished["is_active"] is False


@pytest.mark.asyncio
async def test_device_supports_tag_logic():
    """Verifies recognition of tag/seal capability from extra_properties."""
    from app.models.life import InventoryItem

    # None item defaults to True
    assert wear_svc.device_supports_tag(None) is True

    # Empty extra_properties defaults to True
    item1 = InventoryItem(name="Cage 1", category="wearable", extra_properties={})
    assert wear_svc.device_supports_tag(item1) is True

    # Explicit False
    item2 = InventoryItem(name="Cage 2", category="wearable", extra_properties={"supports_tag": False})
    assert wear_svc.device_supports_tag(item2) is False

    # String "false"
    item3 = InventoryItem(name="Cage 3", category="wearable", extra_properties={"can_seal": "false"})
    assert wear_svc.device_supports_tag(item3) is False

    # Supports seal True
    item4 = InventoryItem(name="Cage 4", category="wearable", extra_properties={"supports_seal": True})
    assert wear_svc.device_supports_tag(item4) is True


@pytest.mark.asyncio
async def test_device_selection_and_inventory_status_cycle(db_session: AsyncSession, test_user: User):
    """Verifies that selecting an inventory item transitions status to in_use and back to available."""
    from app.models.life import InventoryItem

    # Create inventory device
    device = InventoryItem(
        user_id=test_user.id,
        category="wearable",
        group_type="equipment",
        name="Steel Chastity Cage X",
        inventory_status="available",
        extra_properties={"supports_tag": True},
    )
    db_session.add(device)
    await db_session.commit()
    await db_session.refresh(device)

    # 1. User devices search
    devices = await wear_svc.get_user_chastity_devices(db_session, test_user.id)
    assert any(d.id == device.id for d in devices)

    # 2. Start wear session bound to this device
    session, log = await wear_svc.start_open_ended_session(
        db_session,
        test_user.id,
        tag_number="DEV-9999",
        device_id=device.id,
    )
    assert session.device_id == device.id
    assert session.chastity_device_id == device.id

    # Check device transitioned to 'in_use'
    await db_session.refresh(device)
    assert device.inventory_status == "in_use"

    # Status contains device info and supports_tag
    status = await wear_svc.get_wear_status(db_session, test_user.id)
    assert status["is_active"] is True
    assert status["device"] is not None
    assert status["device"].id == device.id
    assert status["supports_tag"] is True

    # 3. Finish wear session -> device transitions back to 'available'
    await wear_svc.finish_open_ended_session(db_session, test_user.id)
    await db_session.refresh(device)
    assert device.inventory_status == "available"


@pytest.mark.asyncio
async def test_device_without_tag_wear_cycle(db_session: AsyncSession, test_user: User):
    """Verifies wear session with a device that does not support tag seals."""
    from app.models.life import InventoryItem

    device = InventoryItem(
        user_id=test_user.id,
        category="wearable",
        group_type="equipment",
        name="Keyless Lock Belt",
        inventory_status="available",
        extra_properties={"supports_tag": False},
    )
    db_session.add(device)
    await db_session.commit()

    # Start session with device_id and tag_number=None
    session, log = await wear_svc.start_open_ended_session(
        db_session,
        test_user.id,
        tag_number=None,
        device_id=device.id,
    )
    assert session.device_id == device.id

    status = await wear_svc.get_wear_status(db_session, test_user.id)
    assert status["device"].name == "Keyless Lock Belt"
    assert status["supports_tag"] is False

    await wear_svc.finish_open_ended_session(db_session, test_user.id)


