"""Today projection (C4, PRODUCT_OVERVIEW §10.1).

Единый спокойный экран дня: объединяет обзор по всем личным модулям, но не
правила — каждый блок сохраняет собственную предметную модель. Никакой новой
агрегированной модели не создаётся: только view-level сшивка существующих
сводок (Tracker, Timer, Health/Cycle, Medication, Care, Aftercare, Journal,
Training, Diet).

Страница:
- GET /today — консолидированный обзор текущего дня
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.activity_log import ActivityLog
from app.models.diet import Diet
from app.models.session import ActivitySession
from app.models.training import TrainingDay
from app.models.user import User
from app.platform.composition import get_composition
from app.templates_setup import templates
from app.timeutils import local_today

router = APIRouter(tags=["today"])


async def _safe(fn):
    """Run a summary helper, returning None if the module is not deployed."""
    try:
        return await fn()
    except Exception:
        return None


@router.get("/today", response_class=HTMLResponse)
async def today_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    composition = get_composition()

    today = local_today()
    today_start = datetime(today.year, today.month, today.day, tzinfo=UTC)
    today_end = today_start + timedelta(days=1)

    # Tracker: today's scheduled tasks + active session
    tasks_result = await db.execute(
        select(ActivityLog)
        .where(
            ActivityLog.user_id == user.id,
            ActivityLog.scheduled_at >= today_start,
            ActivityLog.scheduled_at < today_end,
            ActivityLog.status.in_(["planned", "in_progress"]),
        )
        .order_by(ActivityLog.scheduled_at)
        .limit(15)
    )
    tasks = list(tasks_result.scalars().all())

    active_session = (
        await db.execute(
            select(ActivitySession).where(
                ActivitySession.owner_id == user.id,
                ActivitySession.status.in_(["created", "active"]),
            )
        )
    ).scalar_one_or_none()

    # Training today
    training_result = await db.execute(
        select(TrainingDay).where(TrainingDay.user_id == user.id, TrainingDay.target_date == today).limit(3)
    )
    today_training = list(training_result.scalars().all())

    # Active diets
    diets_result = await db.execute(
        select(Diet).where(Diet.user_id == user.id, Diet.is_active.is_(True)).order_by(Diet.created_at).limit(3)
    )
    active_diets = list(diets_result.scalars().all())

    # Timer active session
    timer = None
    if composition.timer_operational:
        try:
            from app.locktimer.repositories import (
                get_active_session,
                list_slot_occurrences,
                list_task_occurrences,
            )

            lt_active = await get_active_session(db, user.id)
            if lt_active:
                slots = await list_slot_occurrences(db, lt_active.id, limit=50)
                tasks_n = await list_task_occurrences(db, lt_active.id, limit=50)
                timer = {
                    "id": str(lt_active.id),
                    "state": lt_active.state,
                    "duration_type": lt_active.duration_type,
                    "timezone": lt_active.timezone,
                    "started_at": lt_active.started_at,
                    "effective_end_at": lt_active.effective_end_at,
                    "slots_count": len(slots),
                    "tasks_count": len(tasks_n),
                }
        except Exception:
            timer = None

    # Module summaries (relief-only)
    med_summary = (
        await _safe(lambda: _load_med_summary(db, user.id)) if composition.medication_enabled else None
    )
    health_summary = (
        await _safe(lambda: _load_health_summary(db, user.id)) if composition.health_enabled else None
    )
    care_summary = (
        await _safe(lambda: _load_care_summary(db, user.id)) if composition.care_enabled else None
    )
    aftercare_summary = (
        await _safe(lambda: _load_aftercare_summary(db, user.id)) if composition.aftercare_enabled else None
    )
    journal_summary = (
        await _safe(lambda: _load_journal_summary(db, user.id)) if composition.journal_enabled else None
    )

    return templates.TemplateResponse(
        request,
        "today.html",
        {
            "t": t,
            "theme": theme,
            "nav_key": "today",
            "today_label": _today_label(today, locale),
            "tasks": tasks,
            "active_session": active_session,
            "today_training": today_training,
            "active_diets": active_diets,
            "timer": timer,
            "med_summary": med_summary,
            "health_summary": health_summary,
            "care_summary": care_summary,
            "aftercare_summary": aftercare_summary,
            "journal_summary": journal_summary,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Lazy loaders (import inside so a missing module never breaks the page)
# ─────────────────────────────────────────────────────────────────────────────


async def _load_med_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    from app.api.medication import _schedule_summary

    return await _schedule_summary(db, user_id)


async def _load_health_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    from app.api.health import _health_summary

    return await _health_summary(db, user_id)


async def _load_care_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    from app.api.care import _care_summary

    return await _care_summary(db, user_id)


async def _load_aftercare_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    from app.api.aftercare import _aftercare_summary

    return await _aftercare_summary(db, user_id)


async def _load_journal_summary(db: AsyncSession, user_id: uuid.UUID) -> dict:
    from app.api.journal import _journal_summary

    return await _journal_summary(db, user_id)


def _today_label(day, locale: str) -> str:
    """Human date label (mirrors dashboard helper)."""
    weekdays = {
        "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
        "ru": ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"],
    }
    months = {
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
    wd = weekdays.get(locale, weekdays["en"])[day.weekday()]
    mo = months.get(locale, months["en"])[day.month - 1]
    return f"{wd}, {day.day} {mo} {day.year}"
