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
