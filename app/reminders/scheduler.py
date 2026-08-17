"""Reminder scheduler — periodic delivery of personal-contour reminders.

Runs via asyncio loop (no extra deps). At the configured time (reminder_time,
in reminder_tz) it runs one full reminder cycle for all users. Mirrors the
training auto-analysis scheduler pattern.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import date, datetime

from app.config import settings
from app.database import async_session_factory
from app.timeutils import resolve_tz

logger = logging.getLogger(__name__)

_check_interval_seconds = 60  # Check every minute


async def _run_daily() -> None:
    from app.reminders.engine import run_reminder_cycle

    async with async_session_factory() as db:
        delivered = await run_reminder_cycle(db, tz_name=settings.reminder_tz, mode="daily")
        if delivered:
            logger.info(f"Reminders (daily): delivered {delivered} notification(s)")

    # Auto-run Personal Insights (ADR-095) — пользователи, включившие insights_auto.
    from app.insights.scheduler import run_auto_insights

    async with async_session_factory() as db:
        runs = await run_auto_insights(db)
        if runs:
            logger.info(f"Auto-insights: {runs} run(s)")


async def _run_event() -> None:
    from app.reminders.engine import run_reminder_cycle

    async with async_session_factory() as db:
        delivered = await run_reminder_cycle(db, tz_name=settings.reminder_tz, mode="event")
        if delivered:
            logger.info(f"Reminders (event): delivered {delivered} notification(s)")


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    import time as _time

    hour, minute = _parse_time(settings.reminder_time)
    tz = resolve_tz(settings.reminder_tz)
    event_interval = max(10, settings.reminder_event_interval_minutes * 60)
    logger.info(
        f"Reminder scheduler started (daily at {hour:02d}:{minute:02d} {settings.reminder_tz}; "
        f"event every {settings.reminder_event_interval_minutes}m, "
        f"lead {settings.reminder_event_lead_minutes}m)"
    )

    last_daily: date | None = None
    last_event = 0.0
    while not stop_event.is_set():
        try:
            now = datetime.now(tz)
            if now.hour == hour and now.minute == minute and last_daily != now.date():
                logger.info("Reminders: triggering daily run")
                await _run_daily()
                last_daily = now.date()

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
