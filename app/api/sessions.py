"""Activity Sessions — CRUD, lifecycle, JSON API, and interactive pages.

Extracted from dashboard.py (ADR-156) to keep the dashboard focused on
overview/stats and sessions in their own domain router.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.database import get_db
from app.gamification.handler import get_or_create_progress
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.activity_log import ActivityLog
from app.models.progress import UserProgress
from app.models.session import ActivitySession
from app.models.session_history import ActivitySessionHistory
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(tags=["sessions"])
session_json_router = APIRouter(prefix="/api/v2/sessions", tags=["sessions"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _owned_session(db: AsyncSession, session_id: uuid.UUID, user: User) -> ActivitySession:
    result = await db.execute(
        select(ActivitySession).where(ActivitySession.id == session_id, ActivitySession.owner_id == user.id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return session


async def _record_session_event(
    db: AsyncSession,
    session: ActivitySession,
    user: User,
    event_type: str,
    *,
    details: dict | None = None,
    penalize_change: bool = False,
) -> int:
    penalty_xp = 0
    if penalize_change and session.accepted_at is not None:
        configured = (session.session_rules or {}).get("change_penalty_xp", 10)
        try:
            penalty_xp = max(1, int(configured))
        except (TypeError, ValueError):
            penalty_xp = 10
        progress_result = await db.execute(select(UserProgress).where(UserProgress.user_id == user.id))
        progress = progress_result.scalar_one_or_none()
        if progress is None:
            progress = UserProgress(user_id=user.id)
        progress.xp = max(0, progress.xp - penalty_xp)
        progress.combo_count = 0
        progress.total_interrupted += 1
        db.add(progress)
    db.add(
        ActivitySessionHistory(
            session_id=session.id,
            actor_id=user.id,
            event_type=event_type,
            details=details,
            penalty_xp=penalty_xp,
        )
    )
    return penalty_xp


def _session_json(session: ActivitySession) -> dict:
    logs = session.__dict__.get("logs", [])
    return {
        "id": str(session.id),
        "status": session.status,
        "title": session.title,
        "notes": session.notes,
        "session_rules": session.session_rules,
        "accepted_at": session.accepted_at.isoformat() if session.accepted_at else None,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "task_ids": [str(task.id) for task in logs],
        "created_at": session.created_at.isoformat() if session.created_at else None,
    }


# ---------------------------------------------------------------------------
# Interactive pages
# ---------------------------------------------------------------------------


@router.get("/sessions/live", response_class=HTMLResponse)
async def sessions_live_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="sessions_live.html",
        context={
            "request": request, "t": t, "user": user, "locale": locale,
            "theme": theme, "active_nav": "sessions",
        },
    )


@router.get("/sessions/coop", response_class=HTMLResponse)
async def sessions_coop_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    from app.models.ds_suite import ManagedSubmissive
    from app.platform.social.repositories import list_user_relationships
    relationships = await list_user_relationships(db, user.id)
    managed_subs = (
        (await db.execute(select(ManagedSubmissive).where(ManagedSubmissive.top_user_id == user.id)))
        .scalars().all()
    )
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request,
        name="sessions_coop.html",
        context={
            "request": request, "t": t, "user": user, "locale": locale, "theme": theme,
            "active_nav": "sessions", "relationships": relationships, "managed_subs": managed_subs,
        },
    )


@router.get("/sessions", response_class=HTMLResponse)
async def sessions_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    result = await db.execute(
        select(ActivitySession)
        .where(ActivitySession.owner_id == user.id)
        .order_by(ActivitySession.created_at.desc())
        .limit(20)
    )
    sessions = result.scalars().all()

    history_result = (
        await db.execute(
            select(ActivitySessionHistory)
            .where(ActivitySessionHistory.session_id.in_([s.id for s in sessions]))
            .order_by(ActivitySessionHistory.created_at.desc())
        )
        if sessions else None
    )
    histories: dict[uuid.UUID, list[ActivitySessionHistory]] = {s.id: [] for s in sessions}
    if history_result is not None:
        for event in history_result.scalars().all():
            histories[event.session_id].append(event)

    available_result = await db.execute(
        select(ActivityLog)
        .where(
            ActivityLog.user_id == user.id,
            ActivityLog.session_id.is_(None),
            ActivityLog.status.in_(["draft", "planned"]),
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(50)
    )

    return templates.TemplateResponse(
        request=request,
        name="sessions.html",
        context={
            "request": request, "t": t, "user": user, "locale": locale, "theme": theme,
            "sessions": sessions, "session_histories": histories,
            "available_tasks": available_result.scalars().all(),
            "active_nav": "sessions",
        },
    )


@router.get("/sessions/rules-builder", response_class=HTMLResponse)
async def sessions_rules_builder_page(request: Request, user: User = Depends(get_current_user)):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request, name="sessions_rules_builder.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, "active_nav": "sessions"},
    )


@router.get("/sessions/wizard", response_class=HTMLResponse)
async def sessions_wizard_page(request: Request, user: User = Depends(get_current_user)):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request, name="sessions_wizard.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, "active_nav": "sessions"},
    )


@router.get("/sessions/ambient", response_class=HTMLResponse)
async def sessions_ambient_page(request: Request, user: User = Depends(get_current_user)):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    return templates.TemplateResponse(
        request=request, name="sessions_ambient.html",
        context={"request": request, "t": t, "user": user, "locale": locale, "theme": theme, "active_nav": "sessions"},
    )


# ---------------------------------------------------------------------------
# Lifecycle mutations
# ---------------------------------------------------------------------------


@router.post("/sessions/live/complete")
async def live_session_complete_endpoint(
    session_id: str | None = Form(None),
    notes: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(ActivitySession).where(
        ActivitySession.owner_id == user.id,
        ActivitySession.status == "active",
    ).with_for_update()
    if session_id and session_id.strip():
        try:
            query = query.where(ActivitySession.id == uuid.UUID(session_id.strip()))
        except ValueError:
            raise HTTPException(400, "Invalid session_id UUID format") from None

    session = (await db.execute(query)).scalars().first()
    if not session:
        return RedirectResponse(url="/sessions", status_code=303)

    session.status = "ended"
    session.ended_at = datetime.now(UTC)
    session.notes = (session.notes or "") + f"\nCompleted hold with notes: {notes.strip()}"
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user.id, event_type="completed"))
    prog = await get_or_create_progress(db, user.id)
    prog.xp += 50
    prog.total_completed += 1
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/live/interrupt")
async def live_session_interrupt_endpoint(
    session_id: str | None = Form(None),
    reason: str = Form(""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    query = select(ActivitySession).where(
        ActivitySession.owner_id == user.id,
        ActivitySession.status == "active",
    ).with_for_update()
    if session_id and session_id.strip():
        try:
            query = query.where(ActivitySession.id == uuid.UUID(session_id.strip()))
        except ValueError:
            raise HTTPException(400, "Invalid session_id UUID format") from None

    session = (await db.execute(query)).scalars().first()
    if not session:
        return RedirectResponse(url="/sessions", status_code=303)

    session.status = "ended"
    session.ended_at = datetime.now(UTC)
    session.notes = (session.notes or "") + f"\nInterrupted hold with reason: {reason.strip()}"
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user.id, event_type="interrupted"))
    prog = await get_or_create_progress(db, user.id)
    prog.xp = max(0, prog.xp - 25)
    prog.total_interrupted += 1
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/create-from-template")
async def create_session_from_template(
    request: Request,
    template_type: str = Form(default="chastity"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    templates_dict = {
        "chastity": {
            "title": "Chastity & Keyholder Ritual Session",
            "notes": "Сессия контроля доступа, регулярных фото-чек-инов пломб и оценки ИИ-Keyholder.",
            "rules": {"rules": [{"type": "chastity_checkin", "interval_hours": 12}], "ai_role": "keyholder"},
        },
        "training": {
            "title": "Training & Posture Routine Session",
            "notes": "Дисциплинарная сессия физических тренировок, удержания поз и отслеживания выносливости.",
            "rules": {"rules": [{"type": "task_quota", "daily_count": 3}], "ai_role": "observer"},
        },
        "aftercare": {
            "title": "Aftercare & Health Recovery Session",
            "notes": "Мягкая сессия восстановления: уход за кожей, гидратация, стабилизация и Health Pause.",
            "rules": {"rules": [{"type": "health_trigger", "action": "convert_to_aftercare"}], "ai_role": "care"},
        },
        "contract": {
            "title": "Pair BDSM Contract Session",
            "notes": "Полная контрактная сессия с правилами, стоп-словами, эскалациями и заданиями.",
            "rules": {"rules": [{"type": "contract_compliance", "safewords": ["RED", "YELLOW"]}], "ai_role": "observer"},
        },
    }
    cfg = templates_dict.get(template_type, templates_dict["chastity"])
    session = ActivitySession(owner_id=user.id, status="created", title=cfg["title"],
                              notes=cfg["notes"], session_rules=cfg["rules"])
    db.add(session)
    await db.flush()
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user.id, event_type="created"))
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/create-custom")
async def create_custom_session(
    request: Request,
    title: str = Form(...),
    ai_role: str = Form(default="keyholder"),
    notes: str = Form(default=""),
    ext_wheel: bool = Form(default=False),
    ext_pillory: bool = Form(default=False),
    ext_tag_seal: bool = Form(default=False),
    ext_peer_review: bool = Form(default=False),
    ext_dice: bool = Form(default=False),
    ext_aftercare: bool = Form(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = ActivitySession(
        owner_id=user.id, status="created",
        title=title.strip()[:200], notes=notes.strip()[:1000] or None,
        session_rules={
            "ai_role": ai_role, "custom_session": True,
            "extensions": {
                "wheel": ext_wheel, "pillory": ext_pillory, "tag_seal": ext_tag_seal,
                "peer_review": ext_peer_review, "dice": ext_dice, "aftercare": ext_aftercare,
            },
        },
    )
    db.add(session)
    await db.flush()
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user.id, event_type="created"))
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions")
async def create_session(request: Request, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = ActivitySession(owner_id=user.id, status="created", title="Session")
    db.add(session)
    await db.flush()
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user.id, event_type="created"))
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/accept")
async def accept_session(s_id: uuid.UUID, user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await _owned_session(db, s_id, user)
    if session.status != "created":
        raise HTTPException(status_code=409, detail="Only a created session can be accepted")
    if session.accepted_at is None:
        session.accepted_at = datetime.now(UTC)
        db.add(session)
        await _record_session_event(db, session, user, "accepted",
                                     details={"task_ids": [str(log.id) for log in session.logs]})
        await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/tasks/attach")
async def attach_session_task(
    s_id: uuid.UUID, task_id: uuid.UUID = Form(...),
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, s_id, user)
    if session.status == "ended":
        raise HTTPException(status_code=409, detail="Ended session cannot be changed")
    task_result = await db.execute(select(ActivityLog).where(ActivityLog.id == task_id, ActivityLog.user_id == user.id))
    task = task_result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.session_id not in (None, session.id):
        raise HTTPException(status_code=409, detail="Task belongs to another session")
    if task.session_id is None:
        task.session_id = session.id
        db.add(task)
        await _record_session_event(db, session, user, "task_added",
                                     details={"task_id": str(task.id), "title": task.title_override or task.selected_entity_name},
                                     penalize_change=True)
        await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/tasks/{task_id}/detach")
async def detach_session_task(
    s_id: uuid.UUID, task_id: uuid.UUID,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    session = await _owned_session(db, s_id, user)
    if session.status == "ended":
        raise HTTPException(status_code=409, detail="Ended session cannot be changed")
    task_result = await db.execute(
        select(ActivityLog).where(
            ActivityLog.id == task_id, ActivityLog.user_id == user.id,
            ActivityLog.session_id == session.id,
        )
    )
    task = task_result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.session_id = None
    db.add(task)
    await _record_session_event(db, session, user, "task_removed",
                                 details={"task_id": str(task.id), "title": task.title_override or task.selected_entity_name},
                                 penalize_change=True)
    await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/start")
async def start_session(s_id: uuid.UUID, request: Request, user: User = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db)):
    s = await _owned_session(db, s_id, user)
    if s.status != "created":
        raise HTTPException(status_code=409, detail="Only a created session can be started")
    now = datetime.now(UTC)
    if s.accepted_at is None:
        s.accepted_at = now
        await _record_session_event(db, s, user, "accepted", details={"task_ids": [str(log.id) for log in s.logs]})
    s.status = "active"
    s.started_at = now
    db.add(s)
    await _record_session_event(db, s, user, "started")
    await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


@router.post("/sessions/{s_id}/end")
async def end_session(s_id: uuid.UUID, request: Request, user: User = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db)):
    s = await _owned_session(db, s_id, user)
    if s.status not in ("created", "active"):
        raise HTTPException(status_code=409, detail="Session is already ended")
    s.status = "ended"
    s.ended_at = datetime.now(UTC)
    db.add(s)
    await _record_session_event(db, s, user, "ended")
    await db.flush()
    return RedirectResponse(url="/sessions", status_code=303)


# ---------------------------------------------------------------------------
# JSON API (api/v2/sessions)
# ---------------------------------------------------------------------------


class _SessionCreateIn(BaseModel):
    title: str | None = None
    notes: str | None = None
    session_rules: dict | None = None


class _SessionTaskIn(BaseModel):
    task_id: uuid.UUID


@session_json_router.get("")
async def json_sessions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(ActivitySession).where(ActivitySession.owner_id == user.id).order_by(ActivitySession.created_at.desc())
    )).scalars().all()
    return [_session_json(s) for s in rows]


@session_json_router.post("")
async def json_create_session(data: _SessionCreateIn, user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    session = ActivitySession(owner_id=user.id, status="created",
                              title=data.title, notes=data.notes, session_rules=data.session_rules)
    db.add(session)
    await db.flush()
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user.id, event_type="created"))
    await db.flush()
    return JSONResponse(_session_json(session), status_code=201)


@session_json_router.post("/{session_id}/accept")
async def json_accept_session(session_id: uuid.UUID, user: User = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db)):
    session = await _owned_session(db, session_id, user)
    if session.status != "created":
        raise HTTPException(status_code=409, detail="Only a created session can be accepted")
    if session.accepted_at is None:
        session.accepted_at = datetime.now(UTC)
        await _record_session_event(db, session, user, "accepted",
                                     details={"task_ids": [str(t.id) for t in session.logs]})
        await db.flush()
    return _session_json(session)


@session_json_router.post("/{session_id}/start")
async def json_start_session(session_id: uuid.UUID, user: User = Depends(get_current_user),
                             db: AsyncSession = Depends(get_db)):
    session = await _owned_session(db, session_id, user)
    if session.status != "created":
        raise HTTPException(status_code=409, detail="Only a created session can be started")
    now = datetime.now(UTC)
    if session.accepted_at is None:
        session.accepted_at = now
        await _record_session_event(db, session, user, "accepted",
                                     details={"task_ids": [str(t.id) for t in session.logs]})
    session.status = "active"
    session.started_at = now
    await _record_session_event(db, session, user, "started")
    await db.flush()
    return _session_json(session)


@session_json_router.post("/{session_id}/end")
async def json_end_session(session_id: uuid.UUID, user: User = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db)):
    session = await _owned_session(db, session_id, user)
    if session.status not in ("created", "active"):
        raise HTTPException(status_code=409, detail="Session is already ended")
    session.status = "ended"
    session.ended_at = datetime.now(UTC)
    await _record_session_event(db, session, user, "ended")
    await db.flush()
    return _session_json(session)


@session_json_router.post("/{session_id}/tasks")
async def json_attach_session_task(session_id: uuid.UUID, data: _SessionTaskIn,
                                   user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await _owned_session(db, session_id, user)
    if session.status == "ended":
        raise HTTPException(status_code=409, detail="Ended session cannot be changed")
    task = (await db.execute(
        select(ActivityLog).where(ActivityLog.id == data.task_id, ActivityLog.user_id == user.id)
    )).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.session_id not in (None, session.id):
        raise HTTPException(status_code=409, detail="Task belongs to another session")
    if task.session_id is None:
        task.session_id = session.id
        await _record_session_event(db, session, user, "task_added",
                                     details={"task_id": str(task.id), "title": task.title_override or task.selected_entity_name},
                                     penalize_change=True)
        await db.flush()
        await db.refresh(session, ["logs"])
    return _session_json(session)


@session_json_router.delete("/{session_id}/tasks/{task_id}", status_code=204)
async def json_detach_session_task(session_id: uuid.UUID, task_id: uuid.UUID,
                                   user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    session = await _owned_session(db, session_id, user)
    if session.status == "ended":
        raise HTTPException(status_code=409, detail="Ended session cannot be changed")
    task = (await db.execute(
        select(ActivityLog).where(
            ActivityLog.id == task_id, ActivityLog.user_id == user.id,
            ActivityLog.session_id == session.id,
        )
    )).scalar_one_or_none()
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    task.session_id = None
    await _record_session_event(db, session, user, "task_removed",
                                 details={"task_id": str(task.id), "title": task.title_override or task.selected_entity_name},
                                 penalize_change=True)
    await db.flush()


@session_json_router.get("/{session_id}/history")
async def json_session_history(session_id: uuid.UUID, user: User = Depends(get_current_user),
                               db: AsyncSession = Depends(get_db)):
    await _owned_session(db, session_id, user)
    events = (await db.execute(
        select(ActivitySessionHistory).where(ActivitySessionHistory.session_id == session_id)
        .order_by(ActivitySessionHistory.created_at.asc())
    )).scalars().all()
    return [
        {"id": str(e.id), "event_type": e.event_type, "details": e.details,
         "penalty_xp": e.penalty_xp, "created_at": e.created_at.isoformat()}
        for e in events
    ]
