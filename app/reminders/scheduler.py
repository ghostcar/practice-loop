"""Reminder scheduler — periodic delivery of personal-contour reminders.

Runs via asyncio loop (no extra deps). Each user's daily reminder cycle fires
at their own ``prefs.reminder_time`` in their own ``prefs.reminder_tz``
(falling back to the global ``REMINDER_TIME``/``REMINDER_TZ`` — ADR-098).
Event reminders ("shortly before", ADR-096) run on a global cadence but each
user's "now" is computed in their own timezone. Auto-run Personal Insights
(ADR-095) fires once per day on the global default schedule.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from datetime import date, datetime

from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.prefs import prefs_from_dict
from app.timeutils import resolve_tz

logger = logging.getLogger(__name__)

_check_interval_seconds = 60  # Check every minute


async def _run_daily_for_user(user_id: uuid.UUID) -> None:
    from app.models.user import User
    from app.reminders.engine import run_reminder_cycle_for_user

    async with async_session_factory() as db:
        user = await db.get(User, user_id)
        if user is None:
            return
        delivered = await run_reminder_cycle_for_user(db, user, mode="daily")
        await db.commit()
        if delivered:
            logger.info(f"Reminders (daily): delivered {delivered} for user {user_id}")


async def _run_event() -> None:
    from app.reminders.engine import run_reminder_cycle

    async with async_session_factory() as db:
        delivered = await run_reminder_cycle(db, tz_name=settings.reminder_tz, mode="event")
        if delivered:
            logger.info(f"Reminders (event): delivered {delivered} notification(s)")


async def _run_auto_insights_once() -> None:
    from app.insights.scheduler import run_auto_insights

    async with async_session_factory() as db:
        runs = await run_auto_insights(db)
        if runs:
            logger.info(f"Auto-insights: {runs} run(s)")


async def _due_users(last_daily: dict[uuid.UUID, date]) -> dict[uuid.UUID, date]:
    """Users whose local time has reached their configured reminder_time today.

    Returns a ``{user_id: local_date}`` map for users due for their daily
    reminder cycle. The ">= time and not yet run today" guard makes the check
    robust against the 60s loop drifting past the exact minute.
    """
    from app.models.user import User

    async with async_session_factory() as db:
        users = (await db.execute(select(User))).scalars().all()

    due: dict[uuid.UUID, date] = {}
    for user in users:
        prefs = prefs_from_dict(user.prefs)
        tz = resolve_tz(prefs.reminder_tz or settings.reminder_tz)
        now = datetime.now(tz)
        hour, minute = _parse_time(prefs.reminder_time or settings.reminder_time)
        due_minutes = hour * 60 + minute
        if now.hour * 60 + now.minute >= due_minutes and last_daily.get(user.id) != now.date():
            due[user.id] = now.date()
    return due


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    import time as _time

    default_tz = resolve_tz(settings.reminder_tz)
    default_hour, default_minute = _parse_time(settings.reminder_time)
    event_interval = max(10, settings.reminder_event_interval_minutes * 60)
    logger.info(
        f"Reminder scheduler started (per-user daily time/tz, default "
        f"{default_hour:02d}:{default_minute:02d} {settings.reminder_tz}; "
        f"event every {settings.reminder_event_interval_minutes}m, "
        f"lead {settings.reminder_event_lead_minutes}m)"
    )

    last_daily: dict[uuid.UUID, date] = {}
    last_auto: date | None = None
    last_event = 0.0
    while not stop_event.is_set():
        try:
            # Daily per-user reminder cycle (ADR-098).
            for user_id, day in (await _due_users(last_daily)).items():
                await _run_daily_for_user(user_id)
                last_daily[user_id] = day

            # Auto-run Personal Insights once per day (global default schedule).
            default_now = datetime.now(default_tz)
            default_due = default_now.hour * 60 + default_now.minute >= default_hour * 60 + default_minute
            if default_due and last_auto != default_now.date():
                await _run_auto_insights_once()
                last_auto = default_now.date()

            # Event reminders — faster cadence, "shortly before" events (ADR-096).
            if _time.monotonic() - last_event >= event_interval:
                await _run_event()
                last_event = _time.monotonic()

            await asyncio.wait_for(stop_event.wait(), timeout=_check_interval_seconds)
        except TimeoutError:
            pass  # normal
        except Exception:
            logger.exception("Reminder scheduler error")
            await asyncio.sleep(10)


def _parse_time(time_str: str) -> tuple[int, int]:
    parts = time_str.strip().split(":")
    return int(parts[0]) % 24, int(parts[1]) % 60


_stop_event: asyncio.Event | None = None
_task: asyncio.Task | None = None


async def start_reminders() -> None:
    """Start the reminder scheduler. Called at app startup."""
    global _stop_event, _task

    if _task is not None:
        return
    if not settings.reminder_enabled:
        logger.info("Reminder scheduler disabled (REMINDER_ENABLED=false)")
        return

    _stop_event = asyncio.Event()
    _task = asyncio.create_task(_scheduler_loop(_stop_event))
    logger.info("Reminder scheduler background task created")


async def stop_reminders() -> None:
    """Stop the reminder scheduler. Called at app shutdown."""
    global _stop_event, _task

    if _stop_event:
        _stop_event.set()
    if _task:
        _task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _task
        _task = None
    logger.info("Reminder scheduler stopped")
