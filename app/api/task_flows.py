"""Task status transition API (ADR-040).

POST /api/v2/tasks/{task_id}/transition — move a task to any legal status
with an audit record. Rewards/penalties follow the status machine:
- → completed: full reward (on_task_completed)
- → stopped: penalty (on_task_interrupted, ADR-029)
- other statuses (skipped/cancelled/substituted/not_applicable/
  review_needed/in_progress/draft/partially_completed): no reward, no
  penalty — per ADR-038 (cancelled/skipped before start are free).

Also exposes the transition graph so the UI can render quick actions.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.gamification.handler import on_task_completed, on_task_interrupted
from app.models.activity_log import ActivityLog
from app.models.task_status import (
    COMPLETED,
    PARTIALLY_COMPLETED,
    STATUS_TRANSITIONS,
    STOPPED,
    TASK_STATUSES,
    is_valid_status,
)
from app.models.user import User
from app.security import transition_once

router = APIRouter(prefix="/api/v2/tasks", tags=["task-flows"])


class TransitionIn(BaseModel):
    to_status: str
    comment: str | None = None
    # ADR-041: actual parameters recorded when completing a task
    actual_parameters: dict | None = None


async def _get_owned_task(db: AsyncSession, task_id: uuid.UUID, user: User) -> ActivityLog:
    result = await db.execute(select(ActivityLog).where(ActivityLog.id == task_id, ActivityLog.user_id == user.id))
    log = result.scalar_one_or_none()
    if log is None:
        raise HTTPException(404, "Task not found")
    return log


@router.get("/transitions")
async def get_transition_graph(user: User = Depends(get_current_user)):
    """Return the full status machine graph (for UI quick actions)."""
    return {
        "statuses": list(TASK_STATUSES),
        "transitions": {src: sorted(dst) for src, dst in STATUS_TRANSITIONS.items()},
    }


@router.post("/{task_id}/transition")
async def transition_task(
    task_id: uuid.UUID,
    data: TransitionIn,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Transition a task to a legal status, with audit + reward/penalty hooks."""
    if not is_valid_status(data.to_status):
        raise HTTPException(400, f"Unknown status: {data.to_status}")

    log = await _get_owned_task(db, task_id, user)

    async def _reward_hook(session, uid, task, previous, to_status):
        return await on_task_completed(session, uid, task)

    async def _penalty_hook(session, uid, task, previous, to_status):
        return await on_task_interrupted(session, uid, task)

    hook = None
    if data.to_status == COMPLETED:
        hook = _reward_hook
    elif data.to_status == STOPPED:
        hook = _penalty_hook

    # ADR-041/036: record actual parameters + completion comment on finishing states
    if data.to_status in (COMPLETED, PARTIALLY_COMPLETED):
        if data.actual_parameters is not None:
            log.actual_parameters = data.actual_parameters
        if data.comment:
            log.completion_comment = data.comment
        log.completed_at = datetime.now(UTC)
        db.add(log)

    result = await transition_once(db, log, user, data.to_status, comment=data.comment, on_transition_fn=hook)
    await db.commit()
    return result
