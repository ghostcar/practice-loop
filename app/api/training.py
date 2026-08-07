"""Training API: daily plan generation, subtask tracking, day analysis."""

import json
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.auth import get_current_user
from app.database import get_db
from app.gamification.handler import on_task_completed
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.llm.pipeline import analyze_training_day, generate_daily_plan, get_active_llm_config
from app.llm.repair import JsonRepairError
from app.models.activity_log import ActivityLog
from app.models.training import TrainingDay
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(prefix="/training", tags=["training"])


def _get_today() -> date:
    return datetime.now(UTC).date()


# --- Page ---


@router.get("/", response_class=HTMLResponse)
async def training_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Main training page — shows today's plan or prompt to create one."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    today = _get_today()

    # Find or create today's training day
    result = await db.execute(
        select(TrainingDay)
        .where(
            TrainingDay.user_id == user.id,
            TrainingDay.target_date == today,
        )
        .order_by(TrainingDay.created_at.desc())
        .limit(1)
    )
    training_day = result.scalar_one_or_none()

    # Get associated activity logs
    logs: list[ActivityLog] = []
    if training_day:
        logs_result = await db.execute(
            select(ActivityLog).where(ActivityLog.training_day_id == training_day.id).order_by(ActivityLog.created_at)
        )
        logs = list(logs_result.scalars().all())

    active_config = await get_active_llm_config(db, user.id)

    # Parse next_day_suggestion for the template
    next_day = None
    if training_day and training_day.next_day_suggestion:
        try:
            next_day = json.loads(training_day.next_day_suggestion)
        except (json.JSONDecodeError, TypeError):
            next_day = None

    return templates.TemplateResponse(
        request=request,
        name="training.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "training_day": training_day,
            "logs": logs,
            "active_config": active_config,
            "today": today,
            "next_day": next_day,
            "active_nav": "training",
        },
    )


# --- API: Generate Plan ---


@router.post("/plan")
async def generate_plan(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate today's training plan via LLM."""
    locale = detect_locale(request, user.locale)

    active_config = await get_active_llm_config(db, user.id)
    if active_config is None:
        return RedirectResponse(
            url="/training?error=No+active+LLM+provider+configured",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    today = _get_today()

    # Check if there's already a training day for today
    existing = await db.execute(
        select(TrainingDay).where(
            TrainingDay.user_id == user.id,
            TrainingDay.target_date == today,
        )
    )
    if existing.scalar_one_or_none():
        return RedirectResponse(
            url="/training?error=Plan+already+exists+for+today",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        await generate_daily_plan(
            db=db,
            user_id=user.id,
            llm_config=active_config,
            target_date=today,
            locale=locale,
        )
    except (JsonRepairError, ValueError) as e:
        return RedirectResponse(
            url=f"/training?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(url="/training", status_code=status.HTTP_303_SEE_OTHER)


# --- API: Toggle Subtask ---


@router.post("/tasks/{log_id}/subtasks/{sub_idx}/toggle")
async def toggle_subtask(
    log_id: uuid.UUID,
    sub_idx: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Toggle a subtask's done status."""
    result = await db.execute(select(ActivityLog).where(ActivityLog.id == log_id))
    log = result.scalar_one_or_none()
    if log is None or log.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    if not log.subtasks or sub_idx >= len(log.subtasks):
        raise HTTPException(status_code=404, detail="Subtask not found")

    log.subtasks[sub_idx]["is_done"] = not log.subtasks[sub_idx].get("is_done", False)
    flag_modified(log, "subtasks")
    db.add(log)
    await db.flush()

    return RedirectResponse(url="/training", status_code=status.HTTP_303_SEE_OTHER)


# --- API: Complete Training Task ---


@router.post("/tasks/{log_id}/complete")
async def complete_training_task(
    log_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a training task as completed and award XP."""
    result = await db.execute(select(ActivityLog).where(ActivityLog.id == log_id))
    log = result.scalar_one_or_none()
    if log is None or log.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")

    if log.status == "completed":
        return RedirectResponse(url="/training", status_code=status.HTTP_303_SEE_OTHER)

    log.status = "completed"
    db.add(log)
    await db.flush()

    # Award XP via gamification (training mode: no achievements/streaks)
    await on_task_completed(db, user.id, log)

    return RedirectResponse(url="/training", status_code=status.HTTP_303_SEE_OTHER)


# --- API: Analyze Day ---


@router.post("/analyze")
async def analyze_day(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Run end-of-day analysis via LLM."""
    locale = detect_locale(request, user.locale)
    today = _get_today()

    result = await db.execute(
        select(TrainingDay).where(
            TrainingDay.user_id == user.id,
            TrainingDay.target_date == today,
        )
    )
    training_day = result.scalar_one_or_none()
    if training_day is None:
        return RedirectResponse(
            url="/training?error=No+training+day+found+for+today",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    active_config = await get_active_llm_config(db, user.id)
    if active_config is None:
        return RedirectResponse(
            url="/training?error=No+active+LLM+provider",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    try:
        await analyze_training_day(
            db=db,
            training_day=training_day,
            llm_config=active_config,
            locale=locale,
        )
    except (JsonRepairError, ValueError) as e:
        return RedirectResponse(
            url=f"/training?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

    return RedirectResponse(url="/training", status_code=status.HTTP_303_SEE_OTHER)
