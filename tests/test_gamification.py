"""Tests for gamification: handler, achievements, progress."""

import pytest
from httpx import AsyncClient
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
from app.models.opt_in import UserEntityOptIn
from app.models.points import PenaltyRedemption
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


# --- Audit fixes: interrupt 500 + state integrity ---


@pytest.mark.asyncio
async def test_interrupt_with_redemption_config_creates_redemption(db_session: AsyncSession, test_user):
    """Audit: interrupt with a redemption-config entity must not crash (await-on-sync bug)
    and must create a PenaltyRedemption record."""
    progress = UserProgress(user_id=test_user.id, xp=100, level=2)
    db_session.add(progress)
    await db_session.flush()

    entity = Entity(
        type="one_time",
        real_name="Redemption Task",
        category="Test",
        owner_id=test_user.id,
        gamification_config={
            "points": {"base": 50},
            "penalties": {
                "enabled": True,
                "levels": [
                    {
                        "level": 1,
                        "condition": "missed",
                        "deduction": 10,
                        "redemption": {"type": "clothespins", "duration_min": 10},
                    }
                ],
            },
            "bonuses": [],
            "thresholds": {"negative": -100, "warning": 0, "good": 100},
        },
    )
    db_session.add(entity)
    await db_session.flush()

    log = ActivityLog(
        user_id=test_user.id,
        entity_id=entity.id,
        status="pending",
        selected_entity_name="Redemption Task",
    )
    db_session.add(log)
    await db_session.flush()

    result = await on_task_interrupted(db_session, test_user.id, log)
    assert result["xp_penalty"] > 0

    redemptions = (
        (await db_session.execute(select(PenaltyRedemption).where(PenaltyRedemption.activity_log_id == log.id)))
        .scalars()
        .all()
    )
    assert len(redemptions) == 1
    assert redemptions[0].redemption_type == "clothespins"
    assert redemptions[0].points_value > 0


@pytest.mark.asyncio
async def test_cannot_complete_after_interrupt(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Audit: an interrupted task cannot be completed afterwards for a reward."""
    entity = Entity(type="one_time", real_name="T", category="test", owner_id=test_user.id)
    db_session.add(entity)
    await db_session.flush()
    opt_in = UserEntityOptIn(user_id=test_user.id, entity_id=entity.id, is_opted_in=True)
    db_session.add(opt_in)
    await db_session.flush()

    log = ActivityLog(user_id=test_user.id, entity_id=entity.id, status="pending", selected_entity_name="T")
    db_session.add(log)
    await db_session.flush()

    r1 = await auth_client.post(f"/tasks/{log.id}/interrupt", follow_redirects=False)
    assert r1.status_code == 303

    r2 = await auth_client.post(f"/tasks/{log.id}/complete", follow_redirects=False)
    assert r2.status_code == 303

    await db_session.refresh(log)
    assert log.status == "interrupted"  # unchanged — no reward granted
    progress = await get_or_create_progress(db_session, test_user.id)
    await db_session.refresh(progress)
    assert progress.total_completed == 0
    assert progress.total_interrupted == 1
    await db_session.refresh(opt_in)
    assert opt_in.next_due_at is None  # schedule NOT advanced by the rejected completion


@pytest.mark.asyncio
async def test_repeated_complete_does_not_reschedule(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Audit: a repeated Complete must not keep changing next_due_at."""
    entity = Entity(type="one_time", real_name="T", category="test", owner_id=test_user.id)
    db_session.add(entity)
    await db_session.flush()
    opt_in = UserEntityOptIn(user_id=test_user.id, entity_id=entity.id, is_opted_in=True)
    db_session.add(opt_in)
    await db_session.flush()

    log = ActivityLog(user_id=test_user.id, entity_id=entity.id, status="pending", selected_entity_name="T")
    db_session.add(log)
    await db_session.flush()

    r1 = await auth_client.post(f"/tasks/{log.id}/complete", follow_redirects=False)
    assert r1.status_code == 303
    await db_session.refresh(opt_in)
    first_due = opt_in.next_due_at
    assert first_due is not None

    r2 = await auth_client.post(f"/tasks/{log.id}/complete", follow_redirects=False)
    assert r2.status_code == 303
    await db_session.refresh(opt_in)
    assert opt_in.next_due_at == first_due  # unchanged on repeat


@pytest.mark.asyncio
async def test_repeated_interrupt_does_not_reblock(auth_client: AsyncClient, db_session: AsyncSession, test_user):
    """Audit: a repeated Interrupt must not keep moving retry_not_before_at."""
    entity = Entity(type="one_time", real_name="T", category="test", owner_id=test_user.id)
    db_session.add(entity)
    await db_session.flush()
    opt_in = UserEntityOptIn(user_id=test_user.id, entity_id=entity.id, is_opted_in=True)
    db_session.add(opt_in)
    await db_session.flush()

    log = ActivityLog(user_id=test_user.id, entity_id=entity.id, status="pending", selected_entity_name="T")
    db_session.add(log)
    await db_session.flush()

    r1 = await auth_client.post(f"/tasks/{log.id}/interrupt", follow_redirects=False)
    assert r1.status_code == 303
    await db_session.refresh(opt_in)
    first_block = opt_in.retry_not_before_at
    assert first_block is not None

    r2 = await auth_client.post(f"/tasks/{log.id}/interrupt", follow_redirects=False)
    assert r2.status_code == 303
    await db_session.refresh(opt_in)
    assert opt_in.retry_not_before_at == first_block  # unchanged on repeat
