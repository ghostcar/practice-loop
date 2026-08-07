"""Tests for gamification: handler, achievements, progress."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gamification.achievements import seed_achievements
from app.gamification.handler import (
    get_or_create_progress,
    on_task_completed,
    on_task_interrupted,
)
from app.models.achievement import Achievement
from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.notification import Notification
from app.models.progress import UserProgress


@pytest.mark.asyncio
async def test_get_or_create_progress_new(db_session: AsyncSession, test_user):
    """Creates progress for a new user."""
    progress = await get_or_create_progress(db_session, test_user.id)
    assert progress is not None
    assert progress.xp == 0
    assert progress.level == 1
    assert progress.current_streak == 0


@pytest.mark.asyncio
async def test_get_or_create_progress_existing(db_session: AsyncSession, test_user):
    """Returns existing progress."""
    p1 = await get_or_create_progress(db_session, test_user.id)
    p2 = await get_or_create_progress(db_session, test_user.id)
    assert p1.user_id == p2.user_id
    assert p1.xp == p2.xp


@pytest.mark.asyncio
async def test_on_task_completed_earns_xp(db_session: AsyncSession, test_user):
    """Completing a task awards XP and increments counters."""
    entity = Entity(
        type="one_time",
        real_name="Test Task",
        category="Test",
        owner_id=test_user.id,
    )
    db_session.add(entity)
    await db_session.flush()

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=entity.id,
        status="pending",
        selected_entity_name="Test Task",
        selected_params={"intensity": 2},
    )
    db_session.add(log)
    await db_session.flush()

    result = await on_task_completed(db_session, test_user.id, log)
    assert result["xp_earned"] > 0
    assert result["total_xp"] > 0
    assert result["level"] == 1
    assert result["streak"] == 1
    assert result["combo"] == 1

    progress = await get_or_create_progress(db_session, test_user.id)
    assert progress.total_completed == 1
    assert progress.current_streak == 1
    assert progress.combo_count == 1


@pytest.mark.asyncio
async def test_on_task_completed_streak_once_per_day(db_session: AsyncSession, test_user):
    """Streak only increments once per calendar day."""
    entity = Entity(
        type="one_time",
        real_name="Streak Test",
        category="Test",
        owner_id=test_user.id,
    )
    db_session.add(entity)
    await db_session.flush()

    log1 = ActivityLog(
        user_id=test_user.id,
        entity_id=entity.id,
        status="pending",
        selected_entity_name="Streak Test",
        selected_params={"intensity": 1},
    )
    db_session.add(log1)
    await db_session.flush()

    result1 = await on_task_completed(db_session, test_user.id, log1)
    assert result1["streak"] == 1

    log2 = ActivityLog(
        user_id=test_user.id,
        entity_id=entity.id,
        status="pending",
        selected_entity_name="Streak Test",
        selected_params={"intensity": 1},
    )
    db_session.add(log2)
    await db_session.flush()

    result2 = await on_task_completed(db_session, test_user.id, log2)
    assert result2["streak"] == 1  # Still 1 (same day)


@pytest.mark.asyncio
async def test_on_task_completed_level_up(db_session: AsyncSession, test_user):
    """Large XP gains trigger level-up and notification."""
    progress = UserProgress(user_id=test_user.id, xp=95, level=1)
    db_session.add(progress)
    await db_session.flush()

    entity = Entity(
        type="series",
        real_name="Big Task",
        category="Test",
        owner_id=test_user.id,
    )
    db_session.add(entity)
    await db_session.flush()

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=entity.id,
        status="pending",
        selected_entity_name="Big Task",
        selected_params={"intensity": 1},
    )
    db_session.add(log)
    await db_session.flush()

    result = await on_task_completed(db_session, test_user.id, log)
    assert result["level"] >= 2
    assert result["leveled_up"]

    notif_result = await db_session.execute(
        select(Notification).where(
            Notification.user_id == test_user.id,
            Notification.type == "level_up",
        )
    )
    assert notif_result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_on_task_interrupted_applies_penalty(db_session: AsyncSession, test_user):
    """Interruption applies XP penalty and creates notification."""
    progress = UserProgress(user_id=test_user.id, xp=100, level=2)
    db_session.add(progress)
    await db_session.flush()

    log = ActivityLog(
        user_id=test_user.id,
        status="pending",
        selected_entity_name="Task",
    )
    db_session.add(log)
    await db_session.flush()

    result = await on_task_interrupted(db_session, test_user.id, log)
    assert result["xp_penalty"] > 0
    assert result["total_xp"] < 100
    assert result["combo_reset"]

    await db_session.refresh(progress)
    assert progress.combo_count == 0
    assert progress.total_interrupted == 1
    assert log.penalty_applied
    assert log.penalty_details is not None


@pytest.mark.asyncio
async def test_seed_achievements(db_session: AsyncSession):
    """Seeding creates the default 13 achievements."""
    achievements = await seed_achievements(db_session)
    assert len(achievements) == 13

    achievements2 = await seed_achievements(db_session)
    assert len(achievements2) == 0

    result = await db_session.execute(select(Achievement))
    all_achs = result.scalars().all()
    assert len(all_achs) == 13
