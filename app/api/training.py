"""Training API: daily plan generation, subtask tracking, day analysis, log entries."""

import json
import re
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
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
from app.models.entity import Entity
from app.models.life import ScheduleRule
from app.models.opt_in import UserEntityOptIn
from app.models.training import TrainingDay
from app.models.training_log import TrainingLogEntry
from app.models.user import User
from app.params import normalize_schema, validate_params
from app.security import complete_once
from app.templates_setup import templates
from app.timeutils import local_today
from app.title_gen import generate_title

router = APIRouter(prefix="/training", tags=["training"])

# Allowlist for user-supplied journal entry types (audit fix: stored XSS via entry_type).
ENTRY_TYPES = {"fluid_intake", "micro_leak", "pressure_check", "general_note"}


def _get_today() -> date:
    return local_today()


@router.get("/builder", response_class=HTMLResponse)
async def training_builder_page(
    request: Request,
    user: User = Depends(get_current_user),
):
    """Interactive Training Routine & Posture Builder page (Step 35)."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    return templates.TemplateResponse(
        request=request,
        name="training_builder.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "active_nav": "training",
        },
    )


# === Page ===

_TIME_LABEL_RE = re.compile(r"(\d{1,2}):(\d{2})\s*(?:[–-]|до)\s*(\d{1,2}):(\d{2})")


def _parse_time_label(label: str | None) -> tuple[int, int] | None:
    """Parse "09:00" or "16:30–20:00" into (start_min, end_min); None if unparseable."""
    if not label:
        return None
    m = _TIME_LABEL_RE.search(label)
    if m:
        start = int(m.group(1)) * 60 + int(m.group(2))
        end = int(m.group(3)) * 60 + int(m.group(4))
    else:
        m2 = re.match(r"^(\d{1,2}):(\d{2})$", label.strip())
        if not m2:
            return None
        start = int(m2.group(1)) * 60 + int(m2.group(2))
        end = start + 60
    # Clamp to the day bounds (0..1440) so blocks never overflow the scale.
    start = max(0, min(start, 1439))
    end = max(start + 1, min(end, 1440))
    return start, end


def _plan_dict(day: TrainingDay, logs: list[ActivityLog], entries: list[TrainingLogEntry]) -> dict:
    """Bundle a training day with its tasks/journal for template rendering."""
    completed = sum(1 for lg in logs if lg.status == "completed")
    stopped = sum(1 for lg in logs if lg.status == "stopped")
    total = len(logs)
    next_day = None
    if day.next_day_suggestion:
        try:
            next_day = json.loads(day.next_day_suggestion)
        except (json.JSONDecodeError, TypeError):
            next_day = None
    return {
        "day": day,
        "logs": logs,
        "log_entries": entries,
        "completed": completed,
        "stopped": stopped,
        "total": total,
        "next_day": next_day,
    }


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
        .order_by(TrainingDay.created_at.asc())
    )
    training_days = list(result.scalars().all())

    plans: list[dict] = []
    all_entries: list[TrainingLogEntry] = []
    for day in training_days:
        logs_result = await db.execute(
            select(ActivityLog).where(ActivityLog.training_day_id == day.id).order_by(ActivityLog.created_at)
        )
        logs = list(logs_result.scalars().all())
        entries_result = await db.execute(
            select(TrainingLogEntry)
            .where(TrainingLogEntry.training_day_id == day.id)
            .order_by(TrainingLogEntry.sort_order, TrainingLogEntry.time_label)
        )
        entries = list(entries_result.scalars().all())
        all_entries.extend(entries)
        plans.append(_plan_dict(day, logs, entries))

    # Timeline: journal entries from all plans + today's schedule rules.
    timeline_blocks: list[dict] = []
    for entry in all_entries:
        span = _parse_time_label(entry.time_label)
        if span:
            timeline_blocks.append(
                {
                    "kind": "journal",
                    "start": span[0],
                    "end": span[1],
                    "label": entry.time_label,
                    "sub": entry.entry_type,
                    "value": entry.actual_value or entry.planned_value or "",
                }
            )
    sched_result = await db.execute(
        select(ScheduleRule)
        .where(
            ScheduleRule.user_id == user.id,
            ScheduleRule.is_active.is_(True),
            (ScheduleRule.day_of_week == today.weekday()) | (ScheduleRule.day_of_week == 7),
        )
        .order_by(ScheduleRule.start_time)
    )
    for rule in sched_result.scalars().all():
        start = rule.start_time.hour * 60 + rule.start_time.minute
        end = (rule.end_time.hour * 60 + rule.end_time.minute) if rule.end_time else min(start + 60, 1440)
        name = rule.entity.real_name if rule.entity else (rule.notes or rule.task_type)
        timeline_blocks.append(
            {
                "kind": "schedule",
                "start": start,
                "end": max(end, start + 1),
                "label": name,
                "sub": rule.task_type,
                "value": "",
            }
        )

    active_config = await get_active_llm_config(db, user.id)

    # Entities for manual task creation (ADR-106: opted-in + personal).
    ent_result = await db.execute(
        select(Entity)
        .outerjoin(UserEntityOptIn, UserEntityOptIn.entity_id == Entity.id)
        .where(
            (Entity.owner_id == user.id)
            | ((UserEntityOptIn.user_id == user.id) & UserEntityOptIn.is_opted_in.is_(True)),
        )
        .order_by(Entity.category, Entity.real_name)
    )
    create_entities = list(ent_result.scalars().all())

    return templates.TemplateResponse(
        request=request,
        name="training.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "training_days": training_days,
            "plans": plans,
            "active_config": active_config,
            "today": today,
            "timeline_blocks": timeline_blocks,
            "create_entities": create_entities,
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
    form = await request.form()
    plan_name = (form.get("name", "").strip())[:200] or None

    # Leftover empty plans (failed LLM attempts) must not block retry.
    existing_result = await db.execute(
        select(TrainingDay).where(TrainingDay.user_id == user.id, TrainingDay.target_date == today)
    )
    existing_days = list(existing_result.scalars().all())
    for existing_day in existing_days:
        logs_count = await db.execute(
            select(func.count(ActivityLog.id)).where(ActivityLog.training_day_id == existing_day.id)
        )
        entries_count = await db.execute(
            select(func.count(TrainingLogEntry.id)).where(TrainingLogEntry.training_day_id == existing_day.id)
        )
        if logs_count.scalar_one() == 0 and entries_count.scalar_one() == 0:
            await db.delete(existing_day)
            await db.flush()

    # Multiple plans per day are allowed — a new one is appended, not blocked.
    try:
        await generate_daily_plan(
            db=db,
            user_id=user.id,
            llm_config=active_config,
            target_date=today,
            locale=locale,
            name=plan_name,
        )
    except (JsonRepairError, ValueError) as e:
        # generate_daily_plan is transactional — nothing is persisted before
        # the LLM response is parsed and validated, so no rollback is needed.
        return RedirectResponse(url=f"/training?error={str(e)}", status_code=303)
    return RedirectResponse(url="/training", status_code=303)


# === Manual task creation in a training day (no LLM) ===


def _coerce_param(value: str | None, d: dict) -> object:
    """Coerce a form string into the typed value for a param definition."""
    if value is None or value == "":
        return None
    t = d.get("type")
    if t in ("integer", "decimal", "duration"):
        try:
            if t == "integer":
                return int(value)
            return float(value)
        except ValueError:
            return value  # let validator flag it
    if t == "boolean":
        return value.strip().lower() in ("1", "true", "yes", "on")
    if t == "multi_enum":
        return value
    return value


@router.post("/tasks")
async def create_manual_training_task(
    request: Request,
    entity_id: uuid.UUID = Form(...),
    training_day_id: str = Form(default=""),
    planned_comment: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a task manually inside a training day (ADR-106, no LLM).

    Accepts the same dynamic params form as POST /tasks/create (prefix
    ``param_``). The task is linked to the given ``training_day_id``; if the
    id is empty, the first training day of today is used (creating one if
    none exists).
    """
    locale = detect_locale(request, user.locale)
    today = _get_today()

    ent_result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user.id),
        )
    )
    entity = ent_result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    # Resolve the training day: explicit id, else today's first, else create one.
    training_day = None
    if training_day_id.strip():
        try:
            td_id = uuid.UUID(training_day_id.strip())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid training_day_id") from None
        td_result = await db.execute(select(TrainingDay).where(TrainingDay.id == td_id))
        training_day = td_result.scalar_one_or_none()
        if training_day is None or training_day.user_id != user.id:
            raise HTTPException(status_code=404, detail="Training day not found")
    else:
        td_result = await db.execute(
            select(TrainingDay)
            .where(TrainingDay.user_id == user.id, TrainingDay.target_date == today)
            .order_by(TrainingDay.created_at.asc())
        )
        training_day = td_result.scalars().first()
        if training_day is None:
            training_day = TrainingDay(user_id=user.id, target_date=today, status="active")
            db.add(training_day)
            await db.flush()

    try:
        defs = normalize_schema(entity.params_schema)
    except ValueError as e:
        return RedirectResponse(url=f"/training?error={str(e)}", status_code=303)

    form = await request.form()
    params: dict = {}
    multi_keys: list[str] = []
    for d in defs:
        key = d["key"]
        if d.get("type") == "multi_enum":
            multi_keys.append(key)
            continue
        raw = form.get(f"param_{key}")
        value = _coerce_param(raw, d)
        if value is None and d.get("type") == "enum" and d.get("allow_custom_value"):
            custom = form.get(f"param_{key}_custom")
            if custom:
                value = custom
        if value is not None:
            params[key] = value
    for key in multi_keys:
        values = form.getlist(f"param_{key}")
        if values:
            params[key] = values

    errors = validate_params(entity.params_schema, params)
    if errors:
        return RedirectResponse(url=f"/training?error={errors[0]}", status_code=303)

    title = generate_title(
        entity.real_name,
        params,
        schema=entity.params_schema,
        template=entity.task_template.get("template") if entity.task_template else None,
        locale=locale,
    )

    log = ActivityLog(
        user_id=user.id,
        entity_id=entity.id,
        status="planned",
        selected_entity_name=entity.real_name,
        selected_params=params,
        planned_comment=planned_comment.strip() or None,
        title_override=title if title != entity.real_name else None,
        user_prompt="Manual creation in training day (no LLM)",
        training_day_id=training_day.id,
    )
    db.add(log)
    await db.flush()

    return RedirectResponse(url="/training", status_code=303)


# === Toggle Subtask ===


@router.post("/tasks/{log_id}/subtasks/{sub_idx}/toggle")
async def toggle_subtask(
    log_id: uuid.UUID,
    sub_idx: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(ActivityLog).where(ActivityLog.id == log_id))
    log = result.scalar_one_or_none()
    if log is None or log.user_id != user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    # Audit: only a `pending` task may be completed — an interrupted (or already
    # completed) task must not grant XP/points. Uses the atomic idempotency guard.
    outcome = await complete_once(db, log, user, on_task_completed)
    if not outcome["idempotent"]:
        await db.flush()
    return RedirectResponse(url="/training", status_code=303)


# === Analyze Day ===


@router.post("/analyze")
async def analyze_day(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    locale = detect_locale(request, user.locale)
    form = await request.form()
    plan_id_str = form.get("training_day_id", "")
    if plan_id_str:
        try:
            plan_id = uuid.UUID(str(plan_id_str))
        except ValueError:
            plan_id = None
    else:
        plan_id = None
    if plan_id is None:
        today = _get_today()
        result = await db.execute(
            select(TrainingDay).where(TrainingDay.user_id == user.id, TrainingDay.target_date == today)
        )
        training_day = result.scalars().first()
    else:
        result = await db.execute(select(TrainingDay).where(TrainingDay.id == plan_id))
        training_day = result.scalar_one_or_none()
        if training_day is not None and training_day.user_id != user.id:
            training_day = None
    if training_day is None:
        return RedirectResponse(url="/training?error=No+training+day+found+for+today", status_code=303)
    active_config = await get_active_llm_config(db, user.id)
    if active_config is None:
        return RedirectResponse(url="/training?error=No+active+LLM+provider", status_code=303)
    try:
        await analyze_training_day(db=db, training_day=training_day, llm_config=active_config, locale=locale)
    except (JsonRepairError, ValueError) as e:
        # analyze_training_day is transactional — state is only mutated after
        # both LLM calls succeed, so no rollback is needed.
        return RedirectResponse(url=f"/training?error={str(e)}", status_code=303)
    return RedirectResponse(url="/training", status_code=303)


# === Log Entry: Reorder ===


@router.post("/log-entry/reorder")
async def reorder_log_entries(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Persist a new drag&drop order for journal entries of one training day."""
    payload = await request.json()
    training_day_id_str = payload.get("training_day_id")
    ids = payload.get("ids", [])
    if not training_day_id_str or not ids:
        raise HTTPException(status_code=400, detail="training_day_id and ids required")
    try:
        td_id = uuid.UUID(str(training_day_id_str))
        id_list = [uuid.UUID(str(i)) for i in ids]
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Invalid id format") from None

    td_result = await db.execute(select(TrainingDay).where(TrainingDay.id == td_id))
    td = td_result.scalar_one_or_none()
    if td is None or td.user_id != user.id:
        raise HTTPException(status_code=404, detail="Training day not found")

    result = await db.execute(
        select(TrainingLogEntry).where(
            TrainingLogEntry.training_day_id == td_id,
            TrainingLogEntry.user_id == user.id,
        )
    )
    by_id = {e.id: e for e in result.scalars().all()}
    if set(id_list) != set(by_id.keys()):
        raise HTTPException(status_code=400, detail="ids must match all entries of the day")
    for pos, eid in enumerate(id_list):
        by_id[eid].sort_order = pos
        db.add(by_id[eid])
    await db.flush()
    return {"status": "ok"}


# === Log Entry: Update ===


@router.post("/log-entry/{entry_id}")
async def update_log_entry(
    entry_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    td_str = form.get("training_day_id", "")
    time_label = form.get("time_label", "").strip()[:20]  # column is String(20)
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
        .order_by(TrainingLogEntry.sort_order.desc())
        .limit(1)
    )
    max_order = max_o.scalar_one_or_none() or 0

    # Audit fix: entry_type is stored and rendered in HTML — restrict to the allowlist.
    raw_type = form.get("entry_type", "general_note").strip()
    entry_type = raw_type if raw_type in ENTRY_TYPES else "general_note"

    entry = TrainingLogEntry(
        training_day_id=td_id,
        user_id=user.id,
        time_label=time_label,
        entry_type=entry_type,
        actual_value=(form.get("actual_value", "").strip()) or None,
        unit="text",
        notes=(form.get("notes", "").strip()) or None,
        sort_order=max_order + 1,
        is_extra=True,
    )
    db.add(entry)
    await db.commit()
    return HTMLResponse(_render_log_entry_row(entry))


# === Log Entry: Delete Extra ===


@router.delete("/log-entry/{entry_id}")
async def delete_log_entry(
    entry_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
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
        "fluid_intake": "Приём",
        "micro_leak": "Микро-слив",
        "pressure_check": "Давление",
        "general_note": "Заметка",
    }
    tl = labels.get(entry.entry_type, entry.entry_type)
    xc = "border-amber-300 dark:border-amber-700 bg-amber-50 dark:bg-amber-950/20" if entry.is_extra else ""
    db_btn = (
        f'<button hx-delete="/training/log-entry/{entry.id}" hx-target="closest .log-entry-row"'
        f' hx-swap="outerHTML" class="text-red-400 hover:text-red-600 text-xs leading-none px-1">✕</button>'
        if entry.is_extra
        else ""
    )
    unit_esc = _h.escape(entry.unit or "")
    return (
        f'<div class="log-entry-row flex items-start gap-3 p-3 rounded-lg border'
        f' border-slate-200 dark:border-slate-700 {xc}">'
        f'<div class="flex-shrink-0 w-20">'
        f'<span class="text-sm font-mono font-medium text-slate-700 dark:text-slate-300">'
        f"{_h.escape(entry.time_label)}</span>"
        f'<span class="block text-xs text-slate-400">{_h.escape(tl)}{" *" if entry.is_extra else ""}</span></div>'
        f'<div class="flex-shrink-0 w-24">'
        f'<span class="text-xs text-slate-400">{_h.escape(entry.planned_value or "—")} {unit_esc}</span></div>'
        f'<form hx-post="/training/log-entry/{entry.id}" hx-target="closest .log-entry-row" hx-swap="outerHTML"'
        f' class="flex-1 flex items-start gap-2">'
        f'<input type="text" name="actual_value" value="{_h.escape(entry.actual_value or "")}"'
        f' placeholder="Факт ({unit_esc})"'
        f' class="w-24 px-2 py-1 text-sm border border-slate-300 dark:border-slate-600'
        f' rounded bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100">'
        f'<input type="text" name="notes" value="{_h.escape(entry.notes or "")}"'
        f' placeholder="Ощущения, заметки..."'
        f' class="flex-1 px-2 py-1 text-sm border border-slate-300 dark:border-slate-600'
        f' rounded bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-100">'
        f'<button type="submit" class="px-3 py-1 bg-indigo-600 hover:bg-indigo-700'
        f' text-white text-xs font-medium rounded transition-colors">Сохранить</button></form>{db_btn}</div>'
    )
