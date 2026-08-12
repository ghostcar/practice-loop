"""LockTimer command API — C5 execution + C3 draft management.

POST /api/v1/locktimer/sessions/{id}/start            — draft → active
POST /api/v1/locktimer/sessions/{id}/safety-stop      — active → safety_stopped
POST /api/v1/locktimer/slot-occurrences/{id}/open     — pending → open
POST /api/v1/locktimer/slot-occurrences/{id}/close    — open → closed
POST /api/v1/locktimer/task-occurrences/{id}/reveal   — scheduled → visible
POST /api/v1/locktimer/task-occurrences/{id}/complete — submitted → completed
POST /api/v1/locktimer/task-occurrences/{id}/skip     — scheduled/visible → skipped
POST /api/v1/locktimer/sessions/{id}/slot-rules       — add slot rule (draft)
POST /api/v1/locktimer/sessions/{id}/task-rules       — add task rule (draft)
DELETE /api/v1/locktimer/sessions/{id}/slot-rules/{rule_id} — delete slot rule (draft)
DELETE /api/v1/locktimer/sessions/{id}/task-rules/{rule_id} — delete task rule (draft)
PATCH /api/v1/locktimer/sessions/{id}                 — update draft metadata
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.locktimer import enums as e
from app.locktimer.repositories import get_session
from app.locktimer.services.execution import (
    add_slot_rule,
    add_task_rule,
    close_slot,
    complete_task,
    delete_slot_rule,
    delete_task_rule,
    open_slot,
    reveal_task,
    safety_stop,
    skip_task,
    start_session,
    update_draft,
)
from app.models.locktimer import (
    LockSlotOccurrence,
    LockSlotRule,
    LockTaskOccurrence,
    LockTaskRule,
)
from app.models.user import User

router = APIRouter(prefix="/api/v1/locktimer", tags=["locktimer-commands"])


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Session lifecycle
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/start")
async def api_start_session(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a draft session (draft → active)."""
    try:
        await start_session(db, session_id=session_id, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    return RedirectResponse(f"/locktimer/sessions/{session_id}", status_code=303)


@router.post("/sessions/{session_id}/safety-stop")
async def api_safety_stop(
    session_id: uuid.UUID,
    request: Request,
    reason_code: str = Form(default="user_requested"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Safety-stop an active session (active → safety_stopped)."""
    try:
        await safety_stop(db, session_id=session_id, owner_id=current_user.id, reason_code=reason_code)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    return RedirectResponse(f"/locktimer/sessions/{session_id}", status_code=303)


# ---------------------------------------------------------------------------
# Slot execution
# ---------------------------------------------------------------------------


@router.post("/slot-occurrences/{occurrence_id}/open")
async def api_open_slot(
    occurrence_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Open a slot occurrence (pending → open)."""
    occ = await db.get(LockSlotOccurrence, occurrence_id)
    if occ is None:
        raise HTTPException(404, "Slot occurrence not found")

    # Verify ownership via session
    session = await get_session(db, occ.session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Slot occurrence not found")

    try:
        await open_slot(db, occurrence=occ, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    return RedirectResponse(f"/locktimer/sessions/{occ.session_id}", status_code=303)


@router.post("/slot-occurrences/{occurrence_id}/close")
async def api_close_slot(
    occurrence_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Close an open slot (open → closed)."""
    occ = await db.get(LockSlotOccurrence, occurrence_id)
    if occ is None:
        raise HTTPException(404, "Slot occurrence not found")

    session = await get_session(db, occ.session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Slot occurrence not found")

    try:
        await close_slot(db, occurrence=occ, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    return RedirectResponse(f"/locktimer/sessions/{occ.session_id}", status_code=303)


# ---------------------------------------------------------------------------
# Task execution
# ---------------------------------------------------------------------------


@router.post("/task-occurrences/{occurrence_id}/reveal")
async def api_reveal_task(
    occurrence_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reveal a hidden task (scheduled → visible)."""
    occ = await db.get(LockTaskOccurrence, occurrence_id)
    if occ is None:
        raise HTTPException(404, "Task occurrence not found")

    session = await get_session(db, occ.session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Task occurrence not found")

    try:
        await reveal_task(db, occurrence=occ, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    return RedirectResponse(f"/locktimer/sessions/{occ.session_id}", status_code=303)


@router.post("/task-occurrences/{occurrence_id}/complete")
async def api_complete_task(
    occurrence_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Complete a submitted task (submitted → completed)."""
    occ = await db.get(LockTaskOccurrence, occurrence_id)
    if occ is None:
        raise HTTPException(404, "Task occurrence not found")

    session = await get_session(db, occ.session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Task occurrence not found")

    # If visible (not yet submitted), auto-submit then complete
    try:
        if occ.state == e.TASK_VISIBLE:
            from app.locktimer.services.execution import submit_task

            occ = await submit_task(db, occurrence=occ, owner_id=current_user.id)
        await complete_task(db, occurrence=occ, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    return RedirectResponse(f"/locktimer/sessions/{occ.session_id}", status_code=303)


@router.post("/task-occurrences/{occurrence_id}/skip")
async def api_skip_task(
    occurrence_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Skip a task (scheduled/visible → skipped)."""
    occ = await db.get(LockTaskOccurrence, occurrence_id)
    if occ is None:
        raise HTTPException(404, "Task occurrence not found")

    session = await get_session(db, occ.session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Task occurrence not found")

    try:
        await skip_task(db, occurrence=occ, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    return RedirectResponse(f"/locktimer/sessions/{occ.session_id}", status_code=303)


# ---------------------------------------------------------------------------
# Draft rule management
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/slot-rules")
async def api_add_slot_rule(
    session_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    rule_type: str = Form(default="every_n_days"),
    schedule_json: str = Form(default="{}"),
    duration_seconds: int = Form(default=3600),
    allow_late_open: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a slot rule to a draft session."""
    import json

    session = await get_session(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.state != e.SESSION_DRAFT:
        raise HTTPException(400, "Only draft sessions can be edited")

    try:
        schedule = json.loads(schedule_json)
    except json.JSONDecodeError:
        schedule = {}

    await add_slot_rule(
        db,
        session_id=session_id,
        name=name,
        rule_type=rule_type,
        schedule=schedule,
        duration_seconds=duration_seconds,
        allow_late_open=allow_late_open,
    )

    return RedirectResponse(f"/locktimer/sessions/{session_id}", status_code=303)


@router.post("/sessions/{session_id}/task-rules")
async def api_add_task_rule(
    session_id: uuid.UUID,
    request: Request,
    title: str = Form(...),
    schedule_type: str = Form(default="daily"),
    schedule_json: str = Form(default="{}"),
    due_window_seconds: int = Form(default=3600),
    requires_report: bool = Form(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a task rule to a draft session."""
    import json

    session = await get_session(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.state != e.SESSION_DRAFT:
        raise HTTPException(400, "Only draft sessions can be edited")

    try:
        schedule = json.loads(schedule_json)
    except json.JSONDecodeError:
        schedule = {}

    await add_task_rule(
        db,
        session_id=session_id,
        title=title,
        schedule_type=schedule_type,
        schedule=schedule,
        due_window_seconds=due_window_seconds,
        requires_report=requires_report,
    )

    return RedirectResponse(f"/locktimer/sessions/{session_id}", status_code=303)


@router.post("/sessions/{session_id}/slot-rules/{rule_id}/delete")
async def api_delete_slot_rule(
    session_id: uuid.UUID,
    rule_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a slot rule from a draft session."""
    session = await get_session(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.state != e.SESSION_DRAFT:
        raise HTTPException(400, "Only draft sessions can be edited")

    rule = await db.get(LockSlotRule, rule_id)
    if rule is None or rule.session_id != session_id:
        raise HTTPException(404, "Slot rule not found")

    await delete_slot_rule(db, rule)
    return RedirectResponse(f"/locktimer/sessions/{session_id}", status_code=303)


@router.post("/sessions/{session_id}/task-rules/{rule_id}/delete")
async def api_delete_task_rule(
    session_id: uuid.UUID,
    rule_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a task rule from a draft session."""
    session = await get_session(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.state != e.SESSION_DRAFT:
        raise HTTPException(400, "Only draft sessions can be edited")

    rule = await db.get(LockTaskRule, rule_id)
    if rule is None or rule.session_id != session_id:
        raise HTTPException(404, "Task rule not found")

    await delete_task_rule(db, rule)
    return RedirectResponse(f"/locktimer/sessions/{session_id}", status_code=303)


@router.post("/sessions/{session_id}/update")
async def api_update_draft(
    session_id: uuid.UUID,
    request: Request,
    duration_type: str | None = Form(default=None),
    timezone: str | None = Form(default=None),
    merge_gap_seconds: int | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update draft session metadata."""
    session = await get_session(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.state != e.SESSION_DRAFT:
        raise HTTPException(400, "Only draft sessions can be edited")

    fields = {}
    if duration_type:
        fields["duration_type"] = duration_type
    if timezone:
        fields["timezone"] = timezone
    if merge_gap_seconds is not None:
        fields["merge_gap_seconds"] = merge_gap_seconds

    await update_draft(db, session, **fields)
    return RedirectResponse(f"/locktimer/sessions/{session_id}", status_code=303)
