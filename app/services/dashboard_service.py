"""Dashboard service — all business logic for dashboard, achievements, notifications, privacy.

Extracted from app/api/dashboard.py (ADR-167).  HTTP layer stays thin.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.gamification.handler import get_or_create_progress
from app.gamification.xp import xp_progress
from app.models.achievement import Achievement, UserAchievement
from app.models.activity_log import ActivityLog
from app.models.diet import Diet, DietConsumption
from app.models.health import CycleSettings, HealthState
from app.models.notification import Notification
from app.models.session import ActivitySession
from app.models.training import TrainingDay
from app.models.user import User
from app.timeutils import local_today

# ─────────────────────────────────────────────────────────────────────────────
# Locale-aware date label for the dashboard header (DESIGN v2 §9).
# ─────────────────────────────────────────────────────────────────────────────

_DASH_WEEKDAYS = {
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
    "ru": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
}
_DASH_MONTHS = {
    "en": [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ],
    "ru": [
        "января",
        "февраля",
        "марта",
        "апреля",
        "мая",
        "июня",
        "июля",
        "августа",
        "сентября",
        "октября",
        "ноября",
        "декабря",
    ],
}

_FAR_FUTURE = datetime(9999, 1, 1, tzinfo=UTC)


def today_label(day: datetime.date, locale: str) -> str:
    """Human date in the user's locale, e.g. 'Tuesday, 14 August 2026'."""
    wd = _DASH_WEEKDAYS.get(locale, _DASH_WEEKDAYS["en"])[day.weekday()]
    mo = _DASH_MONTHS.get(locale, _DASH_MONTHS["en"])[day.month - 1]
    return f"{wd}, {day.day} {mo} {day.year}"


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard page context
# ─────────────────────────────────────────────────────────────────────────────


async def get_dashboard_context(db: AsyncSession, user: User, locale: str) -> dict:
    """Build the full dashboard context dict (all queries + summaries)."""
    from app.prefs import sanitize_prefs

    progress = await get_or_create_progress(db, user.id)
    level, xp_current, xp_next = xp_progress(progress.xp)

    today = local_today()
    today_start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    today_end = today_start + timedelta(days=1)

    # Today's scheduled tasks
    today_tasks_result = await db.execute(
        select(ActivityLog)
        .where(
            ActivityLog.user_id == user.id,
            ActivityLog.scheduled_at >= today_start,
            ActivityLog.scheduled_at < today_end,
            ActivityLog.status.in_(["planned", "in_progress"]),
        )
        .order_by(ActivityLog.scheduled_at)
        .limit(10)
    )
    today_tasks = list(today_tasks_result.scalars().all())

    # Active diets
    diets_result = await db.execute(
        select(Diet).where(Diet.user_id == user.id, Diet.is_active.is_(True)).order_by(Diet.created_at).limit(3)
    )
    active_diets = list(diets_result.scalars().all())

    # Today's training plans
    training_result = await db.execute(
        select(TrainingDay)
        .where(TrainingDay.user_id == user.id, TrainingDay.target_date == today)
        .order_by(TrainingDay.created_at)
        .limit(3)
    )
    today_training = list(training_result.scalars().all())

    training_task_counts: dict = {}
    if today_training:
        td_ids = [td.id for td in today_training]
        counts_result = await db.execute(
            select(
                ActivityLog.training_day_id,
                func.count(ActivityLog.id),
                func.sum(case((ActivityLog.status == "completed", 1), else_=0)),
            )
            .where(ActivityLog.training_day_id.in_(td_ids))
            .group_by(ActivityLog.training_day_id)
        )
        for row in counts_result:
            training_task_counts[str(row[0])] = {"total": row[1] or 0, "completed": row[2] or 0}

    # Today's calendar schedule
    from app.services.calendar_service import get_day_schedule

    today_schedule = await get_day_schedule(db, user.id, today)

    # Today's diet consumption count
    consumption_count_result = await db.execute(
        select(func.count(DietConsumption.id)).where(
            DietConsumption.user_id == user.id,
            DietConsumption.consumed_date == today,
        )
    )
    today_meals = consumption_count_result.scalar() or 0

    # Recent activity logs
    result = await db.execute(
        select(ActivityLog).where(ActivityLog.user_id == user.id).order_by(ActivityLog.created_at.desc()).limit(5)
    )
    recent_logs = result.scalars().all()

    # Active sessions
    sess_result = await db.execute(
        select(ActivitySession)
        .where(ActivitySession.owner_id == user.id, ActivitySession.status.in_(["created", "active"]))
        .order_by(ActivitySession.created_at.desc())
    )
    active_sessions = sess_result.scalars().all()

    # Notifications count
    notif_count_result = await db.execute(
        select(func.count(Notification.id)).where(Notification.user_id == user.id, not Notification.is_read)
    )
    unread_notifs = notif_count_result.scalar() or 0

    # LockTimer active session
    locktimer_session, locktimer_slots_count, locktimer_tasks_count = await _get_locktimer_summary(db, user.id)

    # Module summaries (relief-only, informational)
    med_summary = await _safe_summary("medication", "medication_enabled", "_schedule_summary", db, user.id)
    health_summary = await _safe_summary("health", "health_enabled", "_health_summary", db, user.id)
    journal_summary = await _safe_summary("journal", "journal_enabled", "_journal_summary", db, user.id)
    care_summary = await _safe_summary_care(db, user.id)
    aftercare_summary = await _safe_summary("aftercare", "aftercare_enabled", "_aftercare_summary", db, user.id)
    insights_summary = await _safe_summary("insights", "insights_enabled", "_insights_summary", db, user.id)

    # Merged today items (tasks + meds)
    today_items = _merge_today_items(today_tasks, med_summary)

    # Dashboard alerts
    dashboard_alerts = await _build_dashboard_alerts(db, user.id, today, med_summary, locktimer_session)

    enabled_modules = sanitize_prefs(user.prefs).get("enabled_modules", [])

    return {
        "progress": progress,
        "level": level,
        "xp_current": xp_current,
        "xp_next": xp_next,
        "xp_percent": int(xp_current / max(xp_next, 1) * 100),
        "recent_logs": recent_logs,
        "active_sessions": active_sessions,
        "unread_notifs": unread_notifs,
        "tg_bot_username": settings.tg_bot_username,
        "enabled_modules": enabled_modules,
        "locktimer_session": locktimer_session,
        "locktimer_slots_count": locktimer_slots_count,
        "locktimer_tasks_count": locktimer_tasks_count,
        "today_tasks": today_tasks,
        "today_items": today_items,
        "dashboard_alerts": dashboard_alerts,
        "active_diets": active_diets,
        "today_training": today_training,
        "training_task_counts": training_task_counts,
        "today_schedule": today_schedule,
        "today_meals": today_meals,
        "today_label": today_label(today, locale),
        "med_summary": med_summary,
        "health_summary": health_summary,
        "journal_summary": journal_summary,
        "care_summary": care_summary,
        "aftercare_summary": aftercare_summary,
        "insights_summary": insights_summary,
    }


# ─────────────────────────────────────────────────────────────────────────────
# LockTimer summary
# ─────────────────────────────────────────────────────────────────────────────


async def _get_locktimer_summary(db: AsyncSession, user_id: uuid.UUID) -> tuple:
    """Returns (session_dict_or_None, slots_count, tasks_count)."""
    try:
        from app.platform.composition import composition

        if not composition.timer_operational:
            return None, 0, 0
        from app.locktimer.repositories import get_active_session as get_lt_active
        from app.locktimer.repositories import list_slot_occurrences, list_task_occurrences

        lt_active = await get_lt_active(db, user_id)
        if not lt_active:
            return None, 0, 0

        lt_slots = await list_slot_occurrences(db, lt_active.id, limit=50)
        lt_tasks = await list_task_occurrences(db, lt_active.id, limit=50)
        session_dict = {
            "id": str(lt_active.id),
            "state": lt_active.state,
            "duration_type": lt_active.duration_type,
            "timezone": lt_active.timezone,
            "started_at": lt_active.started_at,
            "effective_end_at": lt_active.effective_end_at,
        }
        return session_dict, len(lt_slots), len(lt_tasks)
    except Exception:
        return None, 0, 0


# ─────────────────────────────────────────────────────────────────────────────
# Module summary loaders (safe wrappers)
# ─────────────────────────────────────────────────────────────────────────────


async def _safe_summary(
    module_name: str,
    flag_name: str,
    func_name: str,
    db: AsyncSession,
    user_id: uuid.UUID,
):
    """Load a module summary if the module is enabled."""
    try:
        from app.platform.composition import composition

        if not getattr(composition, flag_name, False):
            return None

        if module_name == "medication":
            from app.services.med_service import schedule_summary

            return await schedule_summary(db, user_id)
        elif module_name == "health":
            from app.services.health_service import health_summary

            return await health_summary(db, user_id)
        elif module_name == "journal":
            from app.services.journal_service import journal_summary

            return await journal_summary(db, user_id)
        elif module_name == "aftercare":
            # Not yet decomposed into service
            from app.api.aftercare import _aftercare_summary

            return await _aftercare_summary(db, user_id)
        elif module_name == "insights":
            from app.services.insights_service import insights_summary

            return await insights_summary(db, user_id)
    except Exception:
        pass
    return None


async def _safe_summary_care(db: AsyncSession, user_id: uuid.UUID):
    """Load care summary (uses care_service directly)."""
    try:
        from app.platform.composition import composition

        if not composition.care_enabled:
            return None
        from app.services.care_service import get_care_summary

        return await get_care_summary(db, user_id)
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Today items merge
# ─────────────────────────────────────────────────────────────────────────────


def _merge_today_items(today_tasks: list, med_summary: dict | None) -> list[dict]:
    """Combine scheduled tasks with due meds for the 'today' view."""
    items: list[dict] = [
        {
            "kind": "task",
            "id": str(t.id),
            "title": t.title_override or t.selected_entity_name or "(task)",
            "status": t.status,
            "at": t.scheduled_at,
            "medication_id": None,
        }
        for t in today_tasks
    ]
    if med_summary and med_summary.get("due"):
        for d in med_summary["due"]:
            items.append(
                {
                    "kind": "med",
                    "id": d["id"],
                    "title": d["medication_name"],
                    "status": "med",
                    "at": None,
                    "medication_id": d["medication_id"],
                    "dose": d.get("dose"),
                    "pending": d.get("pending", 1),
                }
            )
    items.sort(key=lambda x: x["at"] or _FAR_FUTURE)
    return items[:10]


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard alert bar
# ─────────────────────────────────────────────────────────────────────────────


async def _build_dashboard_alerts(
    db: AsyncSession,
    user_id: uuid.UUID,
    today,
    med_summary: dict | None,
    locktimer_session: dict | None,
) -> list[dict]:
    """Build dashboard alert bar from health state, meds, locktimer."""
    alerts: list[dict] = []
    try:
        today_state = (
            await db.execute(select(HealthState).where(HealthState.user_id == user_id, HealthState.event_date == today))
        ).scalar_one_or_none()
        c_settings = (
            await db.execute(select(CycleSettings).where(CycleSettings.user_id == user_id))
        ).scalar_one_or_none()

        if today_state and today_state.post_session_drop:
            alerts.append(
                {
                    "type": "warning",
                    "icon": "heart",
                    "title": "Post-session Drop (Эмоциональный спад)",
                    "message": (
                        "Активирован режим бережного восстановления. "
                        "Рекомендуются расслабляющие процедуры Ухода и Aftercare."
                    ),
                    "action_url": "/care",
                    "action_label": "Протоколы Ухода",
                }
            )
        elif today_state and today_state.recovery is not None and today_state.recovery <= 2:
            alerts.append(
                {
                    "type": "warning",
                    "icon": "today",
                    "title": f"Низкий уровень восстановления ({today_state.recovery}/5)",
                    "message": "ИИ-Наблюдатель рекомендует снизить интенсивность физических тренировок и нагрузок.",
                    "action_url": "/health",
                    "action_label": "Дневник Здоровья",
                }
            )

        if c_settings and c_settings.profile_type == "hrt_emulated" and (not today_state or not today_state.hrt_taken):
            alerts.append(
                {
                    "type": "info",
                    "icon": "health",
                    "title": "Напоминание ГТ / HRT",
                    "message": "Не забудьте отметить сегодняшний приём гормональной терапии в Дневнике Здоровья.",
                    "action_url": "/health",
                    "action_label": "Отметить ГТ",
                }
            )
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("failed building dashboard alerts: %s", exc)

    if med_summary and med_summary.get("due"):
        alerts.append(
            {
                "type": "info",
                "icon": "medication",
                "title": "Запланированный приём медикаментов",
                "message": f"Ожидают приёма {len(med_summary['due'])} поз. на сегодня.",
                "action_url": "/medications",
                "action_label": "Принять",
            }
        )

    if locktimer_session:
        alerts.append(
            {
                "type": "lock",
                "icon": "lock",
                "title": "Активен Контроль Доступа (Замок)",
                "message": f"Режим: {locktimer_session['state']}. Ограничения активны.",
                "action_url": "/timer/dashboard",
                "action_label": "Статус замка",
            }
        )

    return alerts


# ─────────────────────────────────────────────────────────────────────────────
# Achievements
# ─────────────────────────────────────────────────────────────────────────────


async def get_achievements_context(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Build achievements page context."""
    # All user achievements (anonymized)
    all_result = await db.execute(
        select(UserAchievement, Achievement)
        .join(Achievement, UserAchievement.achievement_id == Achievement.id)
        .where(not UserAchievement.is_hidden)
        .order_by(UserAchievement.obtained_at.desc())
        .limit(30)
    )
    all_achievements = []
    for ua, ach in all_result:
        all_achievements.append(
            {
                "code": ach.code,
                "name": ach.name,
                "description": ach.description,
                "color": ach.color,
                "obtained_at": ua.obtained_at,
                "display_name": "Anonymous" if ua.user_id != user_id else "You",
            }
        )

    # My achievements
    my_result = await db.execute(
        select(UserAchievement, Achievement)
        .join(Achievement, UserAchievement.achievement_id == Achievement.id)
        .where(UserAchievement.user_id == user_id)
        .order_by(UserAchievement.obtained_at.desc())
    )
    my_achievements = []
    for ua, ach in my_result:
        my_achievements.append(
            {
                "id": ua.id,
                "code": ach.code,
                "name": ach.name,
                "description": ach.description,
                "color": ach.color,
                "context": ua.context,
                "obtained_at": ua.obtained_at,
                "is_hidden": ua.is_hidden,
            }
        )

    return {"all_achievements": all_achievements, "my_achievements": my_achievements}


async def toggle_achievement_visibility(db: AsyncSession, ua_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Toggle achievement visibility on public board."""
    result = await db.execute(select(UserAchievement).where(UserAchievement.id == ua_id))
    ua = result.scalar_one_or_none()
    if ua and ua.user_id != user_id:
        ua = None
    if ua:
        ua.is_hidden = not ua.is_hidden
        db.add(ua)
        await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Notifications
# ─────────────────────────────────────────────────────────────────────────────


async def get_notifications(db: AsyncSession, user_id: uuid.UUID) -> list:
    """Get user's notifications."""
    result = await db.execute(
        select(Notification).where(Notification.user_id == user_id).order_by(Notification.created_at.desc()).limit(50)
    )
    return list(result.scalars().all())


async def mark_notification_read(db: AsyncSession, n_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Mark a notification as read. Returns True if found."""
    result = await db.execute(select(Notification).where(Notification.id == n_id))
    n = result.scalar_one_or_none()
    if n and n.user_id != user_id:
        n = None
    if n:
        n.is_read = True
        db.add(n)
        await db.flush()
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Telegram linking
# ─────────────────────────────────────────────────────────────────────────────


async def generate_tg_link_code(db: AsyncSession, user: User) -> dict:
    """Generate a 6-char code for Telegram linking (expires in 30 min)."""
    code = secrets.token_hex(3).upper()
    user.telegram_link_code = code
    user.telegram_link_code_expires = datetime.now(UTC) + timedelta(minutes=30)
    db.add(user)
    await db.flush()
    return {"code": code, "expires_in_minutes": 30}


def get_tg_link_status(user: User) -> dict:
    """Check if Telegram is linked."""
    return {
        "linked": user.telegram_chat_id is not None,
        "code": user.telegram_link_code if not user.telegram_chat_id else None,
    }
