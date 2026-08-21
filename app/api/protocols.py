"""Protocol Engine UI (R5.3, REFACTOR_ROADMAP_V2.md).

Страницы: список протоколов, конструктор (шаги + duration_picker), интерактивный
ран. Мутации — только через сервисы ``app/services/protocol.py`` (create /
start / execute). ``timing_spec`` собирается из полей формы как типизированный
JSON (``rel_before``/``rel_after`` + offset_seconds).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.auth import get_current_user
from app.database import get_db
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.models.protocol import ProtocolDefinition, ProtocolRun, ProtocolStepLog, ProtocolStepType, TimingSpecType
from app.models.user import User
from app.services.capability import ActorContext
from app.services.protocol import create_protocol_definition, execute_protocol_step, start_protocol_run
from app.templates_setup import templates

router = APIRouter(prefix="/protocols", tags=["protocols"])

STEP_TYPES = [t.value for t in ProtocolStepType]
TIMING_TYPES = [t.value for t in TimingSpecType]
CATEGORIES = ("prep", "recovery", "routine", "discipline")


# ── Страницы ──────────────────────────────────────────────────────────


@router.get("", response_class=HTMLResponse)
async def protocols_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Список протоколов пользователя + активные раны."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    protos = (
        (await db.execute(select(ProtocolDefinition).where(ProtocolDefinition.user_id == user.id).order_by(ProtocolDefinition.created_at.desc())))
        .scalars()
        .all()
    )
    runs = (
        await db.execute(
            select(ProtocolRun)
            .where(ProtocolRun.user_id == user.id)
            .order_by(ProtocolRun.created_at.desc())
        )
    )
    active_runs = [r for r in runs.scalars().all() if r.status in ("scheduled", "active")]

    return templates.TemplateResponse(
        request=request,
        name="protocols.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "protocols",
            "protocols": protos,
            "active_runs": active_runs,
            "step_types": STEP_TYPES,
            "categories": CATEGORIES,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def protocol_builder_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Форма создания протокола (новый)."""
    return _builder_response(request, user, db, proto=None)


@router.get("/{protocol_id}/edit", response_class=HTMLResponse)
async def protocol_edit_page(
    request: Request,
    protocol_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Форма редактирования протокола."""
    proto = await _get_own_protocol(db, protocol_id, user.id)
    return _builder_response(request, user, db, proto=proto)


@router.get("/{protocol_id}/run", response_class=HTMLResponse)
async def protocol_run_page(
    request: Request,
    protocol_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Интерактивный чеклист шагов активного рана."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    run = (
        await db.execute(
            select(ProtocolRun).where(ProtocolRun.id == protocol_id, ProtocolRun.user_id == user.id)
        )
    ).scalar_one_or_none()
    if run is None:
        return RedirectResponse(url="/protocols", status_code=303)

    logs = (
        (await db.execute(select(ProtocolStepLog).where(ProtocolStepLog.run_id == run.id).order_by(ProtocolStepLog.planned_at)))
        .scalars()
        .all()
    )
    return templates.TemplateResponse(
        request=request,
        name="protocol_run.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "protocols",
            "run": run,
            "proto": (
                await db.execute(select(ProtocolDefinition).where(ProtocolDefinition.id == run.protocol_id))
            ).scalar_one_or_none()
            if run.protocol_id
            else None,
            "logs": logs,
            "step_types": STEP_TYPES,
        },
    )


def _builder_response(request, user, db, proto):
    """Общий рендер конструктора (новый/редактирование)."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    steps: list[dict[str, Any]] = []
    if proto is not None:
        for s in proto.steps:
            steps.append(
                {
                    "id": str(s.id),
                    "step_order": s.step_order,
                    "title": s.title,
                    "step_type": s.step_type,
                    "reference_id": str(s.reference_id) if s.reference_id else "",
                    "timing_spec": s.timing_spec or {},
                    "custom_params": s.custom_params or {},
                }
            )

    return templates.TemplateResponse(
        request=request,
        name="protocol_builder.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "protocols",
            "proto": proto,
            "steps": steps,
            "step_types": STEP_TYPES,
            "timing_types": TIMING_TYPES,
            "categories": CATEGORIES,
        },
    )


# ── Мутации ───────────────────────────────────────────────────────────


def _parse_steps_form(steps_json: str) -> list[dict[str, Any]]:
    """Распарсить шаги из JSON-поле steps_json формы конструктора."""
    import json

    try:
        raw = json.loads(steps_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    steps: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        timing = item.get("timing_spec") or {}
        steps.append(
            {
                "title": str(item["title"])[:255],
                "step_type": item.get("step_type", "activity") if item.get("step_type") in STEP_TYPES else "activity",
                "reference_id": item.get("reference_id") or None,
                "timing_spec": {
                    "type": timing.get("type", "rel_after") if timing.get("type") in TIMING_TYPES else "rel_after",
                    "offset_seconds": max(0, int(timing.get("offset_seconds", 0) or 0)),
                },
                "custom_params": item.get("custom_params") or {},
            }
        )
    return steps


@router.post("/create")
async def protocols_create(
    request: Request,
    title: str = Form(...),
    description: str = Form(default=""),
    category: str = Form(default="prep"),
    anchor_type: str = Form(default="session_bound"),
    steps_json: str = Form(default="[]"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if category not in CATEGORIES:
        category = "prep"
    if anchor_type not in ("independent", "session_bound", "timer_bound"):
        anchor_type = "session_bound"
    steps = _parse_steps_form(steps_json)
    proto = await create_protocol_definition(
        db, user.id, title=title.strip()[:255], description=description.strip() or None,
        category=category, anchor_type=anchor_type, steps=steps,
    )
    await db.flush()
    return RedirectResponse(url=f"/protocols/{proto.id}/edit", status_code=303)


@router.post("/{protocol_id}/update")
async def protocols_update(
    request: Request,
    protocol_id: uuid.UUID,
    title: str = Form(...),
    description: str = Form(default=""),
    category: str = Form(default="prep"),
    anchor_type: str = Form(default="session_bound"),
    steps_json: str = Form(default="[]"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proto = await _get_own_protocol(db, protocol_id, user.id)
    if category in CATEGORIES:
        proto.category = category
    if anchor_type in ("independent", "session_bound", "timer_bound"):
        proto.anchor_type = anchor_type
    proto.title = title.strip()[:255]
    proto.description = description.strip() or None

    # Замена шагов целиком (каскад delete-orphan на relationship)
    from app.models.protocol import ProtocolStep

    proto.steps.clear()
    await db.flush()
    steps = _parse_steps_form(steps_json)
    for idx, s in enumerate(steps, start=1):
        ref_id = uuid.UUID(s["reference_id"]) if s.get("reference_id") else None
        proto.steps.append(
            ProtocolStep(
                step_order=idx,
                title=s["title"],
                step_type=s["step_type"],
                reference_id=ref_id,
                timing_spec=s["timing_spec"],
                custom_params=s["custom_params"],
            )
        )
    await db.flush()
    return RedirectResponse(url=f"/protocols/{protocol_id}/edit", status_code=303)


@router.post("/{protocol_id}/delete")
async def protocols_delete(
    request: Request,
    protocol_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proto = await _get_own_protocol(db, protocol_id, user.id)
    await db.delete(proto)
    await db.flush()
    return RedirectResponse(url="/protocols", status_code=303)


@router.post("/{protocol_id}/start")
async def protocols_start(
    request: Request,
    protocol_id: uuid.UUID,
    anchor_time: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    proto = await _get_own_protocol(db, protocol_id, user.id)
    try:
        anchor = datetime.fromisoformat(anchor_time) if anchor_time else datetime.now(timezone.utc)
    except ValueError:
        anchor = datetime.now(timezone.utc)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=timezone.utc)
    run = await start_protocol_run(db, user.id, proto.id, anchor)
    await db.flush()
    return RedirectResponse(url=f"/protocols/{run.id}/run", status_code=303)


@router.post("/runs/{run_id}/complete-step")
async def protocols_complete_step(
    request: Request,
    run_id: uuid.UUID,
    step_log_id: uuid.UUID = Form(...),
    result_payload: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Отметить шаг выполненным (эмуляция, ADR-129)."""
    run = (
        await db.execute(select(ProtocolRun).where(ProtocolRun.id == run_id, ProtocolRun.user_id == user.id))
    ).scalar_one_or_none()
    if run is None:
        return RedirectResponse(url="/protocols", status_code=303)

    actor = ActorContext(actor_id=user.id, actor_type="user", source="owner_manual")
    payload: dict[str, Any] = {}
    if result_payload:
        try:
            import json

            parsed = json.loads(result_payload)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
    try:
        await execute_protocol_step(db, step_log_id, actor, payload)
        await db.flush()
    except ValueError:
        await db.rollback()
    return RedirectResponse(url=f"/protocols/{run_id}/run", status_code=303)


# ── Хелперы ───────────────────────────────────────────────────────────


async def _get_own_protocol(db: AsyncSession, protocol_id: uuid.UUID, user_id: uuid.UUID) -> ProtocolDefinition:
    from fastapi import HTTPException

    proto = (
        await db.execute(
            select(ProtocolDefinition).where(ProtocolDefinition.id == protocol_id, ProtocolDefinition.user_id == user_id)
        )
    ).scalar_one_or_none()
    if proto is None:
        raise HTTPException(status_code=404, detail="Protocol not found")
    return proto
