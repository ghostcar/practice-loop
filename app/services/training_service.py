"""Training API — Business Logic Service Layer.

Extracted from app/api/training.py (ADR-166) to keep routers thin:
all CRUD, validation, serialization, and domain queries live here.

Public API:
  - get_training_page_context / get_adaptive_page_context
  - generate_plan / create_manual_task / toggle_subtask / complete_task / analyze_day
  - reorder_log_entries / update_log_entry / add_extra_log_entry / delete_log_entry
  - create_adaptive_program / log_step_feedback
  - render_log_entry_row / plan_dict / parse_time_label / coerce_param
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.life import ScheduleRule
from app.models.opt_in import UserEntityOptIn
from app.models.training import TrainingDay
from app.models.training_log import TrainingLogEntry
from app.services.errors import NotFoundError
from app.timeutils import local_today

# Allowlist for user-supplied journal entry types (audit fix: stored XSS via entry_type).
ENTRY_TYPES = {"fluid_intake", "micro_leak", "pressure_check", "general_note"}

_TIME_LABEL_RE = re.compile(r"(\d{1,2}):\d{2}\s*(?:[–-]|до)\s*(\d{1,2}):\d{2}")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def get_today() -> date:
    return local_today()


def parse_time_label(label: str | None) -> tuple[int, int] | None:
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
    start = max(0, min(start, 1439))
    end = max(start + 1, min(end, 1440))
    return start, end


def plan_dict(day: TrainingDay, logs: list[ActivityLog], entries: list[TrainingLogEntry]) -> dict:
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


def coerce_param(value: str | None, d: dict) -> object:
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
            return value
    if t == "boolean":
        return value.strip().lower() in ("1", "true", "yes", "on")
    if t == "multi_enum":
        return value
    return value


def render_log_entry_row(entry: TrainingLogEntry) -> str:
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


# ─────────────────────────────────────────────────────────────────────────────
# Page context builder
# ─────────────────────────────────────────────────────────────────────────────


async def get_training_page_context(db: AsyncSession, user) -> dict:
    from app.llm.pipeline import get_active_llm_config

    today = get_today()

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
        plans.append(plan_dict(day, logs, entries))

    timeline_blocks: list[dict] = []
    for entry in all_entries:
        span = parse_time_label(entry.time_label)
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

    return {
        "training_days": training_days,
        "plans": plans,
        "active_config": active_config,
        "today": today,
        "timeline_blocks": timeline_blocks,
        "create_entities": create_entities,
        "active_nav": "training",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Plan generation
# ─────────────────────────────────────────────────────────────────────────────


async def generate_plan(db: AsyncSession, user_id: uuid.UUID, plan_name: str | None, locale: str) -> None:
    from app.llm.pipeline import generate_daily_plan, get_active_llm_config

    active_config = await get_active_llm_config(db, user_id)
    if active_config is None:
        raise ValueError("No active LLM provider configured")
    today = get_today()

    existing_result = await db.execute(
        select(TrainingDay).where(TrainingDay.user_id == user_id, TrainingDay.target_date == today)
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

    await generate_daily_plan(
        db=db,
        user_id=user_id,
        llm_config=active_config,
        target_date=today,
        locale=locale,
        name=plan_name,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Manual task creation
# ─────────────────────────────────────────────────────────────────────────────


async def create_manual_task(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    entity_id: uuid.UUID,
    training_day_id: str,
    planned_comment: str,
    form_data: dict,
    locale: str,
) -> None:
    from app.params import normalize_schema, validate_params
    from app.title_gen import generate_title

    today = get_today()

    ent_result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user_id),
        )
    )
    entity = ent_result.scalar_one_or_none()
    if entity is None:
        raise NotFoundError("Entity not found")

    training_day = None
    if training_day_id.strip():
        try:
            td_id = uuid.UUID(training_day_id.strip())
        except ValueError:
            raise ValueError("Invalid training_day_id") from None
        td_result = await db.execute(select(TrainingDay).where(TrainingDay.id == td_id))
        training_day = td_result.scalar_one_or_none()
        if training_day is None or training_day.user_id != user_id:
            raise NotFoundError("Training day not found")
    else:
        td_result = await db.execute(
            select(TrainingDay)
            .where(TrainingDay.user_id == user_id, TrainingDay.target_date == today)
            .order_by(TrainingDay.created_at.asc())
        )
        training_day = td_result.scalars().first()
        if training_day is None:
            training_day = TrainingDay(user_id=user_id, target_date=today, status="active")
            db.add(training_day)
            await db.flush()

    try:
        defs = normalize_schema(entity.params_schema)
    except ValueError as e:
        raise ValueError(str(e)) from None

    params: dict = {}
    multi_keys: list[str] = []
    for d in defs:
        key = d["key"]
        if d.get("type") == "multi_enum":
            multi_keys.append(key)
            continue
        raw = form_data.get(f"param_{key}")
        value = coerce_param(raw, d)
        if value is None and d.get("type") == "enum" and d.get("allow_custom_value"):
            custom = form_data.get(f"param_{key}_custom")
            if custom:
                value = custom
        if value is not None:
            params[key] = value
    for key in multi_keys:
        if hasattr(form_data, "getlist"):
            values = form_data.getlist(f"param_{key}")
        else:
            values = form_data.get(f"param_{key}", [])
        if values:
            params[key] = values

    errors = validate_params(entity.params_schema, params)
    if errors:
        raise ValueError(errors[0])

    title = generate_title(
        entity.real_name,
        params,
        schema=entity.params_schema,
        template=entity.task_template.get("template") if entity.task_template else None,
        locale=locale,
    )

    log = ActivityLog(
        user_id=user_id,
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


# ─────────────────────────────────────────────────────────────────────────────
# Task operations
# ─────────────────────────────────────────────────────────────────────────────


async def toggle_subtask(db: AsyncSession, user_id: uuid.UUID, log_id: uuid.UUID, sub_idx: int) -> None:
    result = await db.execute(select(ActivityLog).where(ActivityLog.id == log_id))
    log = result.scalar_one_or_none()
    if log is None or log.user_id != user_id:
        raise NotFoundError("Task not found")
    if not log.subtasks or sub_idx >= len(log.subtasks):
        raise NotFoundError("Subtask not found")
    log.subtasks[sub_idx]["is_done"] = not log.subtasks[sub_idx].get("is_done", False)
    flag_modified(log, "subtasks")
    db.add(log)
    await db.flush()


async def complete_task(db: AsyncSession, user_id: uuid.UUID, log_id: uuid.UUID) -> dict:
    from app.gamification.handler import on_task_completed
    from app.models.user import User
    from app.security import complete_once

    result = await db.execute(select(ActivityLog).where(ActivityLog.id == log_id))
    log = result.scalar_one_or_none()
    if log is None or log.user_id != user_id:
        raise NotFoundError("Task not found")
    user_obj = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
    if user_obj is None:
        raise NotFoundError("User not found")
    outcome = await complete_once(db, log, user_obj, on_task_completed)
    if not outcome["idempotent"]:
        await db.flush()
    return outcome


async def analyze_day(db: AsyncSession, user_id: uuid.UUID, plan_id: uuid.UUID | None, locale: str) -> None:
    from app.llm.pipeline import analyze_training_day, get_active_llm_config

    if plan_id is None:
        today = get_today()
        result = await db.execute(
            select(TrainingDay).where(TrainingDay.user_id == user_id, TrainingDay.target_date == today)
        )
        training_day = result.scalars().first()
    else:
        result = await db.execute(select(TrainingDay).where(TrainingDay.id == plan_id))
        training_day = result.scalar_one_or_none()
        if training_day is not None and training_day.user_id != user_id:
            training_day = None
    if training_day is None:
        raise ValueError("No training day found for today")
    active_config = await get_active_llm_config(db, user_id)
    if active_config is None:
        raise ValueError("No active LLM provider")
    await analyze_training_day(db=db, training_day=training_day, llm_config=active_config, locale=locale)


# ─────────────────────────────────────────────────────────────────────────────
# Log entry CRUD
# ─────────────────────────────────────────────────────────────────────────────


async def reorder_log_entries(db: AsyncSession, user_id: uuid.UUID, td_id: uuid.UUID, id_list: list[uuid.UUID]) -> None:
    td_result = await db.execute(select(TrainingDay).where(TrainingDay.id == td_id))
    td = td_result.scalar_one_or_none()
    if td is None or td.user_id != user_id:
        raise NotFoundError("Training day not found")

    result = await db.execute(
        select(TrainingLogEntry).where(
            TrainingLogEntry.training_day_id == td_id,
            TrainingLogEntry.user_id == user_id,
        )
    )
    by_id = {e.id: e for e in result.scalars().all()}
    if set(id_list) != set(by_id.keys()):
        raise ValueError("ids must match all entries of the day")
    for pos, eid in enumerate(id_list):
        by_id[eid].sort_order = pos
        db.add(by_id[eid])
    await db.flush()


async def update_log_entry(
    db: AsyncSession,
    user_id: uuid.UUID,
    entry_id: uuid.UUID,
    form_data: dict,
) -> TrainingLogEntry:
    result = await db.execute(select(TrainingLogEntry).where(TrainingLogEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None or entry.user_id != user_id:
        raise NotFoundError("Log entry not found")
    entry.actual_value = (form_data.get("actual_value", "").strip()) or None
    entry.notes = (form_data.get("notes", "").strip()) or None
    db.add(entry)
    await db.flush()
    return entry


async def add_extra_log_entry(
    db: AsyncSession, *, user_id: uuid.UUID, td_id: uuid.UUID, time_label: str, form_data: dict
) -> TrainingLogEntry:
    td_result = await db.execute(select(TrainingDay).where(TrainingDay.id == td_id))
    td = td_result.scalar_one_or_none()
    if td is None or td.user_id != user_id:
        raise NotFoundError("Training day not found")

    max_o = await db.execute(
        select(TrainingLogEntry.sort_order)
        .where(TrainingLogEntry.training_day_id == td_id)
        .order_by(TrainingLogEntry.sort_order.desc())
        .limit(1)
    )
    max_order = max_o.scalar_one_or_none() or 0

    raw_type = form_data.get("entry_type", "general_note").strip()
    entry_type = raw_type if raw_type in ENTRY_TYPES else "general_note"

    entry = TrainingLogEntry(
        training_day_id=td_id,
        user_id=user_id,
        time_label=time_label[:20],
        entry_type=entry_type,
        actual_value=(form_data.get("actual_value", "").strip()) or None,
        unit="text",
        notes=(form_data.get("notes", "").strip()) or None,
        sort_order=max_order + 1,
        is_extra=True,
    )
    db.add(entry)
    await db.flush()
    return entry


async def delete_log_entry(db: AsyncSession, user_id: uuid.UUID, entry_id: uuid.UUID) -> None:
    result = await db.execute(select(TrainingLogEntry).where(TrainingLogEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None or entry.user_id != user_id:
        raise NotFoundError("Log entry not found")
    if not entry.is_extra:
        raise ValueError("Only extra entries can be deleted")
    await db.delete(entry)
    await db.flush()


# ─────────────────────────────────────────────────────────────────────────────
# Adaptive training
# ─────────────────────────────────────────────────────────────────────────────


async def get_adaptive_page_context(db: AsyncSession, user) -> dict:
    from sqlalchemy.orm import selectinload

    from app.models.adaptive_training import AdaptiveProgram

    programs = (
        (
            await db.execute(
                select(AdaptiveProgram)
                .options(selectinload(AdaptiveProgram.steps))
                .where(AdaptiveProgram.user_id == user.id)
                .order_by(AdaptiveProgram.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return {"programs": programs, "active_nav": "training"}


async def create_adaptive_program(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    title: str,
    focus_domain: str,
    total_days: int,
    difficulty_level: int,
) -> None:
    from app.agent.training_adaptive import create_adaptive_program as _create

    await _create(
        user_id=user_id,
        title=title,
        focus_domain=focus_domain,
        total_days=total_days,
        difficulty_level=difficulty_level,
        db=db,
    )


async def log_step_feedback(
    db: AsyncSession,
    *,
    step_id: uuid.UUID,
    comfort_score: int,
    actual_minutes: int,
    notes: str,
    user_id: uuid.UUID,
) -> None:
    from app.agent.training_adaptive import log_step_feedback_and_adapt

    await log_step_feedback_and_adapt(
        step_id=step_id,
        comfort_score=comfort_score,
        actual_minutes=actual_minutes,
        notes=notes,
        user_id=user_id,
        db=db,
    )
