"""Sessions service — all business logic for activity sessions.

Extracted from app/api/sessions.py (ADR-169).  HTTP layer stays thin.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gamification.handler import get_or_create_progress
from app.models.activity_log import ActivityLog
from app.models.progress import UserProgress
from app.models.session import ActivitySession
from app.models.session_history import ActivitySessionHistory
from app.models.user import User
from app.services.errors import NotFoundError


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


async def get_owned_session(db: AsyncSession, session_id: uuid.UUID, user_id: uuid.UUID) -> ActivitySession:
    """Get a session owned by the user, or raise ValueError."""
    result = await db.execute(
        select(ActivitySession).where(ActivitySession.id == session_id, ActivitySession.owner_id == user_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundError("Session not found")
    return session


async def record_session_event(
    db: AsyncSession,
    session: ActivitySession,
    user_id: uuid.UUID,
    event_type: str,
    *,
    details: dict | None = None,
    penalize_change: bool = False,
) -> int:
    """Record a session event in history. Returns penalty_xp applied."""
    penalty_xp = 0
    if penalize_change and session.accepted_at is not None:
        configured = (session.session_rules or {}).get("change_penalty_xp", 10)
        try:
            penalty_xp = max(1, int(configured))
        except (TypeError, ValueError):
            penalty_xp = 10
        progress_result = await db.execute(select(UserProgress).where(UserProgress.user_id == user_id))
        progress = progress_result.scalar_one_or_none()
        if progress is None:
            progress = UserProgress(user_id=user_id)
        progress.xp = max(0, progress.xp - penalty_xp)
        progress.combo_count = 0
        progress.total_interrupted += 1
        db.add(progress)
    db.add(
        ActivitySessionHistory(
            session_id=session.id,
            actor_id=user_id,
            event_type=event_type,
            details=details,
            penalty_xp=penalty_xp,
        )
    )
    return penalty_xp


def session_json(session: ActivitySession) -> dict:
    """Serialize a session to JSON dict."""
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


def event_view(e: ActivitySessionHistory) -> dict:
    return {
        "id": str(e.id),
        "event_type": e.event_type,
        "details": e.details,
        "penalty_xp": e.penalty_xp,
        "created_at": e.created_at.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Page context
# ─────────────────────────────────────────────────────────────────────────────


async def get_sessions_page_context(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Build sessions list page context."""
    result = await db.execute(
        select(ActivitySession)
        .where(ActivitySession.owner_id == user_id)
        .order_by(ActivitySession.created_at.desc())
        .limit(20)
    )
    sessions = list(result.scalars().all())

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
            ActivityLog.user_id == user_id,
            ActivityLog.session_id.is_(None),
            ActivityLog.status.in_(["draft", "planned"]),
        )
        .order_by(ActivityLog.created_at.desc())
        .limit(50)
    )

    return {
        "sessions": sessions,
        "session_histories": histories,
        "available_tasks": list(available_result.scalars().all()),
    }


async def get_coop_page_context(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Build coop sessions page context."""
    from app.models.ds_suite import ManagedSubmissive
    from app.platform.social.repositories import list_user_relationships

    relationships = await list_user_relationships(db, user_id)
    managed_subs = list(
        (await db.execute(select(ManagedSubmissive).where(ManagedSubmissive.top_user_id == user_id)))
        .scalars().all()
    )
    return {"relationships": relationships, "managed_subs": managed_subs}


# ─────────────────────────────────────────────────────────────────────────────
# Session CRUD
# ─────────────────────────────────────────────────────────────────────────────


async def create_session(db: AsyncSession, user_id: uuid.UUID, **kwargs) -> ActivitySession:
    """Create a basic session."""
    title = kwargs.pop("title", "Session")
    session = ActivitySession(owner_id=user_id, status="created", title=title, **kwargs)
    db.add(session)
    await db.flush()
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user_id, event_type="created"))
    return session


async def create_session_from_template(db: AsyncSession, user_id: uuid.UUID, template_type: str) -> ActivitySession:
    """Create a session from a predefined template."""
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
    session = ActivitySession(
        owner_id=user_id, status="created",
        title=cfg["title"], notes=cfg["notes"], session_rules=cfg["rules"],
    )
    db.add(session)
    await db.flush()
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user_id, event_type="created"))
    return session


async def create_custom_session(
    db: AsyncSession, user_id: uuid.UUID, *, title: str, ai_role: str, notes: str,
    ext_wheel: bool, ext_pillory: bool, ext_tag_seal: bool, ext_peer_review: bool,
    ext_dice: bool, ext_aftercare: bool,
) -> ActivitySession:
    """Create a custom session with user-specified rules."""
    session = ActivitySession(
        owner_id=user_id, status="created",
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
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user_id, event_type="created"))
    return session


# ─────────────────────────────────────────────────────────────────────────────
# Session lifecycle
# ─────────────────────────────────────────────────────────────────────────────


async def accept_session(db: AsyncSession, session: ActivitySession, user_id: uuid.UUID) -> None:
    """Accept a created session."""
    if session.status != "created":
        raise ValueError("Only a created session can be accepted")
    if session.accepted_at is None:
        session.accepted_at = datetime.now(UTC)
        await record_session_event(db, session, user_id, "accepted",
                                    details={"task_ids": [str(log.id) for log in session.logs]})
        await db.flush()


async def start_session(db: AsyncSession, session: ActivitySession, user_id: uuid.UUID) -> None:
    """Start a session (auto-accepts if not yet accepted)."""
    if session.status != "created":
        raise ValueError("Only a created session can be started")
    now = datetime.now(UTC)
    if session.accepted_at is None:
        session.accepted_at = now
        await record_session_event(db, session, user_id, "accepted",
                                    details={"task_ids": [str(log.id) for log in session.logs]})
    session.status = "active"
    session.started_at = now
    await record_session_event(db, session, user_id, "started")
    await db.flush()


async def end_session(db: AsyncSession, session: ActivitySession, user_id: uuid.UUID) -> None:
    """End a session."""
    if session.status not in ("created", "active"):
        raise ValueError("Session is already ended")
    session.status = "ended"
    session.ended_at = datetime.now(UTC)
    await record_session_event(db, session, user_id, "ended")
    await db.flush()


async def complete_live_session(
    db: AsyncSession, user_id: uuid.UUID, session_id: str | None, notes: str,
) -> ActivitySession | None:
    """Complete an active live session. Returns session or None if not found."""
    query = select(ActivitySession).where(
        ActivitySession.owner_id == user_id,
        ActivitySession.status == "active",
    ).with_for_update()
    if session_id and session_id.strip():
        try:
            query = query.where(ActivitySession.id == uuid.UUID(session_id.strip()))
        except ValueError:
            raise ValueError("Invalid session_id UUID format") from None

    session = (await db.execute(query)).scalars().first()
    if not session:
        return None

    session.status = "ended"
    session.ended_at = datetime.now(UTC)
    session.notes = (session.notes or "") + f"\nCompleted hold with notes: {notes.strip()}"
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user_id, event_type="completed"))
    prog = await get_or_create_progress(db, user_id)
    prog.xp += 50
    prog.total_completed += 1
    return session


async def interrupt_live_session(
    db: AsyncSession, user_id: uuid.UUID, session_id: str | None, reason: str,
) -> ActivitySession | None:
    """Interrupt an active live session. Returns session or None if not found."""
    query = select(ActivitySession).where(
        ActivitySession.owner_id == user_id,
        ActivitySession.status == "active",
    ).with_for_update()
    if session_id and session_id.strip():
        try:
            query = query.where(ActivitySession.id == uuid.UUID(session_id.strip()))
        except ValueError:
            raise ValueError("Invalid session_id UUID format") from None

    session = (await db.execute(query)).scalars().first()
    if not session:
        return None

    session.status = "ended"
    session.ended_at = datetime.now(UTC)
    session.notes = (session.notes or "") + f"\nInterrupted hold with reason: {reason.strip()}"
    db.add(ActivitySessionHistory(session_id=session.id, actor_id=user_id, event_type="interrupted"))
    prog = await get_or_create_progress(db, user_id)
    prog.xp = max(0, prog.xp - 25)
    prog.total_interrupted += 1
    return session


# ─────────────────────────────────────────────────────────────────────────────
# Task attach / detach
# ─────────────────────────────────────────────────────────────────────────────


async def attach_task(
    db: AsyncSession, session: ActivitySession, task_id: uuid.UUID, user_id: uuid.UUID,
) -> None:
    """Attach a task to a session."""
    if session.status == "ended":
        raise ValueError("Ended session cannot be changed")
    task_result = await db.execute(select(ActivityLog).where(ActivityLog.id == task_id, ActivityLog.user_id == user_id))
    task = task_result.scalar_one_or_none()
    if task is None:
        raise ValueError("Task not found")
    if task.session_id not in (None, session.id):
        raise ValueError("Task belongs to another session")
    if task.session_id is None:
        task.session_id = session.id
        db.add(task)
        await record_session_event(db, session, user_id, "task_added",
                                    details={"task_id": str(task.id), "title": task.title_override or task.selected_entity_name},
                                    penalize_change=True)
        await db.flush()


async def detach_task(
    db: AsyncSession, session: ActivitySession, task_id: uuid.UUID, user_id: uuid.UUID,
) -> None:
    """Detach a task from a session."""
    if session.status == "ended":
        raise ValueError("Ended session cannot be changed")
    task_result = await db.execute(
        select(ActivityLog).where(
            ActivityLog.id == task_id, ActivityLog.user_id == user_id,
            ActivityLog.session_id == session.id,
        )
    )
    task = task_result.scalar_one_or_none()
    if task is None:
        raise ValueError("Task not found")
    task.session_id = None
    db.add(task)
    await record_session_event(db, session, user_id, "task_removed",
                                details={"task_id": str(task.id), "title": task.title_override or task.selected_entity_name},
                                penalize_change=True)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Session history
# ─────────────────────────────────────────────────────────────────────────────


async def get_session_history(db: AsyncSession, session_id: uuid.UUID) -> list[dict]:
    """Get session history events."""
    events = (await db.execute(
        select(ActivitySessionHistory)
        .where(ActivitySessionHistory.session_id == session_id)
        .order_by(ActivitySessionHistory.created_at.asc())
    )).scalars().all()
    return [event_view(e) for e in events]
