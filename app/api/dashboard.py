"""Dashboard, achievements, notifications, sessions, privacy."""

import json
import secrets
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.gamification.handler import get_or_create_progress
from app.gamification.xp import xp_progress
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.achievement import Achievement, UserAchievement
from app.models.activity_log import ActivityLog
from app.models.diet import Diet
from app.models.notification import Notification
from app.models.progress import UserProgress
from app.models.session import ActivitySession
from app.models.session_history import ActivitySessionHistory
from app.models.training import TrainingDay
from app.models.user import User
from app.security import ensure_csrf_cookie
from app.services.personal_export import build_personal_export
from app.templates_setup import templates
from app.timeutils import local_today

# Locale-aware date label for the dashboard header (DESIGN v2 §9).
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


# Sentinel for sorting items without a scheduled time to the end of the day list.
_FAR_FUTURE = datetime(9999, 1, 1, tzinfo=UTC)


def _today_label(day: datetime.date, locale: str) -> str:
    """Human date in the user's locale, e.g. "Tuesday, 14 August 2026"."""
    wd = _DASH_WEEKDAYS.get(locale, _DASH_WEEKDAYS["en"])[day.weekday()]
    mo = _DASH_MONTHS.get(locale, _DASH_MONTHS["en"])[day.month - 1]
    return f"{wd}, {day.day} {mo} {day.year}"


router = APIRouter(tags=["dashboard-v2"])
session_json_router = APIRouter(prefix="/api/v2/sessions", tags=["sessions"])


# --- Dashboard ---


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Dashboard with real stats."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    progress = await get_or_create_progress(db, user.id)
    level, xp_current, xp_next = xp_progress(progress.xp)

    # Today's scheduled tasks
    today = local_today()
    today_start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    today_end = today_start + timedelta(days=1)
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

    # Active diets summary
    diets_result = await db.execute(
        select(Diet).where(Diet.user_id == user.id, Diet.is_active.is_(True)).order_by(Diet.created_at).limit(3)
    )
    active_diets = list(diets_result.scalars().all())

    # Today's training plans
    training_result = await db.execute(
        select(TrainingDay)
        .where(
            TrainingDay.user_id == user.id,
            TrainingDay.target_date == today,
        )
        .order_by(TrainingDay.created_at)
        .limit(3)
    )
    today_training = list(training_result.scalars().all())
    # Get task counts for today's training
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

    # Today's calendar schedule (reuse existing call)
    from app.api.calendar import get_day_schedule

    today_schedule = await get_day_schedule(db, user.id, today)

    # Today's diet consumption count
    from app.models.diet import DietConsumption

    consumption_count_result = await db.execute(
        select(func.count(DietConsumption.id)).where(
            DietConsumption.user_id == user.id,
            DietConsumption.consumed_date == today,
        )
    )
    today_meals = consumption_count_result.scalar() or 0
    result = await db.execute(
        select(ActivityLog).where(ActivityLog.user_id == user.id).order_by(ActivityLog.created_at.desc()).limit(5)
    )
    recent_logs = result.scalars().all()

    # Active sessions (multiple may run in parallel — migration 063)
    sess_result = await db.execute(
        select(ActivitySession)
        .where(
            ActivitySession.owner_id == user.id,
            ActivitySession.status.in_(["created", "active"]),
        )
        .order_by(ActivitySession.created_at.desc())
    )
    active_sessions = sess_result.scalars().all()

    # Notifications count
    notif_count_result = await db.execute(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id,
            not Notification.is_read,
        )
    )
    unread_notifs = notif_count_result.scalar() or 0

    # LockTimer active session (if timer operational)
    locktimer_session = None
    locktimer_slots_count = 0
    locktimer_tasks_count = 0
    try:
        from app.platform.composition import composition

        if composition.timer_operational:
            from app.locktimer.repositories import get_active_session as get_lt_active

            lt_active = await get_lt_active(db, user.id)
            if lt_active:
                from app.locktimer.repositories import list_slot_occurrences, list_task_occurrences

                lt_slots = await list_slot_occurrences(db, lt_active.id, limit=50)
                lt_tasks = await list_task_occurrences(db, lt_active.id, limit=50)
                locktimer_session = {
                    "id": str(lt_active.id),
                    "state": lt_active.state,
                    "duration_type": lt_active.duration_type,
                    "timezone": lt_active.timezone,
                    "started_at": lt_active.started_at,
                    "effective_end_at": lt_active.effective_end_at,
                }
                locktimer_slots_count = len(lt_slots)
                locktimer_tasks_count = len(lt_tasks)
    except Exception:
        pass  # LockTimer may not be deployed yet

    # Medication summary (due today / expiring / low stock) — relief-only, informational.
    med_summary = None
    try:
        from app.platform.composition import composition

        if composition.medication_enabled:
            from app.api.medication import _schedule_summary

            med_summary = await _schedule_summary(db, user.id)
    except Exception:
        pass  # medication may not be deployed yet

    # Health summary (today check-in / labs count / cycle phase) — relief-only.
    health_summary = None
    try:
        from app.platform.composition import composition

        if composition.health_enabled:
            from app.api.health import _health_summary

            health_summary = await _health_summary(db, user.id)
    except Exception:
        pass  # health may not be deployed yet

    # Sexual Journal summary (entries 30d / last entry / avg satisfaction) — relief-only.
    journal_summary = None
    try:
        from app.platform.composition import composition

        if composition.journal_enabled:
            from app.api.journal import _journal_summary

            journal_summary = await _journal_summary(db, user.id)
    except Exception:
        pass  # journal may not be deployed yet

    # Personal Care summary (procedures 30d / last / routines count) — relief-only.
    care_summary = None
    try:
        from app.platform.composition import composition

        if composition.care_enabled:
            from app.api.care import _care_summary

            care_summary = await _care_summary(db, user.id)
    except Exception:
        pass  # care may not be deployed yet

    # Aftercare summary (entries total / last / kinds) — relief-only.
    aftercare_summary = None
    try:
        from app.platform.composition import composition

        if composition.aftercare_enabled:
            from app.api.aftercare import _aftercare_summary

            aftercare_summary = await _aftercare_summary(db, user.id)
    except Exception:
        pass  # aftercare may not be deployed yet

    # Personal Insights summary (latest run / findings count) — relief-only.
    insights_summary = None
    try:
        from app.platform.composition import composition

        if composition.insights_enabled:
            from app.api.insights import _insights_summary

            insights_summary = await _insights_summary(db, user.id)
    except Exception:
        pass  # insights may not be deployed yet

    # Tracker 'today' merge (view-level): combine scheduled tasks with due meds
    # so the user sees everything due today in one place. No ActivityLog rows are
    # created — medication stays a separate Health domain (ADR-085, relief-only).
    today_items: list[dict] = [
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
            today_items.append(
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
    today_items.sort(key=lambda x: x["at"] or _FAR_FUTURE)
    today_items = today_items[:10]

    # Dashboard Alert Bar & Cockpit collector (Step 20)
    dashboard_alerts: list[dict] = []
    try:
        from app.models.health import CycleSettings, HealthState

        today_state = (
            await db.execute(select(HealthState).where(HealthState.user_id == user.id, HealthState.event_date == today))
        ).scalar_one_or_none()
        c_settings = (
            await db.execute(select(CycleSettings).where(CycleSettings.user_id == user.id))
        ).scalar_one_or_none()

        if today_state and today_state.post_session_drop:
            dashboard_alerts.append(
                {
                    "type": "warning",
                    "icon": "heart",
                    "title": "📉 Post-session Drop (Эмоциональный спад)",
                    "message": (
                        "Активирован режим бережного восстановления. "
                        "Рекомендуются расслабляющие процедуры Ухода и Aftercare."
                    ),
                    "action_url": "/care",
                    "action_label": "Протоколы Ухода",
                }
            )
        elif today_state and today_state.recovery is not None and today_state.recovery <= 2:
            dashboard_alerts.append(
                {
                    "type": "warning",
                    "icon": "today",
                    "title": f"⚡ Низкий уровень восстановления ({today_state.recovery}/5)",
                    "message": "ИИ-Наблюдатель рекомендует снизить интенсивность физических тренировок и нагрузок.",
                    "action_url": "/health",
                    "action_label": "Дневник Здоровья",
                }
            )

        if c_settings and c_settings.profile_type == "hrt_emulated" and (not today_state or not today_state.hrt_taken):
            dashboard_alerts.append(
                {
                    "type": "info",
                    "icon": "sparkles",
                    "title": "💊 Напоминание ГТ / HRT",
                    "message": "Не забудьте отметить сегодняшний приём гормональной терапии в Дневнике Здоровья.",
                    "action_url": "/health",
                    "action_label": "Отметить ГТ",
                }
            )
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning("failed building dashboard alerts: %s", exc)

    if med_summary and med_summary.get("due"):
        dashboard_alerts.append(
            {
                "type": "info",
                "icon": "medication",
                "title": "💊 Запланированный приём медикаментов",
                "message": f"Ожидают приёма {len(med_summary['due'])} поз. на сегодня.",
                "action_url": "/medications",
                "action_label": "Принять",
            }
        )

    if locktimer_session:
        dashboard_alerts.append(
            {
                "type": "lock",
                "icon": "lock",
                "title": "🔒 Активен Контроль Доступа (Замок)",
                "message": f"Режим: {locktimer_session['state']}. Ограничения активны.",
                "action_url": "/timer/dashboard",
                "action_label": "Статус замка",
            }
        )

    response = templates.TemplateResponse(
        request=request,
        name="dashboard_v2.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "progress": progress,
            "level": level,
            "xp_current": xp_current,
            "xp_next": xp_next,
            "xp_percent": int(xp_current / max(xp_next, 1) * 100),
            "recent_logs": recent_logs,
            "active_sessions": active_sessions,
            "unread_notifs": unread_notifs,
            "tg_bot_username": settings.tg_bot_username,
            "active_nav": "dashboard",
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
            "today_label": _today_label(today, locale),
            "med_summary": med_summary,
            "health_summary": health_summary,
            "journal_summary": journal_summary,
            "care_summary": care_summary,
            "aftercare_summary": aftercare_summary,
            "insights_summary": insights_summary,
        },
    )
    # Set CSRF cookie ONLY if absent — re-issuing it here after render used to
    # desync the HTML meta token from the browser cookie (audit: P0 login→dashboard 403).
    ensure_csrf_cookie(request, response)
    return response


# --- Achievements ---


@router.get("/achievements", response_class=HTMLResponse)
async def achievements_board(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Achievement board: all (anonymized) + my."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

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
                "display_name": "Anonymous" if ua.user_id != user.id else "You",
            }
        )

    # My achievements
    my_result = await db.execute(
        select(UserAchievement, Achievement)
        .join(Achievement, UserAchievement.achievement_id == Achievement.id)
        .where(UserAchievement.user_id == user.id)
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

    return templates.TemplateResponse(
        request=request,
        name="achievements.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "all_achievements": all_achievements,
            "my_achievements": my_achievements,
            "active_nav": "dashboard",
        },
    )


@router.post("/achievements/{ua_id}/hide")
async def hide_achievement(
    request: Request,
    ua_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle achievement visibility on public board."""
    result = await db.execute(select(UserAchievement).where(UserAchievement.id == ua_id))
    ua = result.scalar_one_or_none()
    if ua and ua.user_id != user.id:
        ua = None
    if ua:
        ua.is_hidden = not ua.is_hidden
        db.add(ua)
        await db.flush()
    return RedirectResponse(url="/achievements", status_code=303)


# --- Notifications ---


@router.get("/notifications", response_class=HTMLResponse)
async def notifications_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """In-app notifications list."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    result = await db.execute(
        select(Notification).where(Notification.user_id == user.id).order_by(Notification.created_at.desc()).limit(50)
    )
    notifications = result.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="notifications.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "notifications": notifications,
            "active_nav": "dashboard",
        },
    )


@router.post("/notifications/{n_id}/read")
async def mark_read(
    request: Request,
    n_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a notification as read."""
    result = await db.execute(select(Notification).where(Notification.id == n_id))
    n = result.scalar_one_or_none()
    if n and n.user_id != user.id:
        n = None
    if n:
        n.is_read = True
        db.add(n)
        await db.flush()
    return RedirectResponse(url="/notifications", status_code=303)


# --- Sessions ---


@router.get("/sessions/live", response_class=HTMLResponse)
async def sessions_live_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Interactive Session Live Timer & Control Center page."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="sessions_live.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "sessions",
        },
    )


@router.get("/sessions/coop", response_class=HTMLResponse)
async def sessions_coop_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Partner Multi-User Session Co-Op Portal (Step 77)."""
    from app.models.ds_suite import ManagedSubmissive
    from app.platform.social.repositories import list_user_relationships

    relationships = await list_user_relationships(db, user.id)
    managed_subs = (
        (await db.execute(select(ManagedSubmissive).where(ManagedSubmissive.top_user_id == user.id))).scalars().all()
    )

    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="sessions_coop.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "sessions",
            "relationships": relationships,
            "managed_subs": managed_subs,
        },
    )


@router.post("/sessions/live/complete")
async def live_session_complete_endpoint(
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logs completion of active live session task."""
    from app.gamification.handler import on_task_completed

    await on_task_completed(db, user.id, task_type="live_hold", xp_award=50)
    return RedirectResponse(url="/sessions/live", status_code=303)


@router.post("/sessions/live/interrupt")
async def live_session_interrupt_endpoint(
    reason: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Logs early interruption of live session with penalty penalty deduction."""
    from app.gamification.handler import on_task_interrupted

    await on_task_interrupted(db, user.id, task_type="live_hold", penalty_xp=25)
    return RedirectResponse(url="/sessions/live", status_code=303)


@router.get("/sessions", response_class=HTMLResponse)
async def sessions_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Session management page."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    result = await db.execute(
        select(ActivitySession)
        .where(ActivitySession.owner_id == user.id)
        .order_by(ActivitySession.created_at.desc())
        .limit(20)
    )
    sessions = result.scalars().all()

    history_result = (
        await db.execute(
            select(ActivitySessionHistory)
            .where(ActivitySessionHistory.session_id.in_([s.id for s in sessions]))
            .order_by(ActivitySessionHistory.created_at.desc())
        )
        if sessions
        else None
    )
    histories: dict[uuid.UUID, list[ActivitySessionHistory]] = {s.id: [] for s in sessions}
    if history_result is not None:
        for event in history_result.scalars().all():
            histories[event.session_id].append(event)

    available_result = await db.execute(
        select(ActivityLog)
        .where(
            ActivityLog.user_id == user.id,
            ActivityLog.session_id.is_(None),
            ActivityLog.status.in_(["draft", "planned"]),
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(50)
    )

    return templates.TemplateResponse(
        request=request,
        name="sessions.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "sessions": sessions,
            "session_histories": histories,
            "available_tasks": available_result.scalars().all(),
            "active_nav": "dashboard",
        },
    )


@router.get("/sessions/rules-builder", response_class=HTMLResponse)
async def sessions_rules_builder_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Interactive Session Rules & Contracts Builder page (Step 32)."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="sessions_rules_builder.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "sessions",
        },
    )


@router.get("/sessions/wizard", response_class=HTMLResponse)
async def sessions_wizard_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Interactive Session Wizard & Templates Gallery page (Step 34)."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="sessions_wizard.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "sessions",
        },
    )


@router.get("/sessions/ambient", response_class=HTMLResponse)
async def sessions_ambient_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Interactive Session Soundscape & Ambient Assistant page (Step 38)."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="sessions_ambient.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "sessions",
        },
    )


@router.post("/sessions/create-from-template")
async def create_session_from_template(
    request: Request,
    template_type: str = Form(default="chastity"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates a pre-configured session from a ready template (Step 34)."""
    templates_dict = {
        "chastity": {
            "title": "Chastity & Keyholder Ritual Session",
            "notes": "Сессия контроля доступа, регулярных фото-чек-инов пломб и оценки ИИ-Keyholder.",
            "rules": {"rules": [{"type": "chastity_checkin", "interval_hours": 12}], "ai_role": "keyholder"},
        },
        "training": {
            "title": "Training & Posture Routine Session",
            "notes": "Дисциплинарная сессия физических тренировок, удержания поз и отслеживания выносливости.",
            "rules": {"rules": [{"type": "task_quota", "daily_count": 3}], "ai_role": "observer"},
        },
        "aftercare": {
            "title": "Aftercare & Health Recovery Session",
            "notes": "Мягкая сессия восстановления: уход за кожей, гидратация, стабилизация и Health Pause.",
            "rules": {"rules": [{"type": "health_trigger", "action": "convert_to_aftercare"}], "ai_role": "care"},
        },
        "contract": {
            "title": "Pair BDSM Contract Session",
            "notes": "Полная контрактная сессия с правилами, стоп-словами, эскалациями и заданиями.",
            "rules": {
                "rules": [{"type": "contract_compliance", "safewords": ["RED", "YELLOW"]}],
                "ai_role": "observer",
            },
        },
    }
    cfg = templates_dict.get(template_type, templates_dict["chastity"])

    session = ActivitySession(
        owner_id=user.id,
        status="created",
        title=cfg["title"],
        notes=cfg["notes"],
        session_rules=cfg["rules"],
    )
    db.add(session)
    await db.flush()
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user.id, event_type="created"))
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/create-custom")
async def create_custom_session(
    request: Request,
    title: str = Form(...),
    ai_role: str = Form(default="keyholder"),
    notes: str = Form(default=""),
    ext_wheel: bool = Form(default=False),
    ext_pillory: bool = Form(default=False),
    ext_tag_seal: bool = Form(default=False),
    ext_peer_review: bool = Form(default=False),
    ext_dice: bool = Form(default=False),
    ext_aftercare: bool = Form(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Creates a custom configured session with Chaster.app style attached extensions."""
    extensions_config = {
        "wheel": ext_wheel,
        "pillory": ext_pillory,
        "tag_seal": ext_tag_seal,
        "peer_review": ext_peer_review,
        "dice": ext_dice,
        "aftercare": ext_aftercare,
    }

    session = ActivitySession(
        owner_id=user.id,
        status="created",
        title=title.strip()[:200],
        notes=notes.strip()[:1000] or None,
        session_rules={
            "ai_role": ai_role,
            "custom_session": True,
            "extensions": extensions_config,
        },
    )
    db.add(session)
    await db.flush()
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user.id, event_type="created"))
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions")
async def create_session(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Redirect blank session creation to interactive wizard."""
    return RedirectResponse(url="/sessions/wizard", status_code=303)


async def _owned_session(db: AsyncSession, session_id: uuid.UUID, user: User) -> ActivitySession:
    result = await db.execute(
        select(ActivitySession).where(ActivitySession.id == session_id, ActivitySession.owner_id == user.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def _record_session_event(
    db: AsyncSession,
    session: ActivitySession,
    user: User,
    event_type: str,
    *,
    details: dict | None = None,
    penalize_change: bool = False,
) -> int:
    penalty_xp = 0
    if penalize_change and session.accepted_at is not None:
        configured = (session.session_rules or {}).get("change_penalty_xp", 10)
        try:
            penalty_xp = max(1, int(configured))
        except (TypeError, ValueError):
            penalty_xp = 10
        progress_result = await db.execute(select(UserProgress).where(UserProgress.user_id == user.id))
        progress = progress_result.scalar_one_or_none()
        if progress is None:
            progress = UserProgress(user_id=user.id)
        progress.xp = max(0, progress.xp - penalty_xp)
        progress.combo_count = 0
        progress.total_interrupted += 1
        db.add(progress)
    db.add(
        ActivitySessionHistory(
            session_id=session.id,
            actor_id=user.id,
            event_type=event_type,
            details=details,
            penalty_xp=penalty_xp,
        )
    )
    return penalty_xp


@router.post("/sessions/{s_id}/accept")
async def accept_session(
    s_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, s_id, user)
    if session.status != "created":
        raise HTTPException(status_code=409, detail="Only a created session can be accepted")
    if session.accepted_at is None:
        session.accepted_at = datetime.now(UTC)
        db.add(session)
        await _record_session_event(
            db,
            session,
            user,
            "accepted",
            details={"task_ids": [str(log.id) for log in session.logs]},
        )
        await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/tasks/attach")
async def attach_session_task(
    s_id: uuid.UUID,
    task_id: uuid.UUID = Form(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, s_id, user)
    if session.status == "ended":
        raise HTTPException(status_code=409, detail="Ended session cannot be changed")
    task_result = await db.execute(select(ActivityLog).where(ActivityLog.id == task_id, ActivityLog.user_id == user.id))
    task = task_result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.session_id not in (None, session.id):
        raise HTTPException(status_code=409, detail="Task belongs to another session")
    if task.session_id is None:
        task.session_id = session.id
        db.add(task)
        await _record_session_event(
            db,
            session,
            user,
            "task_added",
            details={"task_id": str(task.id), "title": task.title_override or task.selected_entity_name},
            penalize_change=True,
        )
        await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/tasks/{task_id}/detach")
async def detach_session_task(
    s_id: uuid.UUID,
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, s_id, user)
    if session.status == "ended":
        raise HTTPException(status_code=409, detail="Ended session cannot be changed")
    task_result = await db.execute(
        select(ActivityLog).where(
            ActivityLog.id == task_id,
            ActivityLog.user_id == user.id,
            ActivityLog.session_id == session.id,
        )
    )
    task = task_result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.session_id = None
    db.add(task)
    await _record_session_event(
        db,
        session,
        user,
        "task_removed",
        details={"task_id": str(task.id), "title": task.title_override or task.selected_entity_name},
        penalize_change=True,
    )
    await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/start")
async def start_session(
    request: Request,
    s_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start a session."""
    s = await _owned_session(db, s_id, user)
    if s.status != "created":
        raise HTTPException(status_code=409, detail="Only a created session can be started")
    now = datetime.now(UTC)
    if s.accepted_at is None:
        s.accepted_at = now
        await _record_session_event(db, s, user, "accepted", details={"task_ids": [str(log.id) for log in s.logs]})
    s.status = "active"
    s.started_at = now
    db.add(s)
    await _record_session_event(db, s, user, "started")
    await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/end")
async def end_session(
    request: Request,
    s_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """End a session."""
    s = await _owned_session(db, s_id, user)
    if s.status not in ("created", "active"):
        raise HTTPException(status_code=409, detail="Session is already ended")
    s.status = "ended"
    s.ended_at = datetime.now(UTC)
    db.add(s)
    await _record_session_event(db, s, user, "ended")
    await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


class SessionCreateIn(BaseModel):
    title: str | None = None
    notes: str | None = None
    session_rules: dict | None = None


class SessionTaskIn(BaseModel):
    task_id: uuid.UUID


def _session_json(session: ActivitySession) -> dict:
    # Never trigger relationship I/O from this synchronous serializer. Queries
    # load ``logs`` with selectin; newly-created sessions have no tasks yet.
    logs = session.__dict__.get("logs", [])
    return {
        "id": str(session.id),
        "status": session.status,
        "title": session.title,
        "notes": session.notes,
        "session_rules": session.session_rules,
        "accepted_at": session.accepted_at.isoformat() if session.accepted_at else None,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "task_ids": [str(task.id) for task in logs],
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


@session_json_router.get("")
async def json_sessions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (
        (
            await db.execute(
                select(ActivitySession)
                .where(ActivitySession.owner_id == user.id)
                .order_by(ActivitySession.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [_session_json(session) for session in rows]


@session_json_router.post("")
async def json_create_session(
    data: SessionCreateIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new session. Multiple sessions may run in parallel (migration 063
    dropped the one-active-per-user index)."""
    session = ActivitySession(
        owner_id=user.id,
        status="created",
        title=data.title,
        notes=data.notes,
        session_rules=data.session_rules,
    )
    db.add(session)
    await db.flush()
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user.id, event_type="created"))
    await db.flush()
    return JSONResponse(_session_json(session), status_code=201)


@session_json_router.post("/{session_id}/accept")
async def json_accept_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, session_id, user)
    if session.status != "created":
        raise HTTPException(status_code=409, detail="Only a created session can be accepted")
    if session.accepted_at is None:
        session.accepted_at = datetime.now(UTC)
        await _record_session_event(
            db, session, user, "accepted", details={"task_ids": [str(t.id) for t in session.logs]}
        )
        await db.flush()
    return _session_json(session)


@session_json_router.post("/{session_id}/start")
async def json_start_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, session_id, user)
    if session.status != "created":
        raise HTTPException(status_code=409, detail="Only a created session can be started")
    now = datetime.now(UTC)
    if session.accepted_at is None:
        session.accepted_at = now
        await _record_session_event(
            db, session, user, "accepted", details={"task_ids": [str(t.id) for t in session.logs]}
        )
    session.status = "active"
    session.started_at = now
    await _record_session_event(db, session, user, "started")
    await db.flush()
    return _session_json(session)


@session_json_router.post("/{session_id}/end")
async def json_end_session(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, session_id, user)
    if session.status not in ("created", "active"):
        raise HTTPException(status_code=409, detail="Session is already ended")
    session.status = "ended"
    session.ended_at = datetime.now(UTC)
    await _record_session_event(db, session, user, "ended")
    await db.flush()
    return _session_json(session)


@session_json_router.post("/{session_id}/tasks")
async def json_attach_session_task(
    session_id: uuid.UUID,
    data: SessionTaskIn,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, session_id, user)
    if session.status == "ended":
        raise HTTPException(status_code=409, detail="Ended session cannot be changed")
    task = (
        await db.execute(select(ActivityLog).where(ActivityLog.id == data.task_id, ActivityLog.user_id == user.id))
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.session_id not in (None, session.id):
        raise HTTPException(status_code=409, detail="Task belongs to another session")
    if task.session_id is None:
        task.session_id = session.id
        await _record_session_event(
            db,
            session,
            user,
            "task_added",
            details={"task_id": str(task.id), "title": task.title_override or task.selected_entity_name},
            penalize_change=True,
        )
        await db.flush()
        await db.refresh(session, ["logs"])
    return _session_json(session)


@session_json_router.delete("/{session_id}/tasks/{task_id}", status_code=204)
async def json_detach_session_task(
    session_id: uuid.UUID,
    task_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, session_id, user)
    if session.status == "ended":
        raise HTTPException(status_code=409, detail="Ended session cannot be changed")
    task = (
        await db.execute(
            select(ActivityLog).where(
                ActivityLog.id == task_id,
                ActivityLog.user_id == user.id,
                ActivityLog.session_id == session.id,
            )
        )
    ).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.session_id = None
    await _record_session_event(
        db,
        session,
        user,
        "task_removed",
        details={"task_id": str(task.id), "title": task.title_override or task.selected_entity_name},
        penalize_change=True,
    )
    await db.flush()


@session_json_router.get("/{session_id}/history")
async def json_session_history(
    session_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _owned_session(db, session_id, user)
    events = (
        (
            await db.execute(
                select(ActivitySessionHistory)
                .where(ActivitySessionHistory.session_id == session_id)
                .order_by(ActivitySessionHistory.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": str(event.id),
            "event_type": event.event_type,
            "details": event.details,
            "penalty_xp": event.penalty_xp,
            "created_at": event.created_at.isoformat(),
        }
        for event in events
    ]


# --- Privacy ---


@router.get("/privacy", response_class=HTMLResponse)
async def privacy_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Privacy settings page."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="privacy.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "dashboard",
        },
    )


@router.get("/privacy/export")
async def export_data(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Export the complete owner-scoped Personal manifest as JSON."""
    data = await build_personal_export(db, user)

    return PlainTextResponse(
        json.dumps(data, indent=2, ensure_ascii=False, default=str),
        headers={"Content-Disposition": "attachment; filename=tracker-export.json"},
    )


@router.post("/privacy/delete")
async def delete_account(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete account and all data. Returns logout redirect."""
    await db.delete(user)
    await db.flush()

    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie("access_token")
    return response


# --- Telegram linking ---


@router.post("/profile/telegram-link-code")
async def generate_telegram_link_code(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a 6-character code for linking Telegram. Expires in 30 minutes."""
    code = secrets.token_hex(3).upper()  # 6 hex chars
    user.telegram_link_code = code
    user.telegram_link_code_expires = datetime.now(UTC) + timedelta(minutes=30)
    db.add(user)
    await db.flush()
    return JSONResponse({"code": code, "expires_in_minutes": 30})


@router.get("/profile/telegram-status")
async def telegram_status(
    user: User = Depends(get_current_user),
):
    """Check if Telegram is linked."""
    return JSONResponse(
        {
            "linked": user.telegram_chat_id is not None,
            "code": user.telegram_link_code if not user.telegram_chat_id else None,
        }
    )
