"""Tasks service — all business logic for task generation, creation, completion.

Extracted from app/api/tasks.py (ADR-170).  HTTP layer stays thin.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.gamification.handler import on_task_completed, on_task_interrupted
from app.llm.pipeline import generate_task, generate_weekly_tasks, get_active_llm_config
from app.models.activity_log import ActivityLog
from app.models.body_part import TaskBodyTarget
from app.models.entity import Entity
from app.models.llm_config import LLMProviderConfig
from app.models.opt_in import UserEntityOptIn
from app.models.task_history import ActivityTaskHistory
from app.models.task_inventory import TaskInventoryUsage
from app.models.task_location import TaskLocationUsage
from app.models.task_status import PLANNED, STATUS_TRANSITIONS
from app.models.user import User
from app.params import normalize_schema, validate_params
from app.security import complete_once, interrupt_once
from app.services.dead_mans_switch import record_activity_heartbeat
from app.services.errors import NotFoundError
from app.services.scheduler import get_due_practices, set_next_due, set_retry_block
from app.timeutils import local_day_bounds, local_today
from app.title_gen import generate_title

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Page context
# ─────────────────────────────────────────────────────────────────────────────


async def get_tasks_page_context(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    status_filter: str | None = None,
    body_part_id: str | None = None,
    location_id: str | None = None,
    inventory_item_id: str | None = None,
    attention: bool = False,
) -> dict:
    """Build tasks page context with filters, stats, entities."""
    from app.services.calendar_service import get_day_schedule, is_available
    from app.services.scheduler import get_due_practices

    query = select(ActivityLog).where(ActivityLog.user_id == user_id)

    if status_filter and status_filter != "all":
        query = query.where(ActivityLog.status == status_filter)

    if body_part_id:
        bp_uuid = uuid.UUID(body_part_id)
        query = query.where(
            ActivityLog.id.in_(select(TaskBodyTarget.activity_log_id).where(TaskBodyTarget.body_part_id == bp_uuid))
        )

    if location_id:
        loc_uuid = uuid.UUID(location_id)
        query = query.where(
            ActivityLog.id.in_(
                select(TaskLocationUsage.activity_log_id).where(TaskLocationUsage.location_id == loc_uuid)
            )
        )

    if inventory_item_id:
        inv_uuid = uuid.UUID(inventory_item_id)
        query = query.where(
            ActivityLog.id.in_(
                select(TaskInventoryUsage.activity_log_id).where(TaskInventoryUsage.inventory_item_id == inv_uuid)
            )
        )

    if attention:
        today_start, _ = local_day_bounds(local_today())
        query = query.where(
            ((ActivityLog.scheduled_at < today_start) & ActivityLog.status.in_(["planned", "in_progress"]))
            | (ActivityLog.status == "review_needed")
        )

    result = await db.execute(query.order_by(ActivityLog.created_at.desc()).limit(20))
    recent_logs = result.scalars().all()

    history_result = (
        await db.execute(
            select(ActivityTaskHistory)
            .where(ActivityTaskHistory.task_id.in_([log.id for log in recent_logs]))
            .order_by(ActivityTaskHistory.changed_at.desc())
        )
        if recent_logs else None
    )
    task_histories: dict[uuid.UUID, list[ActivityTaskHistory]] = {log.id: [] for log in recent_logs}
    if history_result is not None:
        for event in history_result.scalars().all():
            task_histories[event.task_id].append(event)

    stats_result = await db.execute(
        select(ActivityLog.status, func.count()).where(ActivityLog.user_id == user_id).group_by(ActivityLog.status)
    )
    status_stats = {row[0]: row[1] for row in stats_result.all()}

    active_config = await get_active_llm_config(db, user_id)

    # Auto-seed LLM presets if none exist (ADR-179: Omniroute first)
    if active_config is None:
        existing_cfg = await db.execute(
            select(LLMProviderConfig).where(LLMProviderConfig.user_id == user_id).limit(1)
        )
        if not existing_cfg.scalar_one_or_none():
            from app.seed import seed_llm_presets

            await seed_llm_presets(db, user_id=user_id)
            active_config = await get_active_llm_config(db, user_id)

    from app.timeutils import local_today as _lt
    today_schedule = await get_day_schedule(db, user_id, _lt())
    now_available, now_policy, now_label, _ = await is_available(db, user_id, datetime.now(UTC), 60, "active")

    due_practices = await get_due_practices(db, user_id, limit=8)

    # Entities for manual task creation
    ent_result = await db.execute(
        select(Entity)
        .outerjoin(UserEntityOptIn, UserEntityOptIn.entity_id == Entity.id)
        .where(
            (Entity.owner_id == user_id)
            | ((UserEntityOptIn.user_id == user_id) & UserEntityOptIn.is_opted_in.is_(True)),
        )
        .order_by(Entity.category, Entity.real_name)
    )
    create_entities = list(ent_result.scalars().all())
    create_entities = [
        {
            "id": str(e.id),
            "name": e.real_name,
            "category": (e.category_rel.title if e.category_rel else e.category) or "",
            "schema": normalize_schema(e.params_schema),
        }
        for e in create_entities
    ]

    return {
        "recent_logs": recent_logs,
        "task_histories": task_histories,
        "active_config": active_config,
        "today_schedule": today_schedule,
        "now_available": now_available,
        "now_policy": now_policy,
        "now_label": now_label,
        "due_practices": due_practices,
        "status_stats": status_stats,
        "create_entities": create_entities,
        "next_actions": {src: sorted(dst) for src, dst in STATUS_TRANSITIONS.items()},
    }


# ─────────────────────────────────────────────────────────────────────────────
# LLM generation
# ─────────────────────────────────────────────────────────────────────────────


async def execute_llm_generation(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    locale: str,
    custom_prompt: str | None = None,
    body_part_id: str | None = None,
    location_id: str | None = None,
    inventory_item_id: str | None = None,
) -> None:
    """Generate a task via LLM. Raises ValueError or JsonRepairError on failure."""
    active_config = await get_active_llm_config(db, user_id)
    if active_config is None:
        raise ValueError("No active LLM provider configured")

    await generate_task(
        db=db,
        user_id=user_id,
        llm_config=active_config,
        session_id=None,
        locale=locale,
        custom_prompt=custom_prompt,
        body_part_id=body_part_id,
        location_id=location_id,
        inventory_item_id=inventory_item_id,
    )


async def execute_deterministic_task(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Pick a task from due practices without LLM. Raises ValueError if no practices."""
    practices = await get_due_practices(db, user_id, limit=1)
    if not practices:
        raise ValueError("No due practices found. Enable some in the catalog.")

    p = practices[0]
    entity_id = uuid.UUID(p["entity_id"])

    ent_result = await db.execute(select(Entity).where(Entity.id == entity_id))
    if ent_result.scalar_one_or_none() is None:
        raise ValueError("Entity not found")

    log = ActivityLog(
        user_id=user_id,
        entity_id=entity_id,
        status=PLANNED,
        selected_entity_name=p["entity_name"],
        selected_params={"intensity": 1, "source": "deterministic"},
        user_prompt="Deterministic fallback — no LLM",
    )
    db.add(log)


async def execute_weekly_generation(
    db: AsyncSession, user_id: uuid.UUID, *, locale: str, days: int = 7,
) -> None:
    """Batch-plan tasks for upcoming days. Raises ValueError or JsonRepairError."""
    llm_config = await get_active_llm_config(db, user_id)
    if llm_config is None:
        raise ValueError("No active LLM provider configured")

    await generate_weekly_tasks(db, user_id, llm_config, locale=locale, days=days)


# ─────────────────────────────────────────────────────────────────────────────
# Manual task creation
# ─────────────────────────────────────────────────────────────────────────────


async def create_manual_task_from_form(
    db: AsyncSession,
    user_id: uuid.UUID,
    entity_id: uuid.UUID,
    *,
    form_data: dict,
    planned_comment: str,
    locale: str,
) -> None:
    """Create a task manually from the dynamic params form (no LLM)."""
    ent_result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user_id),
        )
    )
    entity = ent_result.scalar_one_or_none()
    if entity is None:
        raise NotFoundError("Entity not found")

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
        values = form_data.getlist(f"param_{key}")
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
        status=PLANNED,
        selected_entity_name=entity.real_name,
        selected_params=params,
        planned_comment=planned_comment.strip() or None,
        title_override=title if title != entity.real_name else None,
        user_prompt="Manual creation (no LLM)",
    )
    db.add(log)


# ─────────────────────────────────────────────────────────────────────────────
# Entity lookup for params form
# ─────────────────────────────────────────────────────────────────────────────


async def get_entity_for_params(
    db: AsyncSession, entity_id: uuid.UUID, user_id: uuid.UUID,
) -> tuple[Entity, list[dict]]:
    """Get entity and normalized param defs for the params form. Raises ValueError if not found."""
    ent_result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user_id),
        )
    )
    entity = ent_result.scalar_one_or_none()
    if entity is None:
        raise NotFoundError("Entity not found")

    try:
        defs = normalize_schema(entity.params_schema)
    except ValueError:
        defs = []

    return entity, defs


# ─────────────────────────────────────────────────────────────────────────────
# Complete / Interrupt
# ─────────────────────────────────────────────────────────────────────────────


async def complete_task(db: AsyncSession, log_id: uuid.UUID, user: User) -> dict:
    """Mark a task as completed. Returns result dict."""
    result = await db.execute(select(ActivityLog).where(ActivityLog.id == log_id))
    log = result.scalar_one_or_none()
    if log is None or log.user_id != user.id:
        raise ValueError("Activity not found")

    outcome = await complete_once(db, log, user, on_task_completed)
    if not outcome["idempotent"] and log.entity_id:
        await set_next_due(db, user.id, log.entity_id)
        await record_activity_heartbeat(db, user.id, switch_type="daily_task")
    return outcome


async def interrupt_task(db: AsyncSession, log_id: uuid.UUID, user: User) -> dict:
    """Mark a task as stopped (penalty). Returns result dict."""
    result = await db.execute(select(ActivityLog).where(ActivityLog.id == log_id))
    log = result.scalar_one_or_none()
    if log is None or log.user_id != user.id:
        raise ValueError("Activity not found")

    outcome = await interrupt_once(db, log, user, on_task_interrupted)
    if not outcome["idempotent"] and log.entity_id:
        await set_retry_block(db, user.id, log.entity_id)
    return outcome
