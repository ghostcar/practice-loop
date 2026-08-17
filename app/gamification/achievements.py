"""Achievement checking engine: evaluate conditions, award achievements."""

import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.achievement import Achievement, UserAchievement
from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.progress import UserProgress

logger = logging.getLogger(__name__)

# Seed achievement definitions
SEED_ACHIEVEMENTS = [
    # Streaks
    {
        "code": "streak_3",
        "name": "Getting Started",
        "description": "3-day streak",
        "condition_type": "streak",
        "condition_value": 3,
        "color": "amber",
    },
    {
        "code": "streak_7",
        "name": "Weekly Warrior",
        "description": "7-day streak",
        "condition_type": "streak",
        "condition_value": 7,
        "color": "orange",
    },
    {
        "code": "streak_30",
        "name": "Monthly Master",
        "description": "30-day streak",
        "condition_type": "streak",
        "condition_value": 30,
        "color": "red",
    },
    # Volume
    {
        "code": "total_10",
        "name": "First Steps",
        "description": "10 completed tasks",
        "condition_type": "count",
        "condition_value": 10,
        "color": "slate",
    },
    {
        "code": "total_50",
        "name": "Half-Century",
        "description": "50 completed tasks",
        "condition_type": "count",
        "condition_value": 50,
        "color": "indigo",
    },
    {
        "code": "total_100",
        "name": "Centurion",
        "description": "100 completed tasks",
        "condition_type": "count",
        "condition_value": 100,
        "color": "purple",
    },
    # Diversity
    {
        "code": "diverse_3",
        "name": "Explorer",
        "description": "Tasks from 3 different categories",
        "condition_type": "diversity",
        "condition_value": 3,
        "color": "emerald",
    },
    {
        "code": "diverse_5",
        "name": "Adventurer",
        "description": "Tasks from 5 different categories",
        "condition_type": "diversity",
        "condition_value": 5,
        "color": "teal",
    },
    # Joint
    {
        "code": "joint_1",
        "name": "Better Together",
        "description": "First joint session task",
        "condition_type": "joint",
        "condition_value": 1,
        "color": "pink",
    },
    {
        "code": "joint_10",
        "name": "Dynamic Duo",
        "description": "10 joint session tasks",
        "condition_type": "joint",
        "condition_value": 10,
        "color": "rose",
    },
    # Intensity
    {
        "code": "intensity_5",
        "name": "Full Throttle",
        "description": "Completed task with intensity 5",
        "condition_type": "intensity",
        "condition_value": 5,
        "color": "red",
    },
    # Level
    {
        "code": "level_5",
        "name": "Rising Star",
        "description": "Reached level 5",
        "condition_type": "level",
        "condition_value": 5,
        "color": "amber",
    },
    {
        "code": "level_10",
        "name": "Veteran",
        "description": "Reached level 10",
        "condition_type": "level",
        "condition_value": 10,
        "color": "violet",
    },
    # Medication adherence (ADR-085 — positive-only, softened PD-013)
    {
        "code": "med_first",
        "name": "First Dose",
        "description": "First on-time medication dose",
        "condition_type": "med_adherence",
        "condition_value": 0,
        "color": "emerald",
    },
    {
        "code": "med_adherence_3",
        "name": "Medication Routine",
        "description": "3-day medication adherence streak",
        "condition_type": "med_adherence",
        "condition_value": 3,
        "color": "teal",
    },
    {
        "code": "med_adherence_7",
        "name": "Consistent Care",
        "description": "7-day medication adherence streak",
        "condition_type": "med_adherence",
        "condition_value": 7,
        "color": "emerald",
    },
    {
        "code": "med_adherence_30",
        "name": "Health Guardian",
        "description": "30-day medication adherence streak",
        "condition_type": "med_adherence",
        "condition_value": 30,
        "color": "green",
    },
]


async def seed_achievements(db: AsyncSession) -> list[Achievement]:
    """Create default achievements if none exist."""
    result = await db.execute(select(Achievement).limit(1))
    if result.scalar_one_or_none() is not None:
        return []

    achievements = []
    for data in SEED_ACHIEVEMENTS:
        ach = Achievement(**data)
        db.add(ach)
        achievements.append(ach)

    await db.flush()
    return achievements


async def check_and_award_achievements(
    db: AsyncSession,
    user_id: uuid.UUID,
    progress: UserProgress,
    completed_log: ActivityLog | None = None,
) -> list[UserAchievement]:
    """Check all achievement conditions and award new ones. Returns newly awarded."""
    # Get all achievements not yet awarded
    subquery = select(UserAchievement.achievement_id).where(UserAchievement.user_id == user_id)
    result = await db.execute(select(Achievement).where(Achievement.id.not_in(subquery)))
    unawarded = result.scalars().all()

    newly_awarded: list[UserAchievement] = []

    for ach in unawarded:
        awarded = False
        context = None

        match ach.condition_type:
            case "streak":
                if progress.current_streak >= (ach.condition_value or 0):
                    awarded = True
                    context = f"{progress.current_streak}-day streak"

            case "count":
                if progress.total_completed >= (ach.condition_value or 0):
                    awarded = True
                    context = f"{progress.total_completed} tasks completed"

            case "diversity":
                count = await _count_categories(db, user_id)
                if count >= (ach.condition_value or 0):
                    awarded = True
                    context = f"{count} different categories"

            case "joint":
                count = await _count_joint_tasks(db, user_id)
                if count >= (ach.condition_value or 0):
                    awarded = True
                    context = f"{count} joint session tasks"

            case "intensity":
                if completed_log and completed_log.selected_params:
                    intensity = completed_log.selected_params.get("intensity", 0)
                    if intensity >= (ach.condition_value or 0):
                        awarded = True
                        context = f"Intensity {intensity} task"

            case "level":
                if progress.level >= (ach.condition_value or 0):
                    awarded = True
                    context = f"Reached level {progress.level}"

        if awarded:
            ua = UserAchievement(
                user_id=user_id,
                achievement_id=ach.id,
                context=context,
            )
            db.add(ua)
            newly_awarded.append(ua)

    if newly_awarded:
        await db.flush()

    return newly_awarded


async def _count_categories(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Count distinct categories the user has completed tasks in."""
    result = await db.execute(
        select(func.count(func.distinct(Entity.category)))
        .select_from(ActivityLog)
        .join(Entity, ActivityLog.entity_id == Entity.id)
        .where(
            ActivityLog.user_id == user_id,
            ActivityLog.status == "completed",
        )
    )
    return result.scalar() or 0


async def _count_joint_tasks(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Count tasks in sessions with multiple participants."""
    # Simplified: count tasks in non-null sessions (proxy for joint)
    result = await db.execute(
        select(func.count(ActivityLog.id)).where(
            ActivityLog.user_id == user_id,
            ActivityLog.status == "completed",
            ActivityLog.session_id.is_not(None),
        )
    )
    return result.scalar() or 0
