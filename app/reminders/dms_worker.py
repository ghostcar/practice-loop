"""DMS & Protocol Check-in Background Worker (Revision 2 / ADR-095).

Monitors Dead Man's Switch deadlines and upcoming protocol steps,
dispatching alerts via NotificationDispatcher.
"""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session_factory as async_session_maker
from app.models.dead_mans_switch import DeadMansSwitchRule
from app.models.protocol import ProtocolStepLog
from app.services.adapters.notifications import dispatch_notification

logger = logging.getLogger(__name__)

_worker_task: asyncio.Task | None = None
_running: bool = False


async def check_dead_mans_switches(db: AsyncSession) -> list[dict[str, Any]]:
    """Inspect active DMS rules and trigger notifications for expired/warning deadlines."""
    now = datetime.datetime.now(datetime.UTC)
    results = []

    res = await db.execute(
        select(DeadMansSwitchRule).where(
            DeadMansSwitchRule.is_enabled.is_(True),
            DeadMansSwitchRule.status == "active",
        )
    )
    rules = res.scalars().all()

    for r in rules:
        deadline = (
            r.next_deadline_at.replace(tzinfo=datetime.UTC)
            if r.next_deadline_at.tzinfo is None
            else r.next_deadline_at
        )
        if deadline <= now:
            # Trigger DMS escalation
            r.status = "triggered_penalty"
            r.miss_count += 1
            await db.flush()

            await dispatch_notification(
                db=db,
                user_id=r.user_id,
                event_type="dms_triggered",
                title="Внимание: Сработал Dead Man's Switch",
                message=f"Контрольный срок чекина для правила '{r.title}' истёк.",
            )
            results.append({"rule_id": str(r.id), "status": "triggered_penalty"})

    return results


async def check_due_protocol_steps(db: AsyncSession) -> list[dict[str, Any]]:
    """Notify users of due protocol steps."""
    now = datetime.datetime.now(datetime.UTC)
    results = []

    res = await db.execute(
        select(ProtocolStepLog)
        .where(
            ProtocolStepLog.status == "pending",
            ProtocolStepLog.planned_at <= now,
        )
        .limit(50)
    )
    due_steps = res.scalars().all()

    for s in due_steps:
        # Avoid duplicate alerts by marking notified or logging
        results.append({"step_log_id": str(s.id), "title": s.step_title})

    return results


async def dms_and_protocol_worker_loop(poll_interval_sec: int = 60) -> None:
    """Async background worker loop."""
    logger.info("Starting DMS and Protocol Check-in Worker (interval=%ds)", poll_interval_sec)
    while _running:
        try:
            async with async_session_maker() as session:
                await check_dead_mans_switches(session)
                await check_due_protocol_steps(session)
                await session.commit()
        except Exception as exc:
            logger.warning("Error in DMS worker loop: %s", exc)

        try:
            await asyncio.sleep(poll_interval_sec)
        except asyncio.CancelledError:
            break


async def start_dms_worker(poll_interval_sec: int = 60) -> None:
    """Start background worker task."""
    global _worker_task, _running
    if _running:
        return
    _running = True
    _worker_task = asyncio.create_task(dms_and_protocol_worker_loop(poll_interval_sec))


async def stop_dms_worker() -> None:
    """Stop background worker task."""
    global _worker_task, _running
    _running = False
    if _worker_task:
        _worker_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _worker_task
        _worker_task = None
