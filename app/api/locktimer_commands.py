"""LockTimer command API — C5 execution + C3 draft management + C4 horizon + templates.

POST .../sessions/{id}/start            — draft → active
POST .../sessions/{id}/safety-stop      — active → safety_stopped
POST .../sessions/{id}/validate         — pre-start validation (JSON)
POST .../sessions/{id}/extend-horizon   — materialize future days
POST .../sessions/{id}/save-template    — save draft as template
POST .../templates/{id}/instantiate     — create draft from template
POST .../templates/{id}/archive         — archive template
POST .../slot-occurrences/{id}/open     — pending → open
POST .../slot-occurrences/{id}/close    — open → closed
POST .../task-occurrences/{id}/reveal   — scheduled → visible
POST .../task-occurrences/{id}/complete — submitted → completed
POST .../task-occurrences/{id}/skip     — scheduled/visible → skipped
POST .../sessions/{id}/slot-rules       — add slot rule (draft)
POST .../sessions/{id}/task-rules       — add task rule (draft)
POST .../sessions/{id}/slot-rules/{rule_id}/delete — delete slot rule (draft)
POST .../sessions/{id}/task-rules/{rule_id}/delete — delete task rule (draft)
POST .../sessions/{id}/update           — update draft metadata
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.api.responses import action_response
from app.database import get_db
from app.locktimer import enums as e
from app.locktimer.repositories import get_session
from app.locktimer.services.execution import (
    add_medication_task_rule,
    add_slot_rule,
    add_task_rule,
    close_slot,
    complete_task,
    delete_slot_rule,
    delete_task_rule,
    list_tag_violations,
    lookup_tag,
    open_slot,
    reorder_rules,
    reveal_task,
    safety_stop,
    skip_task,
    start_session,
    update_draft,
    verify_tag,
)
from app.locktimer.services.extras import (
    archive_template,
    extend_horizon,
    instantiate_template,
    reorder_templates,
    save_template,
    validate_session,
)
from app.models.locktimer import (
    LockSlotOccurrence,
    LockSlotRule,
    LockTaskOccurrence,
    LockTaskRule,
)
from app.models.user import User

router = APIRouter(prefix="/api/v2/locktimer", tags=["locktimer-commands"])

logger = logging.getLogger(__name__)

# Sentinel for optional form fields: distinguishes "absent" from "empty".
_UNSET = "__unset__"


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

    return action_response(
        request,
        json_body={"status": "started", "session_id": str(session_id)},
        redirect_url=f"/locktimer/sessions/{session_id}",
    )


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

    return action_response(
        request,
        json_body={"status": "safety_stopped", "session_id": str(session_id)},
        redirect_url=f"/locktimer/sessions/{session_id}",
    )


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

    return action_response(
        request,
        json_body={"status": "opened", "occurrence_id": str(occurrence_id), "session_id": str(occ.session_id)},
        redirect_url=f"/locktimer/sessions/{occ.session_id}",
    )


@router.post("/slot-occurrences/{occurrence_id}/close")
async def api_close_slot(
    occurrence_id: uuid.UUID,
    request: Request,
    tag_number: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Close an open slot (open → closed). Optional tag_number for numbered seal."""
    occ = await db.get(LockSlotOccurrence, occurrence_id)
    if occ is None:
        raise HTTPException(404, "Slot occurrence not found")

    session = await get_session(db, occ.session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Slot occurrence not found")

    try:
        await close_slot(db, occurrence=occ, owner_id=current_user.id, tag_number=tag_number)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc

    # Q14: report the actual penalty result (JSON-first, ADR-065).
    from app.locktimer.services.execution import get_penalty_for_source, serialize_penalty_event

    penalty = await get_penalty_for_source(
        db,
        source_kind="slot_occurrence",
        source_id=occ.id,
    )
    # Шаг 14b: если окно было для плановой активности (journal_auto), draft-запись
    # журнала ждёт заполнения деталей при закрытии — сообщаем клиенту.
    journal_pending = None
    try:
        from app.api.journal import get_pending_slot_entry

        pending = await get_pending_slot_entry(
            db,
            user_id=current_user.id,
            slot_occurrence_id=occ.id,
        )
        if pending is not None:
            journal_pending = {
                "entry_id": str(pending.id),
                "url": "/journal",
            }
    except Exception as exc:  # journal not deployed — не блокируем закрытие
        logger.warning("journal pending lookup skipped for slot %s: %s", occ.id, exc)
    return JSONResponse(
        {
            "status": "closed",
            "session_id": str(occ.session_id),
            "penalty": serialize_penalty_event(penalty),
            "journal_pending": journal_pending,
        }
    )


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

    return action_response(
        request,
        json_body={"status": "revealed", "occurrence_id": str(occurrence_id), "session_id": str(occ.session_id)},
        redirect_url=f"/locktimer/sessions/{occ.session_id}",
    )


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

    return action_response(
        request,
        json_body={"status": "completed", "occurrence_id": str(occurrence_id), "session_id": str(occ.session_id)},
        redirect_url=f"/locktimer/sessions/{occ.session_id}",
    )


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

    # Q14: report the actual penalty result (JSON-first, ADR-065).
    from app.locktimer.services.execution import get_penalty_for_source, serialize_penalty_event

    penalty = await get_penalty_for_source(
        db,
        source_kind="task_occurrence",
        source_id=occ.id,
    )
    return JSONResponse(
        {
            "status": "skipped",
            "session_id": str(occ.session_id),
            "penalty": serialize_penalty_event(penalty),
        }
    )


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
    max_late_seconds: int = Form(default=3600),
    journal_auto: bool = Form(default=False),
    catalog_item_id: str = Form(default=""),
    care_product_ids: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a slot rule to a draft session.

    ``max_late_seconds`` sets the late-open eligibility window (0 = on-time
    only). Default 3600s keeps the UI ``allow_late_open`` checkbox usable —
    without it the eligible window collapses to [planned_open, planned_open]
    and no real-time request can ever open the slot.

    ``journal_auto`` (Шаг 14b): окно для плановой сексуальной активности —
    при открытии авто-создаётся draft-запись Sexual Journal, детали пользователь
    обязан внести при закрытии.
    """
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

    # Сквозной каталог (ADR-091): причина/цель окна (системная или своя запись).
    catalog_uuid = None
    if catalog_item_id.strip():
        from sqlalchemy import select

        from app.models.catalog import ActivityCatalogItem

        try:
            cid = uuid.UUID(catalog_item_id.strip())
        except ValueError as exc:
            raise HTTPException(422, "Invalid catalog_item_id format") from exc
        item = (
            await db.execute(
                select(ActivityCatalogItem).where(
                    ActivityCatalogItem.id == cid,
                    ActivityCatalogItem.owner_id.is_(None) | (ActivityCatalogItem.owner_id == current_user.id),
                )
            )
        ).scalar_one_or_none()
        if item is None:
            raise HTTPException(400, "Catalog item not found")
        catalog_uuid = cid

    # Средства/косметика (ADR-092/094): какие средства нужно использовать
    # в этом окне. Мягкие ссылки на care_products по ID — валидируем
    # принадлежность пользователю.
    care_uuids: list[uuid.UUID] | None = None
    if care_product_ids.strip():
        from sqlalchemy import select

        from app.models.care import CareProduct

        raw = [x.strip() for x in care_product_ids.split(",") if x.strip()]
        try:
            parsed = [uuid.UUID(x) for x in raw]
        except ValueError as exc:
            raise HTTPException(422, "Invalid care_product_ids format") from exc
        if parsed:
            rows = (
                (
                    await db.execute(
                        select(CareProduct.id).where(
                            CareProduct.id.in_(parsed),
                            CareProduct.user_id == current_user.id,
                        )
                    )
                )
                .scalars()
                .all()
            )
            if len(rows) != len(set(parsed)):
                raise HTTPException(400, "One or more care products not found")
            # JSON-колонка: храним строки (UUID не сериализуется в JSON)
            care_uuids = [str(x) for x in parsed]

    await add_slot_rule(
        db,
        session_id=session_id,
        name=name,
        rule_type=rule_type,
        schedule=schedule,
        duration_seconds=duration_seconds,
        allow_late_open=allow_late_open,
        max_late_seconds=max_late_seconds,
        journal_auto=journal_auto,
        catalog_item_id=catalog_uuid,
        care_product_ids=care_uuids,
    )

    return action_response(
        request,
        json_body={"status": "created", "session_id": str(session_id)},
        redirect_url=f"/locktimer/sessions/{session_id}",
    )


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

    return action_response(
        request,
        json_body={"status": "created", "session_id": str(session_id)},
        redirect_url=f"/locktimer/sessions/{session_id}",
    )


@router.post("/sessions/{session_id}/medication-task-rules")
async def api_add_medication_task_rule(
    session_id: uuid.UUID,
    request: Request,
    med_schedule_id: uuid.UUID = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add a medication relief task rule to a draft session (ADR-085).

    Relief-only: the generated task rule has no penalty policy, so a skipped
    medication dose never triggers a penalty. The rule is marked with
    availability_policy relief=medication for honest UI.
    """
    session = await get_session(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.state != e.SESSION_DRAFT:
        raise HTTPException(400, "Only draft sessions can be edited")

    try:
        await add_medication_task_rule(
            db,
            session_id=session_id,
            med_schedule_id=med_schedule_id,
            owner_id=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return action_response(
        request,
        json_body={"status": "created", "session_id": str(session_id)},
        redirect_url=f"/locktimer/sessions/{session_id}",
    )


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
    return action_response(
        request,
        json_body={"status": "deleted", "rule_id": str(rule_id), "session_id": str(session_id)},
        redirect_url=f"/locktimer/sessions/{session_id}",
    )


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
    return action_response(
        request,
        json_body={"status": "deleted", "rule_id": str(rule_id), "session_id": str(session_id)},
        redirect_url=f"/locktimer/sessions/{session_id}",
    )


@router.post("/sessions/{session_id}/slot-rules/reorder")
async def api_reorder_slot_rules(
    session_id: uuid.UUID,
    request: Request,
    rule_ids: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reorder slot rules of a draft session. Expects comma-separated rule ids."""
    parsed = [uuid.UUID(x.strip()) for x in rule_ids.split(",") if x.strip()]
    try:
        await reorder_rules(
            db,
            session_id=session_id,
            owner_id=current_user.id,
            kind="slot",
            rule_ids=parsed,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return action_response(
        request,
        json_body={"status": "reordered", "session_id": str(session_id)},
        redirect_url=f"/locktimer/sessions/{session_id}",
    )


@router.post("/sessions/{session_id}/task-rules/reorder")
async def api_reorder_task_rules(
    session_id: uuid.UUID,
    request: Request,
    rule_ids: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reorder task rules of a draft session. Expects comma-separated rule ids."""
    parsed = [uuid.UUID(x.strip()) for x in rule_ids.split(",") if x.strip()]
    try:
        await reorder_rules(
            db,
            session_id=session_id,
            owner_id=current_user.id,
            kind="task",
            rule_ids=parsed,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return action_response(
        request,
        json_body={"status": "reordered", "session_id": str(session_id)},
        redirect_url=f"/locktimer/sessions/{session_id}",
    )


@router.post("/sessions/{session_id}/update")
async def api_update_draft(
    session_id: uuid.UUID,
    request: Request,
    duration_type: str | None = Form(default=None),
    timezone: str | None = Form(default=None),
    merge_gap_seconds: int | None = Form(default=None),
    device_id: str = Form(default=_UNSET),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update draft session metadata (duration, tz, merge gap, device)."""
    session = await get_session(db, session_id, current_user.id)
    if session is None:
        raise HTTPException(404, "Session not found")
    if session.state != e.SESSION_DRAFT:
        raise HTTPException(400, "Only draft sessions can be edited")

    print("DBG device_id raw ->", repr(device_id), flush=True)
    fields: dict = {}
    if duration_type:
        fields["duration_type"] = duration_type
    if timezone:
        fields["timezone"] = timezone
    if merge_gap_seconds is not None:
        fields["merge_gap_seconds"] = merge_gap_seconds
    # device_id: absent → no change; "__none__" (UI sentinel) → unbind;
    # otherwise must be a UUID. NOTE: FastAPI maps empty form values to the
    # parameter default, so "" never reaches this code.
    if device_id != _UNSET:
        device_id = device_id.strip()
        if device_id == "__none__":
            fields["device_id"] = None
        else:
            try:
                fields["device_id"] = uuid.UUID(device_id)
            except ValueError as exc:
                raise HTTPException(422, "Invalid device_id format") from exc

    try:
        await update_draft(db, session, **fields)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return action_response(
        request,
        json_body={"status": "updated", "session_id": str(session_id)},
        redirect_url=f"/locktimer/sessions/{session_id}",
    )


# ---------------------------------------------------------------------------
# Validation + Horizon extension
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/validate")
async def api_validate_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run pre-start validation (returns JSON)."""
    from fastapi.responses import JSONResponse

    result = await validate_session(db, session_id, current_user.id)
    return JSONResponse(result)


@router.post("/sessions/{session_id}/extend-horizon")
async def api_extend_horizon(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Extend occurrence horizon for an active session."""
    from fastapi.responses import JSONResponse

    try:
        result = await extend_horizon(db, session_id, current_user.id)
        return JSONResponse(result)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


# ---------------------------------------------------------------------------
# Template management
# ---------------------------------------------------------------------------


@router.post("/sessions/{session_id}/save-template")
async def api_save_template(
    session_id: uuid.UUID,
    request: Request,
    name: str = Form(...),
    description: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save current draft session as a reusable template."""
    try:
        await save_template(
            db,
            session_id=session_id,
            owner_id=current_user.id,
            name=name,
            description=description,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return action_response(
        request,
        json_body={"status": "saved", "session_id": str(session_id)},
        redirect_url="/locktimer/templates",
    )


@router.post("/templates/{template_id}/instantiate")
async def api_instantiate_template(
    template_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new draft session from a template."""
    try:
        session = await instantiate_template(db, template_id=template_id, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return action_response(
        request,
        json_body={"status": "instantiated", "session_id": str(session.id)},
        redirect_url=f"/locktimer/sessions/{session.id}",
    )


@router.post("/slot-occurrences/{occurrence_id}/verify-tag")
async def api_verify_tag(
    occurrence_id: uuid.UUID,
    request: Request,
    tag_number: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Verify a tag number against the stored close_tag_number."""
    occ = await db.get(LockSlotOccurrence, occurrence_id)
    if occ is None:
        raise HTTPException(404, "Slot occurrence not found")

    try:
        result = await verify_tag(db, occurrence=occ, provided_tag=tag_number, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    from fastapi.responses import JSONResponse

    return JSONResponse(result)


@router.get("/tag-violations/{session_id}")
async def api_tag_violations(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List tag violations for a session (JSON)."""
    from fastapi.responses import JSONResponse

    try:
        violations = await list_tag_violations(db, session_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

    return JSONResponse(
        [
            {
                "id": str(v.id),
                "slot_occurrence_id": str(v.slot_occurrence_id),
                "expected_tag": v.expected_tag,
                "provided_tag": v.provided_tag,
                "reason": v.reason,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in violations
        ]
    )


@router.get("/tag-lookup/{session_id}")
async def api_tag_lookup(
    session_id: uuid.UUID,
    tag_number: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Look up which slot was closed with a given tag number."""
    from fastapi.responses import JSONResponse

    try:
        result = await lookup_tag(db, tag_number=tag_number, session_id=session_id, owner_id=current_user.id)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc

    if result is None:
        raise HTTPException(404, f"No slot found with tag '{tag_number}'")

    return JSONResponse(result)


@router.post("/templates/{template_id}/archive")
async def api_archive_template(
    template_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Archive a template."""
    try:
        await archive_template(db, template_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    return action_response(
        request,
        json_body={"status": "archived", "template_id": str(template_id)},
        redirect_url="/locktimer/templates",
    )


@router.post("/templates/reorder")
async def api_reorder_templates(
    request: Request,
    template_ids: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reorder the owner's templates. Expects comma-separated template ids."""
    parsed = [uuid.UUID(x.strip()) for x in template_ids.split(",") if x.strip()]
    try:
        await reorder_templates(db, owner_id=current_user.id, template_ids=parsed)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return action_response(
        request,
        json_body={"status": "reordered"},
        redirect_url="/locktimer/templates",
    )
