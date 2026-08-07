"""Tests for training feature: model, API, gamification integration."""

from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.gamification.handler import get_or_create_progress, on_task_completed
from app.models.activity_log import ActivityLog
from app.models.training import TrainingDay

# --- Model tests ---


@pytest.mark.asyncio
async def test_create_training_day(db_session: AsyncSession, test_user):
    """TrainingDay model can be created and persisted."""
    today = datetime.now(UTC).date()
    td = TrainingDay(
        user_id=test_user.id,
        target_date=today,
        status="planned",
    )
    db_session.add(td)
    await db_session.flush()

    assert td.id is not None
    assert td.status == "planned"
    assert td.target_date == today


@pytest.mark.asyncio
async def test_training_day_lifecycle(db_session: AsyncSession, test_user):
    """TrainingDay goes through planned → active → completed → analyzed."""
    td = TrainingDay(
        user_id=test_user.id,
        target_date=date.today(),
        status="planned",
    )
    db_session.add(td)
    await db_session.flush()

    td.status = "active"
    db_session.add(td)
    await db_session.flush()
    assert td.status == "active"

    td.status = "completed"
    db_session.add(td)
    await db_session.flush()
    assert td.status == "completed"

    td.status = "analyzed"
    td.analyzed_at = datetime.now(UTC)
    db_session.add(td)
    await db_session.flush()
    assert td.status == "analyzed"
    assert td.analyzed_at is not None


@pytest.mark.asyncio
async def test_activity_log_with_training(db_session: AsyncSession, test_user):
    """ActivityLog can link to TrainingDay and have subtasks."""
    today = date.today()
    td = TrainingDay(
        user_id=test_user.id,
        target_date=today,
        status="active",
    )
    db_session.add(td)
    await db_session.flush()

    subtasks = [
        {"id": 1, "desc": "Prepare", "is_done": True},
        {"id": 2, "desc": "Execute", "is_done": False},
        {"id": 3, "desc": "Clean up", "is_done": False},
    ]

    log = ActivityLog(
        user_id=test_user.id,
        status="pending",
        selected_entity_name="Test Task",
        training_day_id=td.id,
        subtasks=subtasks,
    )
    db_session.add(log)
    await db_session.flush()

    assert log.training_day_id == td.id
    assert len(log.subtasks) == 3
    assert log.subtasks[0]["is_done"]


# --- Subtask toggle ---


@pytest.mark.asyncio
async def test_toggle_subtask_toggles(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Toggling a subtask flips is_done."""
    today = date.today()
    td = TrainingDay(
        user_id=test_user.id,
        target_date=today,
        status="active",
    )
    db_session.add(td)
    await db_session.flush()

    log = ActivityLog(
        user_id=test_user.id,
        status="pending",
        selected_entity_name="Toggle Test",
        training_day_id=td.id,
        subtasks=[{"id": 1, "desc": "Step 1", "is_done": False}],
    )
    db_session.add(log)
    await db_session.flush()

    response = await auth_client.post(
        f"/training/tasks/{log.id}/subtasks/0/toggle",
        follow_redirects=False,
    )
    assert response.status_code == 303

    await db_session.refresh(log)
    assert log.subtasks[0]["is_done"]


# --- Gamification: training mode ---


@pytest.mark.asyncio
async def test_training_completion_skips_streak(db_session: AsyncSession, test_user):
    """Training task completion awards XP but skips streak/achievements."""
    from app.models.entity import Entity

    progress = await get_or_create_progress(db_session, test_user.id)
    assert progress.current_streak == 0

    entity = Entity(
        type="one_time",
        real_name="Training Entity",
        category="Test",
        owner_id=test_user.id,
    )
    db_session.add(entity)
    await db_session.flush()

    today = date.today()
    td = TrainingDay(
        user_id=test_user.id,
        target_date=today,
        status="active",
    )
    db_session.add(td)
    await db_session.flush()

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=entity.id,
        status="pending",
        selected_entity_name="Training Entity",
        selected_params={"intensity": 1},
        training_day_id=td.id,
    )
    db_session.add(log)
    await db_session.flush()

    result = await on_task_completed(db_session, test_user.id, log)
    assert result["xp_earned"] > 0  # XP still awarded
    assert result["streak"] == 0  # Streak NOT incremented
    assert result["combo"] == 0  # Combo NOT incremented
    assert result["new_achievements"] == 0  # No achievements
