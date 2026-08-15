"""Gamification handler: process task completion/interruption, update progress."""

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gamification.achievements import check_and_award_achievements
from app.gamification.points_v2 import (
    award_points,
    calculate_entity_penalty,
    calculate_entity_points,
)
from app.gamification.xp import (
    calculate_penalty_xp,
    calculate_task_xp,
    level_from_xp,
    should_reset_streak,
)
from app.models.activity_log import ActivityLog
from app.models.notification import Notification
from app.models.points import PenaltyRedemption
from app.models.progress import UserProgress
from app.models.user import User
from app.prefs import UserPrefs, neutral_notification, prefs_from_dict
from app.timeutils import local_date, local_today

logger = logging.getLogger(__name__)


async def get_or_create_progress(db: AsyncSession, user_id: uuid.UUID) -> UserProgress:
    """Get or create UserProgress for a user."""
    result = await db.execute(select(UserProgress).where(UserProgress.user_id == user_id))
    progress = result.scalar_one_or_none()
    if progress is None:
        progress = UserProgress(user_id=user_id)
        db.add(progress)
        await db.flush()
    return progress


async def _user_prefs(db: AsyncSession, user_id: uuid.UUID) -> tuple:
    """Load (UserPrefs, locale) for notification masking (DESIGN_V2 §12)."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        return UserPrefs(), "en"
    return prefs_from_dict(user.prefs), user.locale or "en"


async def on_task_completed(
    db: AsyncSession,
    user_id: uuid.UUID,
    log: ActivityLog,
) -> dict:
    """Process task completion: award XP, update streaks, check achievements."""
    progress = await get_or_create_progress(db, user_id)
    prefs, locale = await _user_prefs(db, user_id)

    # Extract intensity from ACTUAL params first (what was really done),
    # falling back to planned params (ADR-041 planned/actual split).
    intensity = 1
    if log.actual_parameters and isinstance(log.actual_parameters, dict):
        intensity = log.actual_parameters.get("intensity", 1)
    elif log.selected_params and isinstance(log.selected_params, dict):
        intensity = log.selected_params.get("intensity", 1)

    # Training mode: skip streaks and combo
    is_training = log.training_day_id is not None

    # Streak handling — only increment once per calendar day
    today = local_today()
    if not is_training:
        if should_reset_streak(progress.last_activity_date):
            progress.current_streak = 0

        last_date = local_date(progress.last_activity_date)
        if last_date != today:
            progress.current_streak += 1
            if progress.current_streak > progress.longest_streak:
                progress.longest_streak = progress.current_streak

        progress.last_activity_date = datetime.now(UTC)
        progress.combo_count += 1

    # Determine entity type
    entity_type = "one_time"
    gamification_config = None
    if log.entity:
        entity_type = log.entity.type
        gamification_config = log.entity.gamification_config

    # Calculate XP (always)
    earned_xp = calculate_task_xp(
        entity_type=entity_type,
        intensity=intensity,
        streak_days=progress.current_streak,
        combo_count=progress.combo_count,
    )
    progress.xp += earned_xp
    old_level = progress.level
    progress.level = level_from_xp(progress.xp)
    progress.total_completed += 1

    # Points v2: if entity has gamification_config, calculate flexible points.
    # Bonus conditions evaluate against actual params when present (ADR-041).
    points_earned = 0
    bonus_descriptions: list[str] = []
    if gamification_config:
        eval_params = log.actual_parameters or log.selected_params
        points_earned, bonus_descriptions, _ = await calculate_entity_points(gamification_config, eval_params)
        progress.points_balance += points_earned
        log.points_awarded = points_earned
        await award_points(
            db,
            user_id,
            points_earned,
            "earn",
            reason=f"Completed: {log.selected_entity_name or 'task'}",
            entity_id=log.entity_id,
            activity_log_id=log.id,
            meta={"bonuses": bonus_descriptions},
        )

    # Add XP to the log
    log.selected_params = {
        **(log.selected_params or {}),
        "_xp_earned": earned_xp,
        "_points_earned": points_earned,
    }

    db.add(progress)
    db.add(log)

    # Check achievements (skip for training tasks)
    new_achievements = [] if is_training else await check_and_award_achievements(db, user_id, progress, log)

    # Create notifications
    notifications = []

    # Level up notification
    if progress.level > old_level:
        title, body = neutral_notification(
            prefs, "Level Up! 🎉", f"You reached level {progress.level}!", locale
        )
        n = Notification(
            user_id=user_id,
            type="level_up",
            title=title,
            body=body,
            link="/dashboard",
        )
        db.add(n)
        notifications.append(n)

    # Achievement notifications
    for ua in new_achievements:
        title, body = neutral_notification(
            prefs,
            f"Achievement: {ua.achievement.name} 🏆",
            ua.achievement.description,
            locale,
        )
        n = Notification(
            user_id=user_id,
            type="achievement",
            title=title,
            body=body,
            link="/achievements",
        )
        db.add(n)
        notifications.append(n)

    # Streak milestone
    if progress.current_streak in (3, 7, 14, 30, 100):
        title, body = neutral_notification(
            prefs,
            f"🔥 {progress.current_streak}-day streak!",
            f"You've been active for {progress.current_streak} days in a row.",
            locale,
        )
        n = Notification(
            user_id=user_id,
            type="streak",
            title=title,
            body=body,
            link="/dashboard",
        )
        db.add(n)
        notifications.append(n)

    # Threshold check
    if gamification_config and isinstance(gamification_config, dict):
        thresholds = gamification_config.get("thresholds", {})
        if thresholds:
            neg = thresholds.get("negative", -100)
            warn = thresholds.get("warning", 0)
            good = thresholds.get("good", 100)
            new_balance = progress.points_balance
            if new_balance < neg:
                title, body = neutral_notification(
                    prefs,
                    "🔴 Critical points!",
                    f"Balance ({new_balance}) below negative threshold ({neg}). Restrictions active.",
                    locale,
                )
                n = Notification(
                    user_id=user_id,
                    type="threshold",
                    title=title,
                    body=body,
                    link="/api/v2/points/page",
                )
                db.add(n)
                notifications.append(n)
            elif new_balance < warn:
                title, body = neutral_notification(
                    prefs,
                    "⚠️ Low points",
                    f"Balance ({new_balance}) below warning threshold ({warn}).",
                    locale,
                )
                n = Notification(
                    user_id=user_id,
                    type="threshold",
                    title=title,
                    body=body,
                    link="/api/v2/points/page",
                )
                db.add(n)
                notifications.append(n)
            elif new_balance >= good:
                title, body = neutral_notification(
                    prefs,
                    "🎉 Points milestone!",
                    f"Balance ({new_balance}) reached good threshold ({good})!",
                    locale,
                )
                n = Notification(
                    user_id=user_id,
                    type="threshold",
                    title=title,
                    body=body,
                    link="/api/v2/points/page",
                )
                db.add(n)
                notifications.append(n)

    await db.flush()

    # Send Telegram notifications if user has linked account
    await _send_tg_notifications(db, user_id, notifications)

    return {
        "xp_earned": earned_xp,
        "points_earned": points_earned,
        "points_balance": progress.points_balance,
        "total_xp": progress.xp,
        "level": progress.level,
        "leveled_up": progress.level > old_level,
        "streak": progress.current_streak,
        "combo": progress.combo_count,
        "new_achievements": len(new_achievements),
        "notifications": len(notifications),
        "bonus_descriptions": bonus_descriptions,
    }


async def _send_tg_notifications(db: AsyncSession, user_id: uuid.UUID, notifications: list):
    """Try to send Telegram messages for new notifications."""
    if not notifications:
        return
    try:
        from app.models.user import User
        from app.telegram.bot import send_telegram_notification

        result = await db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if user and user.telegram_chat_id:
            for n in notifications[:3]:  # Limit to 3 messages
                await send_telegram_notification(user.telegram_chat_id, f"*{n.title}*\n{n.body or ''}")
    except Exception:
        logger.debug("TG notification send failed", exc_info=True)


async def on_task_interrupted(
    db: AsyncSession,
    user_id: uuid.UUID,
    log: ActivityLog,
) -> dict:
    """Process task interruption: apply XP penalty, reset combo, escalate."""
    progress = await get_or_create_progress(db, user_id)
    prefs, locale = await _user_prefs(db, user_id)

    # Escalation: count consecutive interruptions
    escalation = await _get_escalation(db, user_id)

    # Calculate penalty
    base_penalty = 25  # base XP loss
    penalty_xp = calculate_penalty_xp(base_penalty, escalation)

    # Points v2 penalty if entity has gamification_config
    points_penalty = 0
    redemption_action = None
    if log.entity and log.entity.gamification_config:
        config = log.entity.gamification_config
        points_penalty = await calculate_entity_penalty(config, "missed", escalation)
        if points_penalty > 0:
            progress.points_balance = max(-1000, progress.points_balance - points_penalty)
            await award_points(
                db,
                user_id,
                -points_penalty,
                "penalty",
                reason=f"Interrupted: {log.selected_entity_name or 'task'}",
                entity_id=log.entity_id,
                activity_log_id=log.id,
            )
        redemption_action = _get_redemption_action_from_config(config)  # sync helper — no await
        # Create PenaltyRedemption record
        if redemption_action:
            redemption = PenaltyRedemption(
                user_id=user_id,
                entity_id=log.entity_id,
                activity_log_id=log.id,
                redemption_type=redemption_action.get("type", "clothespins"),
                duration_min=redemption_action.get("duration_min", 0),
                count=redemption_action.get("count", 0),
                description=redemption_action.get("description", ""),
                escalation_level=escalation,
                points_value=points_penalty,
            )
            db.add(redemption)

    progress.xp = max(0, progress.xp - penalty_xp)
    progress.total_interrupted += 1
    progress.combo_count = 0  # Reset combo

    # Update log
    log.penalty_applied = True
    log.penalty_details = {
        "xp_penalty": penalty_xp,
        "points_penalty": points_penalty,
        "escalation_level": escalation,
        "redemption": redemption_action,
    }

    db.add(progress)
    db.add(log)

    # Penalty notification
    title, body = neutral_notification(
        prefs,
        "Task Interrupted ⚠️",
        f"-{penalty_xp} XP (escalation ×{escalation}). Combo reset.",
        locale,
    )
    n = Notification(
        user_id=user_id,
        type="penalty",
        title=title,
        body=body,
        link="/tasks/",
    )
    db.add(n)

    await db.flush()

    # Send Telegram notification
    await _send_tg_notifications(db, user_id, [n])

    return {
        "xp_penalty": penalty_xp,
        "total_xp": progress.xp,
        "escalation": escalation,
        "combo_reset": True,
    }


def _get_redemption_action_from_config(config: dict | None) -> dict | None:
    """Synchronous helper to extract redemption action."""
    if not config:
        return None
    penalties_cfg = config.get("penalties", {})
    if not penalties_cfg.get("enabled", True):
        return None
    for level_cfg in penalties_cfg.get("levels", []):
        if level_cfg.get("condition") == "missed" and level_cfg.get("redemption"):
            return level_cfg["redemption"]
    return None


async def _get_escalation(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Count consecutive interruptions for escalation multiplier."""
    result = await db.execute(
        select(ActivityLog.status)
        .where(ActivityLog.user_id == user_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(10)
    )
    statuses = [row[0] for row in result.all()]
    consecutive = 0
    for s in statuses:
        if s == "stopped":
            consecutive += 1
        else:
            break
    return max(1, consecutive)
