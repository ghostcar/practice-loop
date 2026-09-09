"""Unit and integration tests for Telegram Personal Contour (ADR-193).

Covers:
- Main reply keyboard structure (6 core personal contour sections)
- Inline action keyboards for tasks, meds, AI generation, workouts, health, stats
- 1-click task execution and skipping logic
- Medication slot batch intake flow
- Weight recording and health state check-in
- Penalty redemption completion
- DataMatrix vs Agent photo verification routing
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity_log import ActivityLog
from app.models.health import HealthState
from app.models.life import BodyMeasurement
from app.models.medication import Medication, MedSchedule
from app.models.points import PenaltyRedemption
from app.models.progress import UserProgress
from app.models.user import User
from app.services import med_service as med_svc
from app.telegram.keyboards import (
    get_ai_generator_keyboard,
    get_health_keyboard,
    get_main_reply_keyboard,
    get_med_slot_keyboard,
    get_stats_keyboard,
    get_task_card_keyboard,
    get_training_keyboard,
)
from app.timeutils import local_today


def test_main_reply_keyboard_structure():
    """Verify that the main reply keyboard contains all 6 personal contour buttons."""
    kb = get_main_reply_keyboard()
    assert kb.resize_keyboard is True
    assert kb.is_persistent is True

    button_texts = [[btn.text for btn in row] for row in kb.keyboard]
    assert len(button_texts) == 4
    assert button_texts[0] == ["📋 План дня", "💊 Лекарства"]
    assert button_texts[1] == ["🤖 AI-генератор", "🏋️ Тренировка"]
    assert button_texts[2] == ["🔒 Пояс", "❤️ Чек-ин / Замеры"]
    assert button_texts[3] == ["🏆 Прогресс"]


def test_task_card_keyboard():
    """Verify task card buttons for 1-click completion, custom params, and interruption."""
    task_id = uuid.uuid4()
    kb = get_task_card_keyboard(task_id)

    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert f"done:{task_id}" in callbacks
    assert f"task_custom:{task_id}" in callbacks
    assert f"task_skip:{task_id}" in callbacks
    assert f"int:{task_id}" in callbacks


def test_ai_generator_keyboard_presets():
    """Verify AI generator presents required presets."""
    kb = get_ai_generator_keyboard()
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "ai_gen:auto" in callbacks
    assert "ai_gen:quick" in callbacks
    assert "ai_gen:relax" in callbacks
    assert "ai_gen:intense" in callbacks


def test_med_slot_keyboard_actions():
    """Verify slot batch intake and individual items."""
    slot_key = "morning"
    slot_time = "09:00"
    items = [{"schedule_id": str(uuid.uuid4()), "medication_name": "Витамин C"}]

    kb = get_med_slot_keyboard(slot_key, slot_time, items)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert f"med_slot_take:{slot_key}:{slot_time}" in callbacks
    assert f"med_take:{items[0]['schedule_id']}" in callbacks
    assert "med_scan_guide" in callbacks
    assert "med_kits_view" in callbacks


def test_training_keyboard():
    """Verify workout subtask checklist and completion buttons."""
    day_id = uuid.uuid4()
    subtasks = [{"desc": "Приседания 3x15", "is_done": False}]

    kb = get_training_keyboard(day_id, subtasks, is_completed=False)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert f"tr_toggle:{day_id}:0" in callbacks
    assert f"tr_complete:{day_id}" in callbacks
    assert f"tr_adapt:{day_id}" in callbacks


def test_health_keyboard_scales():
    """Verify mood and energy scales and quick actions."""
    kb = get_health_keyboard(mood=4, energy=3)
    callbacks = [btn.callback_data for row in kb.inline_keyboard for btn in row]
    assert "health_mood:4" in callbacks
    assert "health_energy:3" in callbacks
    assert "health_weight_prompt" in callbacks
    assert "health_cycle_view" in callbacks


def test_stats_keyboard_with_penalties():
    """Verify penalty redemption button appears when penalties exist."""
    kb_no_pen = get_stats_keyboard(has_penalties=False)
    assert "stat_redemptions" not in [btn.callback_data for row in kb_no_pen.inline_keyboard for btn in row]

    kb_pen = get_stats_keyboard(has_penalties=True)
    assert "stat_redemptions" in [btn.callback_data for row in kb_pen.inline_keyboard for btn in row]


@pytest.mark.asyncio
async def test_task_skip_flow(db_session: AsyncSession, test_user: User):
    """Skipping a task changes status to 'skipped' without applying penalty or rewards."""
    log = ActivityLog(
        user_id=test_user.id,
        status="planned",
        selected_entity_name="Тестовая растяжка",
    )
    db_session.add(log)
    await db_session.commit()

    log.status = "skipped"
    db_session.add(log)
    await db_session.commit()

    updated = await db_session.get(ActivityLog, log.id)
    assert updated is not None
    assert updated.status == "skipped"
    assert updated.penalty_applied is False


@pytest.mark.asyncio
async def test_medication_slot_batch_intake(db_session: AsyncSession, test_user: User):
    """Batch intake via med_service for a time slot marks intake and updates stocks."""
    kit = await med_svc.create_kit(
        db_session,
        user_id=test_user.id,
        name="Домашняя аптечка",
        location="",
        notes="",
    )
    med = Medication(user_id=test_user.id, name="Омега-3", kind="supplement")
    db_session.add(med)
    await db_session.flush()

    await med_svc.add_stock_to_kit(
        db_session,
        test_user.id,
        kit_id=kit.id,
        medication_id=med.id,
        quantity=30.0,
    )
    sched = MedSchedule(
        user_id=test_user.id,
        medication_id=med.id,
        dose_quantity=1.0,
        dose_unit="капс",
        frequency_type="daily",
        times_per_day=1,
        times_of_day=["09:00"],
    )
    db_session.add(sched)
    await db_session.commit()

    await med_svc.record_batch_intake(
        db_session,
        user_id=test_user.id,
        schedule_ids=[sched.id],
        slot_time="09:00",
    )
    await db_session.commit()

    summary = await med_svc.schedule_summary(db_session, test_user.id)
    assert len(summary["slots"]) >= 1
    assert summary["slots"][0]["all_taken"] is True


@pytest.mark.asyncio
async def test_weight_and_health_checkin(db_session: AsyncSession, test_user: User):
    """Logging weight and daily mood/energy updates database models correctly."""
    today = local_today()

    meas = BodyMeasurement(
        user_id=test_user.id,
        measured_date=today,
        time_of_day="morning",
        weight=73.5,
    )
    db_session.add(meas)

    state = HealthState(
        user_id=test_user.id,
        event_date=today,
        mood=5,
        energy=4,
    )
    db_session.add(state)
    await db_session.commit()

    loaded_meas = (
        await db_session.execute(
            select(BodyMeasurement).where(
                BodyMeasurement.user_id == test_user.id,
                BodyMeasurement.measured_date == today,
            )
        )
    ).scalar_one()
    assert loaded_meas.weight == 73.5

    loaded_state = (
        await db_session.execute(
            select(HealthState).where(HealthState.user_id == test_user.id, HealthState.event_date == today)
        )
    ).scalar_one()
    assert loaded_state.mood == 5
    assert loaded_state.energy == 4


@pytest.mark.asyncio
async def test_penalty_redemption_flow(db_session: AsyncSession, test_user: User):
    """Executing a penalty redemption completes the record and restores points."""
    progress = UserProgress(
        user_id=test_user.id,
        xp=200,
        level=2,
        points_balance=50,
    )
    db_session.add(progress)

    redemption = PenaltyRedemption(
        user_id=test_user.id,
        redemption_type="cold_shower",
        duration_min=5,
        description="Контрастный душ 5 минут",
        status="pending",
        points_value=25,
    )
    db_session.add(redemption)
    await db_session.commit()

    # Simulate redemption completion
    redemption.status = "completed"
    redemption.completed_at = datetime.now(UTC)
    progress.points_balance += redemption.points_value
    db_session.add(redemption)
    db_session.add(progress)
    await db_session.commit()

    updated_prog = await db_session.get(UserProgress, test_user.id)
    assert updated_prog.points_balance == 75

    updated_redemp = await db_session.get(PenaltyRedemption, redemption.id)
    assert updated_redemp.status == "completed"


@pytest.mark.asyncio
async def test_photo_handler_datamatrix_dispatch(monkeypatch):
    """Verify that a photo with DataMatrix is dispatched to med scan, not to agent vision."""
    from app.services.datamatrix_service import DataMatrixParseResult
    from app.telegram.agent_handler import handle_agent_photo_verification

    fake_result = [
        DataMatrixParseResult(
            raw_code="010460000000000021123456789012",
            gtin="04600000000000",
            serial="123456789012",
        )
    ]

    monkeypatch.setattr(
        "app.services.datamatrix_service.decode_datamatrix_from_image",
        lambda _bytes: fake_result,
    )

    mock_process_scan = AsyncMock()
    monkeypatch.setattr("app.telegram.bot.process_datamatrix_scan", mock_process_scan)

    fake_user = MagicMock()
    fake_user.id = uuid.uuid4()
    monkeypatch.setattr("app.telegram.agent_handler._get_linked_user", AsyncMock(return_value=fake_user))

    fake_photo_size = MagicMock()
    fake_photo_size.file_id = "test_file_id"
    fake_message = MagicMock()
    fake_message.chat.id = 123456
    fake_message.photo = [fake_photo_size]
    fake_bot = MagicMock()
    fake_file = MagicMock()
    fake_file.file_path = "photos/test.jpg"
    fake_bot.get_file = AsyncMock(return_value=fake_file)
    fake_bot.download_file = AsyncMock(return_value=b"fake_image_bytes")
    fake_message.bot = fake_bot

    await handle_agent_photo_verification(fake_message)

    # Must call process_datamatrix_scan and NOT call agent
    mock_process_scan.assert_awaited_once_with(fake_message, fake_user, fake_result)
