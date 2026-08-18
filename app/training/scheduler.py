"""Background scheduler for end-of-day training analysis.

Runs via asyncio loop — no extra dependencies (no APScheduler needed).
At the configured time (tg_auto_analysis_time, interpreted in tg_auto_analysis_tz),
scans for unanalyzed training days and runs analyze_training_day for each.
"""

import asyncio
import contextlib
import logging
from datetime import UTC, date, datetime

from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.llm.pipeline import analyze_training_day, get_active_llm_config
from app.models.training import TrainingDay
from app.models.user import User
from app.prefs import prefs_from_dict
from app.timeutils import resolve_tz

logger = logging.getLogger(__name__)

_check_interval_seconds = 60  # Check every minute


async def _run_auto_analysis() -> None:
    """Scan for unanalyzed training days and run analysis for each."""
    today = datetime.now(resolve_tz(settings.tg_auto_analysis_tz)).date()

    async with async_session_factory() as db:
        # Find unanalyzed training days for yesterday (or today if it's late)
        # We target yesterday because analysis runs at end-of-day
        result = await db.execute(
            select(TrainingDay).where(
                TrainingDay.target_date <= today,
                TrainingDay.status.in_(["active", "planned"]),  # not yet analyzed/completed
            )
        )
        training_days = result.scalars().all()

        if not training_days:
            return

        logger.info(f"Auto-analysis: found {len(training_days)} unanalyzed training day(s)")

        for td in training_days:
            try:
                config = await get_active_llm_config(db, td.user_id)
                if config is None:
                    logger.debug(f"Auto-analysis: skip user {td.user_id} — no active LLM config")
                    continue

                user = (await db.execute(select(User).where(User.id == td.user_id))).scalar_one_or_none()
                llm_mode = prefs_from_dict(user.prefs).llm_mode if user else "safe"

                await analyze_training_day(
                    db=db,
                    training_day=td,
                    llm_config=config,
                    locale=user.locale if user else "en",
                    llm_mode=llm_mode,
                )
                await db.commit()
                logger.info(f"Auto-analysis: completed for user {td.user_id}, day {td.target_date}")
            except Exception:
                logger.exception(f"Auto-analysis: failed for user {td.user_id}, day {td.target_date}")
                await db.rollback()


async def cleanup_expired_raw_responses(db) -> int:
    """Delete expired raw_llm_response payloads (REM §7.5 TTL enforcement).

    The TTL is currently only written to the DB; this job actually removes the
    retained raw payloads once they expire, so the debug data does not live
    forever (audit: 30-day TTL without cleanup). Returns the number of logs
    cleared. Caller owns the session/commit.
    """
    from sqlalchemy import update as sa_update

    from app.models.activity_log import ActivityLog

    now = datetime.now(UTC)
    result = await db.execute(
        sa_update(ActivityLog)
        .where(
            ActivityLog.raw_llm_response.is_not(None),
            ActivityLog.raw_response_expires_at.is_not(None),
            ActivityLog.raw_response_expires_at < now,
        )
        .values(raw_llm_response=None, raw_response_expires_at=None)
    )
    return result.rowcount or 0


async def _purge_expired_raw_payloads() -> None:
    """Session wrapper around cleanup_expired_raw_responses for the scheduler loop."""
    async with async_session_factory() as db:
        cleared = await cleanup_expired_raw_responses(db)
        if cleared:
            logger.info(f"TTL purge: cleared raw payloads from {cleared} activity logs")
        await db.commit()


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    """Loop that checks every minute whether it's time to run analysis."""
    analysis_hour, analysis_minute = _parse_time(settings.tg_auto_analysis_time)
    analysis_tz = resolve_tz(settings.tg_auto_analysis_tz)
    logger.info(
        f"Auto-analysis scheduler started (runs daily at {analysis_hour:02d}:{analysis_minute:02d} "
        f"{settings.tg_auto_analysis_tz})"
    )

    last_run_date: date | None = None
    last_purge: datetime | None = None

    while not stop_event.is_set():
        try:
            now = datetime.now(analysis_tz)

            # Run once per day at the configured hour:minute
            if now.hour == analysis_hour and now.minute == analysis_minute and last_run_date != now.date():
                logger.info("Auto-analysis: triggering daily run")
                await _run_auto_analysis()
                last_run_date = now.date()

            # Purge expired raw payloads every 6 hours (cheap, idempotent)
            if last_purge is None or (now - last_purge).total_seconds() > 6 * 3600:
                await _purge_expired_raw_payloads()
                last_purge = now

            # Wait until next check
            await asyncio.wait_for(stop_event.wait(), timeout=_check_interval_seconds)
        except TimeoutError:
            pass  # Normal — just check the time again
        except Exception:
            logger.exception("Auto-analysis scheduler error")
            await asyncio.sleep(10)  # Back off on error


def _parse_time(time_str: str) -> tuple[int, int]:
    """Parse 'HH:MM' string into (hour, minute)."""
    parts = time_str.strip().split(":")
    return int(parts[0]) % 24, int(parts[1]) % 60


_scheduler_stop_event: asyncio.Event | None = None
_scheduler_task: asyncio.Task | None = None


async def start_auto_analysis() -> None:
    """Start the background scheduler. Called at app startup."""
    global _scheduler_stop_event, _scheduler_task

    if _scheduler_task is not None:
        return  # Already running

    _scheduler_stop_event = asyncio.Event()
    _scheduler_task = asyncio.create_task(_scheduler_loop(_scheduler_stop_event))
    logger.info("Auto-analysis background task created")


async def stop_auto_analysis() -> None:
    """Stop the background scheduler. Called at app shutdown."""
    global _scheduler_stop_event, _scheduler_task

    if _scheduler_stop_event:
        _scheduler_stop_event.set()

    if _scheduler_task:
        _scheduler_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _scheduler_task
        _scheduler_task = None

    logger.info("Auto-analysis scheduler stopped")
