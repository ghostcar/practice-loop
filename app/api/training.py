"""Training API: daily plan generation, subtask tracking, day analysis, log entries."""

import json
import uuid
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
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
from app.models.training_log import TrainingLogEntry
from app.models.user import User
from app.templates_setup import templates

router = APIRouter(prefix="/training", tags=["training"])


def _get_today() -> date:
    return datetime.now(UTC).date()


# === Page ===


@router.get("/", response_class=HTMLResponse)
async def training_page(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)
    today = _get_today()

    result = await db.execute(
        select(TrainingDay)
        .where(TrainingDay.user_id == user.id, TrainingDay.target_date == today)
        .order_by(TrainingDay.created_at.desc())
        .limit(1)
    )
    training_day = result.scalar_one_or_none()

    logs: list[ActivityLog] = []
    log_entries: list[TrainingLogEntry] = []
    if training_day:
        logs_result = await db.execute(
            select(ActivityLog)
            .where(ActivityLog.training_day_id == training_day.id)
            .order_by(ActivityLog.created_at)
        )
        logs = list(logs_result.scalars().all())
        entries_result = await db.execute(
            select(TrainingLogEntry)
            .where(TrainingLogEntry.training_day_id == training_day.id)
            .order_by(TrainingLogEntry.sort_order, TrainingLogEntry.time_label)
        )
        log_entries = list(entries_result.scalars().all())

    active_config = await get_active_llm_config(db, user.id)

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
            "request": request, "t": t, "user": user, "locale": locale, "theme": theme,
            "training_day": training_day, "logs": logs, "log_entries": log_entries,
            "active_config": active_config, "today": today, "next_day": next_day,
            "active_nav": "training",
        },
    )


# === Generate Plan ===


@router.post("/plan")
async def generate_plan(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    active_config = await get_active_llm_config(db, user.id)
    if active_config is None:
        return RedirectResponse(url="/training?error=No+active+LLM+provider+configured", status_code=303)
    today = _get_today()
    existing = await db.execute(
        select(TrainingDay).where(TrainingDay.user_id == user.id, TrainingDay.target_date == today)
    )
    if existing.scalar_one_or_none():
        return RedirectResponse(url="/training?error=Plan+already+exists+for+today", status_code=303)
    try:
        await generate_daily_plan(db=db, user_id=user.id, llm_config=active_config, target_date=today, locale=locale)
    except (JsonRepairError, ValueError) as e:
        return RedirectResponse(url=f"/training?error={str(e)}", status_code=303)
    return RedirectResponse(url="/training", status_code=303)


# === Toggle Subtask ===


@router.post("/tasks/{log_id}/subtasks/{sub_idx}/toggle")
async def toggle_subtask(
    log_id: uuid.UUID, sub_idx: int,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
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
    return RedirectResponse(url="/training", status_code=303)


# === Complete Training Task ===


@router.post("/tasks/{log_id}/complete")
async def complete_training_task(
    log_id: uuid.UUID,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ActivityLog).where(ActivityLog.id == log_id))
    log = result.scalar_one_or_none()
    if log is None or log.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    if log.status == "completed":
        return RedirectResponse(url="/training", status_code=303)
    log.status = "completed"
    db.add(log)
    await db.flush()
    await on_task_completed(db, user.id, log)
    return RedirectResponse(url="/training", status_code=303)


# === Analyze Day ===


@router.post("/analyze")
async def analyze_day(
    request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    today = _get_today()
    result = await db.execute(
        select(TrainingDay).where(TrainingDay.user_id == user.id, TrainingDay.target_date == today)
    )
    training_day = result.scalar_one_or_none()
    if training_day is None:
        return RedirectResponse(url="/training?error=No+training+day+found+for+today", status_code=303)
    active_config = await get_active_llm_config(db, user.id)
    if active_config is None:
        return RedirectResponse(url="/training?error=No+active+LLM+provider", status_code=303)
    try:
        await analyze_training_day(db=db, training_day=training_day, llm_config=active_config, locale=locale)
    except (JsonRepairError, ValueError) as e:
        return RedirectResponse(url=f"/training?error={str(e)}", status_code=303)
    return RedirectResponse(url="/training", status_code=303)


# === Log Entry: Update ===


@router.post("/log-entry/{entry_id}")
async def update_log_entry(
    entry_id: uuid.UUID, request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TrainingLogEntry).where(TrainingLogEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status_code=404, detail="Log entry not found")
    form = await request.form()
    entry.actual_value = (form.get("actual_value", "").strip()) or None
    entry.notes = (form.get("notes", "").strip()) or None
    db.add(entry)
    await db.commit()
    return HTMLResponse(_render_log_entry_row(entry))


# === Log Entry: Add Extra ===


@router.post("/log-entry")
async def add_extra_log_entry(
    request: Request,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    td_str = form.get("training_day_id", "")
    time_label = form.get("time_label", "").strip()
    if not td_str or not time_label:
        raise HTTPException(status_code=400, detail="training_day_id and time_label required")

    td_id = uuid.UUID(td_str)
    td_result = await db.execute(select(TrainingDay).where(TrainingDay.id == td_id))
    td = td_result.scalar_one_or_none()
    if td is None or td.user_id != user.id:
        raise HTTPException(status_code=404, detail="Training day not found")

    max_o = await db.execute(
        select(TrainingLogEntry.sort_order)
        .where(TrainingLogEntry.training_day_id == td_id)
        .order_by(TrainingLogEntry.sort_order.desc()).limit(1)
    )
    max_order = max_o.scalar_one_or_none() or 0

    entry = TrainingLogEntry(
        training_day_id=td_id, user_id=user.id, time_label=time_label,
        entry_type=form.get("entry_type", "general_note").strip(),
        actual_value=(form.get("actual_value", "").strip()) or None,
        unit="text", notes=(form.get("notes", "").strip()) or None,
        sort_order=max_order + 1, is_extra=True,
    )
    db.add(entry)
    await db.commit()
    return HTMLResponse(_render_log_entry_row(entry))


# === Log Entry: Delete Extra ===


@router.delete("/log-entry/{entry_id}")
async def delete_log_entry(
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(TrainingLogEntry).where(TrainingLogEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None or entry.user_id != user.id:
        raise HTTPException(status_code=404, detail="Log entry not found")
    if not entry.is_extra:
        raise HTTPException(status_code=400, detail="Only extra entries can be deleted")
    await db.delete(entry)
    await db.commit()
    return HTMLResponse("")


# === HTML Renderer ===


def _render_log_entry_row(entry: TrainingLogEntry) -> str:
    import html as _h
    labels = {
        "fluid_intake": "Приём", "micro_leak": "Микро-слив",
        "pressure_check": "Давление", "general_note": "Заметка",
    }
    tl = labels.get(entry.entry_type, entry.entry_type)
    xc = "border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/20" if entry.is_extra else ""
    db_btn = (
        f"<button hx-delete=\"/training/log-entry/{entry.id}\" hx-target=\"closest .log-entry-row\""
        f" hx-swap=\"outerHTML\" class=\"text-red-400 hover:text-red-600 text-xs leading-none px-1\">✕</button>"
        if entry.is_extra else ""
    )
    return (
        f"<div class=\"log-entry-row flex items-start gap-3 p-3 rounded-lg border"
        f" border-slate-200 dark:border-slate-700 {xc}\">"
        f"<div class=\"flex-shrink-0 w-20\">"
        f"<span class=\"text-sm font-mono font-medium text-slate-700 dark:text-slate-300\">"
        f"{_h.escape(entry.time_label)}</span>"
        f"<span class=\"block text-xs text-slate-400\">{tl}{' *' if entry.is_extra else ''}</span></div>"
        f"<div class=\"flex-shrink-0 w-24\">"
        f"<span class=\"text-xs text-slate-400\">{_h.escape(entry.planned_value or '—')} {entry.unit or ''}</span></div>"  # noqa: E501
        f"<form hx-post=\"/training/log-entry/{entry.id}\" hx-target=\"closest .log-entry-row\" hx-swap=\"outerHTML\""
        f" class=\"flex-1 flex items-start gap-2\">"
        f"<input type=\"text\" name=\"actual_value\" value=\"{_h.escape(entry.actual_value or '')}\""
        f" placeholder=\"Факт ({entry.unit or ''})\""
        f" class=\"w-24 px-2 py-1 text-sm border border-slate-300 dark:border-slate-600"
        f" rounded bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100\">"
        f"<input type=\"text\" name=\"notes\" value=\"{_h.escape(entry.notes or '')}\""
        f" placeholder=\"Ощущения, заметки...\""
        f" class=\"flex-1 px-2 py-1 text-sm border border-slate-300 dark:border-slate-600"
        f" rounded bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100\">"
        f"<button type=\"submit\" class=\"px-3 py-1 bg-indigo-600 hover:bg-indigo-700"
        f" text-white text-xs font-medium rounded transition-colors\">Сохранить</button></form>{db_btn}</div>"
    )
