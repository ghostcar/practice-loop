import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.calendar import get_day_schedule, is_available
from app.auth import get_current_user
from app.database import get_db
from app.gamification.handler import on_task_completed, on_task_interrupted
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.llm.pipeline import generate_task, get_active_llm_config
from app.llm.repair import JsonRepairError
from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.user import User
from app.security import complete_once, interrupt_once
from app.services.scheduler import get_due_practices, set_next_due, set_retry_block
from app.templates_setup import templates

router = APIRouter(prefix="/tasks", tags=["tasks"])


# --- Page ---


@router.get("/", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    error: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Task generation page."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    # Get recent logs
    result = await db.execute(
        select(ActivityLog).where(ActivityLog.user_id == user.id).order_by(ActivityLog.created_at.desc()).limit(10)
    )
    recent_logs = result.scalars().all()

    # Check if there's an active config
    active_config = await get_active_llm_config(db, user.id)

    # Get today's calendar schedule
    today_schedule = await get_day_schedule(db, user.id, date.today())
    now_available, now_policy, now_label, _ = await is_available(db, user.id, datetime.now(), 60, "active")

    # Get due practices
    due_practices = await get_due_practices(db, user.id, limit=8)

    return templates.TemplateResponse(
        request=request,
        name="tasks.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "recent_logs": recent_logs,
            "active_config": active_config,
            "error": error,
            "today_schedule": today_schedule,
            "now_available": now_available,
            "now_policy": now_policy,
            "now_label": now_label,
            "due_practices": due_practices,
            "active_nav": "tasks",
        },
    )


# --- API: Generate ---


@router.post("/generate")
async def generate_task_endpoint(
    request: Request,
    custom_prompt: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate a task via LLM and redirect to the tasks page."""
    locale = detect_locale(request, user.locale)

    # Get active LLM config
    active_config = await get_active_llm_config(db, user.id)
    if active_config is None:
        return RedirectResponse(
            url="/tasks/?error=No+active+LLM+provider+configured",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        await generate_task(
            db=db,
            user_id=user.id,
            llm_config=active_config,
            session_id=None,
            locale=locale,
            custom_prompt=custom_prompt if custom_prompt.strip() else None,
        )
    except JsonRepairError:
        return RedirectResponse(
            url="/tasks/?error=LLM+response+could+not+be+parsed+after+3+attempts.+Try+again.",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except ValueError as e:
        return RedirectResponse(
            url=f"/tasks/?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    except Exception:
        return RedirectResponse(
            url="/tasks/?error=LLM+request+failed.+Check+your+provider+configuration.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(url="/tasks/", status_code=status.HTTP_303_SEE_OTHER)


# --- API: Deterministic fallback (no LLM) ---


@router.post("/generate-deterministic")
async def generate_deterministic(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pick a task from due practices without LLM."""
    practices = await get_due_practices(db, user.id, limit=1)
    if not practices:
        return RedirectResponse(
            url="/tasks/?error=No+due+practices+found.+Enable+some+in+the+catalog.",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    p = practices[0]
    entity_id = uuid.UUID(p["entity_id"])

    # Verify entity exists
    ent_result = await db.execute(select(Entity).where(Entity.id == entity_id))
    if ent_result.scalar_one_or_none() is None:
        return RedirectResponse(
            url="/tasks/?error=Entity+not+found",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    log = ActivityLog(
        user_id=user.id,
        entity_id=entity_id,
        status="planned",
        selected_entity_name=p["entity_name"],
        selected_params={"intensity": 1, "source": "deterministic"},
        user_prompt="Deterministic fallback — no LLM",
    )
    db.add(log)
    await db.commit()

    return RedirectResponse(url="/tasks/", status_code=status.HTTP_303_SEE_OTHER)


# --- API: Complete / Interrupt ---


@router.post("/{log_id}/complete")
async def complete_task(
    request: Request,
    log_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a task as completed."""
    result = await db.execute(select(ActivityLog).where(ActivityLog.id == log_id))
    log = result.scalar_one_or_none()
    if log is None or log.user_id != user.id:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Idempotent completion
    result = await complete_once(db, log, user, on_task_completed)
    # Set next due for this practice only when the state actually changed
    if not result["idempotent"] and log.entity_id:
        await set_next_due(db, user.id, log.entity_id)
    await db.commit()

    return RedirectResponse(url="/tasks/", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/{log_id}/interrupt")
async def interrupt_task(
    request: Request,
    log_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a task as stopped (penalty)."""
    result = await db.execute(select(ActivityLog).where(ActivityLog.id == log_id))
    log = result.scalar_one_or_none()
    if log is None or log.user_id != user.id:
        raise HTTPException(status_code=404, detail="Activity not found")

    # Idempotent interruption
    result = await interrupt_once(db, log, user, on_task_interrupted)
    # Block retry only when the state actually changed
    if not result["idempotent"] and log.entity_id:
        await set_retry_block(db, user.id, log.entity_id)
    await db.commit()

    return RedirectResponse(url="/tasks/", status_code=status.HTTP_303_SEE_OTHER)
