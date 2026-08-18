"""Medication adherence gamification (ADR-085 — softened PD-013).

Positive-only: an on-time intake may earn XP and achievements (capped per day).
A missed/skipped intake NEVER subtracts points and never penalizes — negative
gamification of health is prohibited. Medical signals remain relief-only.

Achievements (seeded via SEED_ACHIEVEMENTS + migration 042):
- ``med_first``        — first on-time intake
- ``med_adherence_3``  — 3-day adherence streak
- ``med_adherence_7``  — 7-day adherence streak
- ``med_adherence_30`` — 30-day adherence streak
"""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gamification.achievements import Achievement, UserAchievement
from app.gamification.handler import get_or_create_progress
from app.gamification.xp import level_from_xp
from app.models.medication import MedIntake, MedSchedule
from app.models.notification import Notification
from app.models.user import User
from app.prefs import neutral_notification, prefs_from_dict
from app.timeutils import local_date, local_today

logger = logging.getLogger(__name__)

# XP per on-time dose (small — adherence is a gentle nudge, not a reward farm).
ADHERENCE_XP_PER_DOSE = 5
# Daily XP cap from medication adherence (per user).
ADHERENCE_XP_DAILY_CAP = 20

# Achievement codes (must match SEED_ACHIEVEMENTS + migration 042).
ACH_FIRST = "med_first"
ACH_3 = "med_adherence_3"
ACH_7 = "med_adherence_7"
ACH_30 = "med_adherence_30"


async def _load_prefs(db: AsyncSession, user_id: uuid.UUID) -> tuple:
    """Load (UserPrefs, locale) for notification masking."""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        from app.prefs import UserPrefs

        return UserPrefs(), "en"
    return prefs_from_dict(user.prefs), user.locale or "en"


async def _expected_doses_today(schedule: MedSchedule, day) -> int:
    """Number of scheduled doses for a schedule on a given date (0 = not active that day)."""
    if not schedule.is_active:
        return 0
    if schedule.start_date and day < schedule.start_date:
        return 0
    if schedule.end_date and day > schedule.end_date:
        return 0
    if schedule.frequency_type == "weekly":
        wd = day.weekday()
        if schedule.days_of_week and wd not in schedule.days_of_week:
            return 0
        return schedule.times_per_day or 1
    if schedule.frequency_type == "interval":
        if not schedule.interval_hours:
            return 0
        return max(1, int(24 // schedule.interval_hours))
    # daily
    if schedule.times_per_day:
        return schedule.times_per_day
    if schedule.times_of_day:
        return len(schedule.times_of_day)
    return 1


async def adherence_streak(db: AsyncSession, user_id: uuid.UUID) -> int:
    """Consecutive days (ending today or yesterday) where all scheduled doses were taken.

    A day counts as adhered when at least one active schedule expected doses and
    the number of taken intakes that day >= expected doses. Days with no active
    schedule are ignored (do not break the streak).
    """
    schedules = (await db.execute(select(MedSchedule).where(MedSchedule.user_id == user_id))).scalars().all()
    intakes = (await db.execute(select(MedIntake).where(MedIntake.user_id == user_id))).scalars().all()

    # taken intakes per local day
    taken_by_day: dict = {}
    for it in intakes:
        if it.status != "taken":
            continue
        dt = it.taken_at or it.created_at
        if dt is None:
            continue
        day = local_date(dt)
        taken_by_day[day] = taken_by_day.get(day, 0) + 1

    today = local_today()
    # Pre-compute expected doses per day (async calls must be awaited before use).
    expected_by_day: dict = {}
    for offset in range(0, 366):
        day = today - timedelta(days=offset)
        total = 0
        for s in schedules:
            total += await _expected_doses_today(s, day)
        expected_by_day[day] = total

    # If today isn't fully adhered yet, start the streak from yesterday.
    streak = 0
    for offset in range(0, 366):
        day = today - timedelta(days=offset)
        expected = expected_by_day[day]
        if expected <= 0:
            if offset == 0:
                # no schedule today — start from yesterday
                continue
            # a day with no schedule doesn't break the streak
            streak += 1
            continue
        taken = taken_by_day.get(day, 0)
        if taken >= expected:
            streak += 1
        else:
            break
    return streak


async def _xp_earned_today(db: AsyncSession, user_id: uuid.UUID) -> int:
    """XP already earned from medication today (for the daily cap)."""
    today = local_today()
    intakes = (await db.execute(select(MedIntake).where(MedIntake.user_id == user_id))).scalars().all()
    count = 0
    for it in intakes:
        if it.status != "taken":
            continue
        dt = it.taken_at or it.created_at
        if dt is not None and local_date(dt) == today:
            count += 1
    return count * ADHERENCE_XP_PER_DOSE


async def _award_achievement(
    db: AsyncSession,
    user_id: uuid.UUID,
    code: str,
    context: str,
) -> UserAchievement | None:
    """Award an achievement by code if not already owned. Returns the new record when new."""
    result = await db.execute(select(Achievement).where(Achievement.code == code))
    ach = result.scalar_one_or_none()
    if ach is None:
        return None
    owned = (
        await db.execute(
            select(UserAchievement).where(
                UserAchievement.user_id == user_id,
                UserAchievement.achievement_id == ach.id,
            )
        )
    ).scalar_one_or_none()
    if owned is not None:
        return None
    ua = UserAchievement(user_id=user_id, achievement_id=ach.id, context=context)
    db.add(ua)
    await db.flush()
    return ua


async def on_medication_taken(
    db: AsyncSession,
    user_id: uuid.UUID,
    medication_name: str,
    on_time: bool = True,
) -> dict:
    """Award XP + achievements for an on-time intake (ADR-085, positive-only).

    Never raises and never subtracts points. Missed/skipped intakes are not
    handled here — they are logged by the caller without gamification.
    """
    result: dict = {"xp_earned": 0, "new_achievements": 0, "streak": 0}
    try:
        if not on_time:
            return result

        prefs, locale = await _load_prefs(db, user_id)
        progress = await get_or_create_progress(db, user_id)

        # XP with daily cap
        earned_today = await _xp_earned_today(db, user_id)
        if earned_today < ADHERENCE_XP_DAILY_CAP:
            xp = min(ADHERENCE_XP_PER_DOSE, ADHERENCE_XP_DAILY_CAP - earned_today)
            progress.xp += xp
            progress.level = level_from_xp(progress.xp)
            result["xp_earned"] = xp

        # Achievements
        streak = await adherence_streak(db, user_id)
        result["streak"] = streak
        notifications: list[Notification] = []
        for code, threshold, label in (
            (ACH_FIRST, 0, "First on-time dose"),
            (ACH_3, 3, f"{streak}-day adherence streak"),
            (ACH_7, 7, f"{streak}-day adherence streak"),
            (ACH_30, 30, f"{streak}-day adherence streak"),
        ):
            if code == ACH_FIRST:
                # first ever taken intake
                n = await _award_achievement(db, user_id, code, f"{medication_name} — {label}")
            elif streak >= threshold:
                n = await _award_achievement(db, user_id, code, f"{medication_name} — {label}")
            else:
                n = None
            if n is not None:
                result["new_achievements"] += 1
                ach = (
                    await db.execute(select(Achievement).where(Achievement.id == n.achievement_id))
                ).scalar_one_or_none()
                title, body = neutral_notification(
                    prefs,
                    f"Achievement: {ach.name if ach else code} 🏆",
                    (ach.description if ach else "") or label,
                    locale,
                )
                notif = Notification(
                    user_id=user_id,
                    type="achievement",
                    title=title,
                    body=body,
                    link="/achievements",
                )
                db.add(notif)
                notifications.append(notif)

        db.add(progress)
        await db.flush()

        if notifications:
            from app.gamification.handler import _send_push_notifications, _send_tg_notifications

            await _send_tg_notifications(db, user_id, notifications)
            await _send_push_notifications(db, user_id, notifications)
    except Exception:
        # Adherence gamification must never break the intake recording.
        logger.warning("Medication adherence gamification failed", exc_info=True)
        result = {"xp_earned": 0, "new_achievements": 0, "streak": 0}
    return result
