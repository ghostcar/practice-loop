"""Background scheduler for end-of-day training analysis.

Runs via asyncio loop — no extra dependencies (no APScheduler needed).
At the configured time (tg_auto_analysis_time), scans for unanalyzed training
days and runs analyze_training_day for each.
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

logger = logging.getLogger(__name__)

_check_interval_seconds = 60  # Check every minute


async def _run_auto_analysis() -> None:
    """Scan for unanalyzed training days and run analysis for each."""
    today = date.today()

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

                await analyze_training_day(
                    db=db,
                    training_day=td,
                    llm_config=config,
                    locale="en",
                )
                await db.commit()
                logger.info(
                    f"Auto-analysis: completed for user {td.user_id}, day {td.target_date}"
                )
            except Exception:
                logger.exception(
                    f"Auto-analysis: failed for user {td.user_id}, day {td.target_date}"
                )
                await db.rollback()


async def _scheduler_loop(stop_event: asyncio.Event) -> None:
    """Loop that checks every minute whether it's time to run analysis."""
    analysis_hour, analysis_minute = _parse_time(settings.tg_auto_analysis_time)
    logger.info(
        f"Auto-analysis scheduler started (runs daily at {analysis_hour:02d}:{analysis_minute:02d} UTC)"
    )

    last_run_date: date | None = None

    while not stop_event.is_set():
        try:
            now = datetime.now(UTC)

            # Run once per day at the configured hour:minute
            if (now.hour == analysis_hour and now.minute == analysis_minute
                    and last_run_date != now.date()):
                    logger.info("Auto-analysis: triggering daily run")
                    await _run_auto_analysis()
                    last_run_date = now.date()

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
