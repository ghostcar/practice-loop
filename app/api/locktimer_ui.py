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
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
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
from app.models.chastity import ChastityCheckIn
from app.models.device import DEVICE_EVENT_TYPES, ChastityDeviceEvent
from app.models.locktimer import (
    LockLlmProposal,
    LockSession,
    LockSlotOccurrence,
    LockTaskOccurrence,
)
from app.models.user import User
from app.templates_setup import templates
from app.timeutils import as_utc, local_today

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
    device_id: str | None = Form(default=None),
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
    if device_id and device_id.strip():
        from app.locktimer.services.device import get_device

        device = await get_device(db, uuid.UUID(device_id.strip()), current_user.id)
        if device is None:
            raise HTTPException(400, "Device not found or not owned by you")
        session.device_id = device.id
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

    active_device = None
    if active:
        active_device, _ = await _load_device_info(db, active)

    return templates.TemplateResponse(
        request,
        "locktimer/overview.html",
        {
            "t": t,
            "user": current_user,
            "locale": locale,
            "active_session": _serialize_session(active, t) if active else None,
            "active_device": active_device,
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

    # Шаг 14b: pending (draft) journal entries per slot occurrence — окна,
    # открытые для плановой активности, ждут заполнения деталей при закрытии.
    slot_journal_pending: dict[str, str] = {}
    try:
        from app.models.journal import JournalEntry

        slot_ids = [o.id for o in slot_occs]
        if slot_ids:
            jr = await db.execute(
                select(JournalEntry.id, JournalEntry.slot_occurrence_id).where(
                    JournalEntry.user_id == current_user.id,
                    JournalEntry.slot_occurrence_id.in_(slot_ids),
                    JournalEntry.status == "draft",
                )
            )
            for jid, soid in jr.all():
                slot_journal_pending[str(soid)] = str(jid)
    except Exception:
        pass  # journal module may not be deployed yet

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

    bound_device, devices = await _load_device_info(db, session)

    # Device care log (B2, §6.2) — комфорт/проблемы/обслуживание устройства.
    device_events: list[dict] = []
    ev_result = await db.execute(
        select(ChastityDeviceEvent)
        .where(
            ChastityDeviceEvent.user_id == current_user.id,
            ChastityDeviceEvent.session_id == session_id,
        )
        .order_by(ChastityDeviceEvent.created_at.desc())
        .limit(50)
    )
    for ev in ev_result.scalars().all():
        device_events.append(
            {
                "id": str(ev.id),
                "event_type": ev.event_type,
                "comfort_level": ev.comfort_level,
                "severity": ev.severity,
                "notes": ev.notes,
                "created_at": ev.created_at,
            }
        )

    # Chastity check-ins (C2, §6.6) — состояние/комфорт/отчёт во время ношения.
    check_ins: list[dict] = []
    ci_result = await db.execute(
        select(ChastityCheckIn)
        .where(ChastityCheckIn.user_id == current_user.id, ChastityCheckIn.session_id == session_id)
        .order_by(ChastityCheckIn.created_at.desc())
        .limit(50)
    )
    for ci in ci_result.scalars().all():
        check_ins.append(
            {
                "id": str(ci.id),
                "mood": ci.mood,
                "comfort_level": ci.comfort_level,
                "notes": ci.notes,
                "created_at": ci.created_at,
            }
        )

    # Сквозной каталог (ADR-091): пикер причин/целей окон (домен timer).
    catalog_items: list[dict] = []
    try:
        from app.api.catalog import catalog_options

        catalog_items = await catalog_options(db, current_user.id, domain="timer")
    except Exception:
        pass  # catalog module may not be deployed yet

    # Средства/косметика (ADR-094): пикер средств для окон таймера.
    care_products: list[dict] = []
    care_names: dict[str, str] = {}
    care_products_by_rule: dict[str, list[dict]] = {}
    try:
        from app.models.care import CareProduct

        cp_result = await db.execute(
            select(CareProduct).where(CareProduct.user_id == current_user.id).order_by(CareProduct.name).limit(200)
        )
        for p in cp_result.scalars().all():
            care_products.append({"id": str(p.id), "name": p.name})
            care_names[str(p.id)] = p.name
        # карта rule_id → средства окна (для отображения в открытых окнах)
        for r in slot_rules:
            if r.care_product_ids:
                care_products_by_rule[str(r.id)] = [
                    {"id": pid, "name": care_names.get(str(pid), str(pid))} for pid in r.care_product_ids
                ]
    except Exception:
        pass  # care module may not be deployed yet

    # Medication schedules for the relief-task picker (ADR-085, relief-only).
    med_schedules: list[dict] = []
    try:
        from app.platform.composition import composition

        if composition.medication_enabled:
            from app.models.medication import MedSchedule

            sched_result = await db.execute(
                select(MedSchedule)
                .where(MedSchedule.user_id == current_user.id, MedSchedule.is_active.is_(True))
                .order_by(MedSchedule.created_at)
                .limit(50)
            )
            for s in sched_result.scalars().all():
                dose = f"{s.dose_quantity:g} {s.dose_unit or ''}".strip()
                med_schedules.append(
                    {
                        "id": str(s.id),
                        "label": f"{s.medication.name if s.medication else '?'}" + (f" ({dose})" if dose else ""),
                    }
                )
    except Exception:
        pass  # medication module may not be deployed yet

    # R5.4 / ADR-155: protocol runs attached to this timer session
    protocol_runs: list[dict] = []
    try:
        from app.models.protocol import ProtocolRun

        pr_result = await db.execute(
            select(ProtocolRun).where(
                ProtocolRun.lock_session_id == session_id,
            ).order_by(ProtocolRun.created_at.desc())
        )
        for pr in pr_result.scalars().all():
            protocol_runs.append({
                "id": str(pr.id),
                "title": pr.frozen_steps_snapshot[0].get("title", "Untitled") if pr.frozen_steps_snapshot else "Untitled",
                "status": pr.status,
                "total_steps": len(pr.frozen_steps_snapshot or []),
                "anchor_time": pr.anchor_time.isoformat() if pr.anchor_time else None,
                "created_at": pr.created_at.isoformat() if pr.created_at else None,
            })
    except Exception:
        pass

    return templates.TemplateResponse(
        request,
        "locktimer/session_detail.html",
        {
            "t": t,
            "user": current_user,
            "locale": locale,
            "protocol_runs": protocol_runs,
            "session": _serialize_session(session, t),
            "med_schedules": med_schedules,
            "catalog_items": catalog_items,
            "care_products": care_products,
            "bound_device": bound_device,
            "devices": devices,
            "device_events": device_events,
            "device_event_types": list(DEVICE_EVENT_TYPES),
            "check_ins": check_ins,
            "slot_rules": [
                {
                    "id": str(r.id),
                    "name": r.name,
                    "rule_type": r.rule_type,
                    "schedule": r.schedule,
                    "duration_seconds": r.duration_seconds,
                    "care_product_ids": r.care_product_ids or [],
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
                    "is_relief": bool((r.availability_policy or {}).get("relief") == "medication"),
                }
                for r in task_rules
            ],
            "slot_occurrences": [
                _serialize_slot_occ(o, t, care_products_by_rule=care_products_by_rule, care_names=care_names)
                for o in slot_occs
            ],
            "slot_journal_pending": slot_journal_pending,
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
                    "updated_at": tmpl.updated_at,
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
                    "created_at": v.created_at,
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

    today = local_today()
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


async def _load_device_info(db: AsyncSession, session) -> tuple[dict | None, list[dict]]:
    """Load the bound device + all user devices for the picker (Step 8)."""
    from sqlalchemy import select

    from app.models.life import InventoryItem

    result = await db.execute(
        select(InventoryItem)
        .where(InventoryItem.user_id == session.owner_id, InventoryItem.inventory_status != "archived")
        .order_by(InventoryItem.name)
    )
    items = list(result.scalars().all())
    by_id = {str(i.id): i for i in items}
    bound = None
    if session.device_id and str(session.device_id) in by_id:
        d = by_id[str(session.device_id)]
        bound = {
            "id": str(d.id),
            "name": d.name,
            "category": d.category,
            "inventory_status": d.inventory_status,
        }
    devices = [
        {
            "id": str(i.id),
            "name": i.name,
            "category": i.category,
            "inventory_status": i.inventory_status,
        }
        for i in items
    ]
    return bound, devices


def _serialize_session(session, t) -> dict | None:
    if session is None:
        return None
    effective_end = as_utc(session.effective_end_at) if session.effective_end_at else None
    return {
        "id": str(session.id),
        "device_id": str(session.device_id) if session.device_id else None,
        "state": session.state,
        "duration_type": session.duration_type,
        "timezone": session.timezone,
        "started_at": session.started_at,
        "effective_end_at": session.effective_end_at,
        "effective_end_ts": effective_end.timestamp() if effective_end else None,
        "max_end_at": session.max_end_at,
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
            max(0, (effective_end - _now()).total_seconds()) if effective_end and session.state == "active" else None
        ),
    }


def _serialize_slot_occ(
    occ: LockSlotOccurrence,
    t,
    care_products_by_rule: dict[str, list[dict]] | None = None,
    care_names: dict[str, str] | None = None,
) -> dict:
    care_products_by_rule = care_products_by_rule or {}
    care_names = care_names or {}
    rule_id = str(occ.rule_id) if occ.rule_id else None
    return {
        "id": str(occ.id),
        "rule_id": rule_id,
        "state": occ.state,
        "planned_open_at": occ.planned_open_at,
        "planned_close_at": occ.planned_close_at,
        "actual_opened_at": occ.actual_opened_at,
        "actual_closed_at": occ.actual_closed_at,
        "close_due_at": occ.close_due_at,
        "extension_applied_seconds": occ.extension_applied_seconds,
        "blocked_reason_code": occ.blocked_reason_code,
        "close_tag_number": occ.close_tag_number,
        "care_products": care_products_by_rule.get(rule_id or "", []),
    }


def _serialize_task_occ(occ: LockTaskOccurrence, t) -> dict:
    return {
        "id": str(occ.id),
        "state": occ.state,
        "appears_at": occ.appears_at,
        "due_at": occ.due_at,
        "content_visible": occ.content_visible,
        "occurrence_snapshot": occ.occurrence_snapshot,
        "final_reason_code": occ.final_reason_code,
    }


chastity_top_router = APIRouter(tags=["chastity-alias"])


@chastity_top_router.get("/chastity")
@router.get("/chastity")
async def chastity_alias_redirect(
    current_user: User = Depends(get_current_user),
):
    """Alias for /chastity redirecting to /locktimer."""
    return RedirectResponse(url="/locktimer", status_code=307)


@router.post("/keyholder/action")
async def keyholder_action(
    request: Request,
    session_id: uuid.UUID = Form(...),
    action_kind: str = Form(default="extension_request"),
    reason: str = Form(default=""),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """AI Keyholder Bot action handler (Step 21 — Chaster.app paradigm)."""
    _check_owner_allowlist(current_user)
    from app.llm.pipeline.keyholder import evaluate_keyholder_action
    from app.services.llm_provider import get_active_llm_config

    llm_config = await get_active_llm_config(db, current_user.id)
    if not llm_config:
        return RedirectResponse(url=f"/locktimer/sessions/{session_id}?error=no_llm_config", status_code=303)

    locale = detect_locale(request, current_user.locale)
    res = await evaluate_keyholder_action(
        db=db,
        user_id=current_user.id,
        session_id=session_id,
        action_kind=action_kind,
        reason=reason,
        llm_config=llm_config,
        locale=locale,
    )

    if res.get("decision") == "grant_extension" and res.get("added_duration_minutes"):
        stmt = select(LockSession).where(LockSession.id == session_id, LockSession.owner_id == current_user.id)
        sess = (await db.execute(stmt)).scalar_one_or_none()
        if sess and sess.effective_end_at:
            added = timedelta(minutes=res["added_duration_minutes"])
            sess.effective_end_at = sess.effective_end_at + added
            await db.flush()

    import urllib.parse

    msg_enc = urllib.parse.quote(res.get("keyholder_message", "Action processed."))
    return RedirectResponse(url=f"/locktimer/sessions/{session_id}?keyholder_msg={msg_enc}", status_code=303)
