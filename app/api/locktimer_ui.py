"""LockTimer SSR pages — C8.

GET  /locktimer                     — overview (active session, drafts, history)
POST /locktimer/new                 — create draft session, redirect to detail
GET  /locktimer/sessions/{id}       — session detail (rules, occurrences, timeline)
GET  /locktimer/templates           — saved templates
GET  /locktimer/tag-violations/{id} — tag violation audit
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale
from app.locktimer import enums as e
from app.locktimer.repositories import (
    get_active_session,
    get_session,
    get_weekly_compliance,
    list_sessions,
    list_sessions_by_date_range,
    list_slot_occurrences,
    list_slot_rules,
    list_task_occurrences,
    list_task_rules,
)
from app.locktimer.services.extras import list_templates
from app.models.locktimer import (
    LockLlmProposal,
    LockSession,
    LockSlotOccurrence,
    LockTaskOccurrence,
)
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(prefix="/locktimer", tags=["locktimer-pages"])


def _check_owner_allowlist(user: User) -> None:
    """Gate: if owner allowlist is set, only listed emails may access LockTimer."""
    allowlist = settings.locktimer_owner_allowlist.strip()
    if not allowlist:
        return  # no restriction
    allowed = {e.strip().lower() for e in allowlist.split(",") if e.strip()}
    if (user.email or "").lower() not in allowed:
        from fastapi import HTTPException

        raise HTTPException(403, "LockTimer Core is in restricted pilot — you are not on the allowlist.")


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# POST /locktimer/new — create draft session
# ---------------------------------------------------------------------------


@router.post("/new")
async def locktimer_create_draft(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_owner_allowlist(current_user)

    now = _now()
    seed = secrets.token_hex(16)
    session = LockSession(
        owner_id=current_user.id,
        state=e.SESSION_DRAFT,
        duration_type="duration_from_start",
        timezone=getattr(current_user, "timezone", "UTC") or "UTC",
        random_seed_encrypted=seed,
        random_seed_commitment=seed,
        created_at=now,
        updated_at=now,
    )
    db.add(session)
    await db.flush()

    return RedirectResponse(f"/locktimer/sessions/{session.id}", status_code=303)


# ---------------------------------------------------------------------------
# GET /locktimer — overview
# ---------------------------------------------------------------------------


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def locktimer_overview(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_owner_allowlist(current_user)

    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)

    active = await get_active_session(db, current_user.id)
    drafts_result = await db.execute(
        select(LockSession)
        .where(LockSession.owner_id == current_user.id, LockSession.state == e.SESSION_DRAFT)
        .order_by(LockSession.updated_at.desc())
        .limit(5)
    )
    drafts = list(drafts_result.scalars().all())

    recent = await list_sessions(db, current_user.id, limit=10)

    # Gather occurrences for active session
    active_slots: list = []
    active_tasks: list = []
    if active:
        slot_occs = await list_slot_occurrences(db, active.id, limit=20)
        active_slots = [_serialize_slot_occ(o, t) for o in slot_occs]

        task_occs = await list_task_occurrences(db, active.id, limit=20)
        active_tasks = [_serialize_task_occ(o, t) for o in task_occs]

    # Compliance snapshot (current week)
    compliance = await get_weekly_compliance(db, current_user.id, weeks=1)
    compliance_snapshot = None
    if compliance:
        cw = compliance[0]
        slot_pct = round(cw["slots_closed"] / cw["slots_total"] * 100) if cw["slots_total"] > 0 else 0
        task_pct = round(cw["tasks_completed"] / cw["tasks_total"] * 100) if cw["tasks_total"] > 0 else 0
        # Calculate streak: count consecutive weeks with >50% slot+task compliance
        all_weeks = await get_weekly_compliance(db, current_user.id, weeks=12)
        streak = 0
        for w in all_weeks:
            ws = round(w["slots_closed"] / w["slots_total"] * 100) if w["slots_total"] > 0 else 100
            wt = round(w["tasks_completed"] / w["tasks_total"] * 100) if w["tasks_total"] > 0 else 100
            if (ws + wt) >= 100 or (w["slots_total"] == 0 and w["tasks_total"] == 0):
                streak += 1
            else:
                break
        compliance_snapshot = {
            "sessions": cw["sessions"],
            "slot_pct": slot_pct,
            "task_pct": task_pct,
            "streak": streak,
        }

    return templates.TemplateResponse(
        request,
        "locktimer/overview.html",
        {
            "t": t,
            "user": current_user,
            "locale": locale,
            "active_session": _serialize_session(active, t) if active else None,
            "active_slots": active_slots,
            "active_tasks": active_tasks,
            "drafts": [_serialize_session(s, t) for s in drafts],
            "recent": [_serialize_session(s, t) for s in recent],
            "compliance_snapshot": compliance_snapshot,
        },
    )


# ---------------------------------------------------------------------------
# GET /locktimer/sessions/{id} — session detail
# ---------------------------------------------------------------------------


@router.get("/sessions/{session_id}", response_class=HTMLResponse)
async def locktimer_session_detail(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_owner_allowlist(current_user)

    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)

    session = await get_session(db, session_id, current_user.id)
    if session is None:
        return RedirectResponse("/locktimer", status_code=303)

    slot_rules = await list_slot_rules(db, session_id)
    task_rules = await list_task_rules(db, session_id)
    slot_occs = await list_slot_occurrences(db, session_id, limit=100)
    task_occs = await list_task_occurrences(db, session_id, limit=100)

    # Fetch proposals for this session
    proposals_result = await db.execute(
        select(LockLlmProposal)
        .where(
            LockLlmProposal.session_id == session_id,
            LockLlmProposal.owner_id == current_user.id,
        )
        .order_by(LockLlmProposal.created_at.desc())
        .limit(10)
    )
    proposals = list(proposals_result.scalars().all())

    return templates.TemplateResponse(
        request,
        "locktimer/session_detail.html",
        {
            "t": t,
            "user": current_user,
            "locale": locale,
            "session": _serialize_session(session, t),
            "slot_rules": [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "rule_type": r.rule_type,
                    "schedule": r.schedule,
                    "duration_seconds": r.duration_seconds,
                }
                for r in slot_rules
            ],
            "task_rules": [
                {
                    "id": str(r.id),
                    "title": r.title,
                    "schedule_type": r.schedule_type,
                    "schedule": r.schedule,
                    "due_window_seconds": r.due_window_seconds,
                }
                for r in task_rules
            ],
            "slot_occurrences": [_serialize_slot_occ(o, t) for o in slot_occs],
            "task_occurrences": [_serialize_task_occ(o, t) for o in task_occs],
            "proposals": [
                {
                    "id": str(p.id),
                    "kind": p.kind,
                    "status": p.status,
                    "items": p.items,
                    "pending_count": sum(1 for it in p.items if it.get("status") == "pending"),
                }
                for p in proposals
            ],
        },
    )


# ---------------------------------------------------------------------------
# GET /locktimer/templates — saved templates
# ---------------------------------------------------------------------------


@router.get("/templates", response_class=HTMLResponse)
async def locktimer_templates(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_owner_allowlist(current_user)

    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)

    templates_list = await list_templates(db, current_user.id)

    return templates.TemplateResponse(
        request,
        "locktimer/templates.html",
        {
            "t": t,
            "user": current_user,
            "locale": locale,
            "templates": [
                {
                    "id": str(tmpl.id),
                    "name": tmpl.name,
                    "description": tmpl.description,
                    "slot_count": len(tmpl.config.get("slot_rules", [])),
                    "task_count": len(tmpl.config.get("task_rules", [])),
                    "updated_at": tmpl.updated_at.isoformat() if tmpl.updated_at else None,
                }
                for tmpl in templates_list
            ],
        },
    )


# ---------------------------------------------------------------------------
# GET /locktimer/tag-violations/{session_id} — tag audit
# ---------------------------------------------------------------------------


@router.get("/tag-violations/{session_id}", response_class=HTMLResponse)
async def locktimer_tag_violations(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_owner_allowlist(current_user)

    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)

    session = await get_session(db, session_id, current_user.id)
    if session is None:
        return RedirectResponse("/locktimer", status_code=303)

    from app.locktimer.services.execution import list_tag_violations

    violations = await list_tag_violations(db, session_id, current_user.id)

    return templates.TemplateResponse(
        request,
        "locktimer/tag_violations.html",
        {
            "t": t,
            "user": current_user,
            "locale": locale,
            "session": _serialize_session(session, t),
            "violations": [
                {
                    "id": str(v.id),
                    "slot_occurrence_id": str(v.slot_occurrence_id),
                    "expected_tag": v.expected_tag or "—",
                    "provided_tag": v.provided_tag,
                    "reason": v.reason,
                    "created_at": v.created_at.isoformat() if v.created_at else None,
                }
                for v in violations
            ],
        },
    )


# ---------------------------------------------------------------------------
# GET /locktimer/calendar — calendar view
# ---------------------------------------------------------------------------


@router.get("/calendar", response_class=HTMLResponse)
async def locktimer_calendar(
    request: Request,
    month: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _check_owner_allowlist(current_user)

    locale = detect_locale(request, current_user.locale)
    t = get_translations(locale)

    today = date.today()
    try:
        ym = datetime.strptime(month or "", "%Y-%m").date().replace(day=1)
    except (ValueError, TypeError):
        ym = today.replace(day=1)

    # Month boundaries
    next_month = ym.replace(year=ym.year + 1, month=1) if ym.month == 12 else ym.replace(month=ym.month + 1)
    prev_month = ym - timedelta(days=1)
    prev_month = prev_month.replace(day=1)

    month_start = ym.isoformat()
    month_end = (next_month - timedelta(days=1)).isoformat()

    sessions = await list_sessions_by_date_range(db, current_user.id, month_start, month_end)

    # Build day → sessions map
    day_map: dict[int, list[dict]] = {}
    for s in sessions:
        if not s.started_at:
            continue
        day = s.started_at.day
        day_map.setdefault(day, []).append(
            {
                "id": str(s.id),
                "state": s.state,
                "duration_type": s.duration_type,
            }
        )

    # Compliance for the month
    compliance = await get_weekly_compliance(db, current_user.id, weeks=4)

    # Pre-compute calendar grid (Jinja2 doesn't have mktime/strftime)
    import calendar as cal_mod

    days_in_month = cal_mod.monthrange(ym.year, ym.month)[1]
    # weekday(): Monday=0 … Sunday=6
    first_weekday = ym.weekday()
    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    # Build grid: list of {day, is_today, sessions}
    grid: list[dict] = []
    for _ in range(first_weekday):
        grid.append({"day": 0, "is_today": False, "sessions": []})
    for d in range(1, days_in_month + 1):
        is_today = today.year == ym.year and today.month == ym.month and today.day == d
        grid.append({"day": d, "is_today": is_today, "sessions": day_map.get(d, [])})

    return templates.TemplateResponse(
        request,
        "locktimer/calendar.html",
        {
            "t": t,
            "user": current_user,
            "locale": locale,
            "today": today,
            "year": ym.year,
            "month": ym.month,
            "prev_month": prev_month.strftime("%Y-%m"),
            "next_month": next_month.strftime("%Y-%m"),
            "month_label": f"{ym.strftime('%B')} {ym.year}",
            "day_names": day_names,
            "grid": grid,
            "sessions_count": len(sessions),
            "compliance": compliance,
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _serialize_session(session, t) -> dict | None:
    if session is None:
        return None
    return {
        "id": str(session.id),
        "state": session.state,
        "duration_type": session.duration_type,
        "timezone": session.timezone,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "effective_end_at": session.effective_end_at.isoformat() if session.effective_end_at else None,
        "effective_end_ts": session.effective_end_at.timestamp() if session.effective_end_at else None,
        "max_end_at": session.max_end_at.isoformat() if session.max_end_at else None,
        "merge_gap_seconds": session.merge_gap_seconds,
        "row_version": session.row_version,
        "safety_stop_reason_code": session.safety_stop_reason_code,
        "state_label": {
            "draft": "Draft",
            "active": "Active",
            "completed": "Completed",
            "safety_stopped": "Safety Stopped",
        }.get(session.state, session.state),
        "remaining_seconds": (
            max(0, (session.effective_end_at - _now()).total_seconds())
            if session.effective_end_at and session.state == "active"
            else None
        ),
    }


def _serialize_slot_occ(occ: LockSlotOccurrence, t) -> dict:
    return {
        "id": str(occ.id),
        "state": occ.state,
        "planned_open_at": occ.planned_open_at.isoformat() if occ.planned_open_at else None,
        "planned_close_at": occ.planned_close_at.isoformat() if occ.planned_close_at else None,
        "actual_opened_at": occ.actual_opened_at.isoformat() if occ.actual_opened_at else None,
        "actual_closed_at": occ.actual_closed_at.isoformat() if occ.actual_closed_at else None,
        "close_due_at": occ.close_due_at.isoformat() if occ.close_due_at else None,
        "extension_applied_seconds": occ.extension_applied_seconds,
        "blocked_reason_code": occ.blocked_reason_code,
        "close_tag_number": occ.close_tag_number,
    }


def _serialize_task_occ(occ: LockTaskOccurrence, t) -> dict:
    return {
        "id": str(occ.id),
        "state": occ.state,
        "appears_at": occ.appears_at.isoformat() if occ.appears_at else None,
        "due_at": occ.due_at.isoformat() if occ.due_at else None,
        "content_visible": occ.content_visible,
        "occurrence_snapshot": occ.occurrence_snapshot,
        "final_reason_code": occ.final_reason_code,
    }
