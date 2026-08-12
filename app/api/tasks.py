import logging
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.calendar import get_day_schedule, is_available
from app.auth import get_current_user
from app.database import get_db
from app.gamification.handler import on_task_completed, on_task_interrupted
from app.i18n import get_translations
from app.i18n.helpers import detect_locale, detect_theme
from app.llm.pipeline import generate_task, generate_weekly_tasks, get_active_llm_config
from app.llm.repair import JsonRepairError
from app.models.activity_log import ActivityLog
from app.models.body_part import TaskBodyTarget
from app.models.entity import Entity
from app.models.opt_in import UserEntityOptIn
from app.models.task_inventory import TaskInventoryUsage
from app.models.task_location import TaskLocationUsage
from app.models.task_status import PLANNED, STATUS_TRANSITIONS
from app.models.user import User
from app.params import normalize_schema, validate_params
from app.security import complete_once, interrupt_once
from app.services.scheduler import get_due_practices, set_next_due, set_retry_block
from app.templates_setup import templates
from app.title_gen import generate_title

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tasks", tags=["tasks"])


# --- Page ---


@router.get("/", response_class=HTMLResponse)
async def tasks_page(
    request: Request,
    error: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    body_part_id: str | None = Query(None),
    location_id: str | None = Query(None),
    inventory_item_id: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Task generation page."""
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    # Build filtered query
    query = select(ActivityLog).where(ActivityLog.user_id == user.id)

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

    # Get recent logs
    result = await db.execute(query.order_by(ActivityLog.created_at.desc()).limit(20))
    recent_logs = result.scalars().all()

    # Status statistics (over ALL user tasks, not just the filtered page)
    stats_result = await db.execute(
        select(ActivityLog.status, func.count()).where(ActivityLog.user_id == user.id).group_by(ActivityLog.status)
    )
    status_stats = {row[0]: row[1] for row in stats_result.all()}

    # Check if there's an active config
    active_config = await get_active_llm_config(db, user.id)

    # Get today's calendar schedule
    today_schedule = await get_day_schedule(db, user.id, date.today())
    now_available, now_policy, now_label, _ = await is_available(db, user.id, datetime.now(), 60, "active")

    # Get due practices
    due_practices = await get_due_practices(db, user.id, limit=8)

    # Entities for manual task creation (opted-in or owned, with normalized schemas)
    ent_result = await db.execute(
        select(Entity)
        .join(UserEntityOptIn, UserEntityOptIn.entity_id == Entity.id)
        .where(
            UserEntityOptIn.user_id == user.id,
            UserEntityOptIn.is_opted_in.is_(True),
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
            "status_stats": status_stats,
            "create_entities": create_entities,
            "next_actions": {src: sorted(dst) for src, dst in STATUS_TRANSITIONS.items()},
            "active_nav": "tasks",
            "status_filter": status_filter or "",
            "body_part_id": body_part_id or "",
            "location_id": location_id or "",
            "inventory_item_id": inventory_item_id or "",
        },
    )


# --- API: Generate ---


@router.post("/generate")
async def generate_task_endpoint(
    request: Request,
    custom_prompt: str = Form(default=""),
    preferred_body_part: str = Form(default=""),
    preferred_location: str = Form(default=""),
    preferred_item: str = Form(default=""),
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
            body_part_id=preferred_body_part.strip() or None,
            location_id=preferred_location.strip() or None,
            inventory_item_id=preferred_item.strip() or None,
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
        status=PLANNED,
        selected_entity_name=p["entity_name"],
        selected_params={"intensity": 1, "source": "deterministic"},
        user_prompt="Deterministic fallback — no LLM",
    )
    db.add(log)
    await db.commit()

    return RedirectResponse(url="/tasks/", status_code=status.HTTP_303_SEE_OTHER)


# --- API: Manual task creation (dynamic params form from DSL, ADR-041) ---


@router.post("/generate-weekly")
async def generate_weekly_endpoint(
    request: Request,
    days: int = Form(7),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """POST /tasks/generate-weekly — batch-plan tasks for upcoming days."""
    llm_config = await get_active_llm_config(db, user.id)
    if llm_config is None:
        return RedirectResponse(
            url="/tasks/?error=no_llm",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    try:
        await generate_weekly_tasks(
            db,
            user.id,
            llm_config,
            locale=detect_locale(request, user.locale),
            days=days,
        )
    except (ValueError, JsonRepairError) as exc:
        logger.warning("Weekly generation failed: %s", exc)
        return RedirectResponse(
            url="/tasks/?error=generation_failed",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    return RedirectResponse(url="/tasks/", status_code=status.HTTP_303_SEE_OTHER)


def _coerce_param(value: str | None, d: dict) -> object:
    """Coerce a form string into the typed value for a param definition.

    Returns the raw value when parsing is not needed (kept as the form
    string) and coerces numbers/booleans. ``None``/empty → None.
    """
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
        # checkbox groups come as repeated field values → handled by caller
        return value
    return value


@router.get("/params-form", response_class=HTMLResponse)
async def params_form(
    request: Request,
    entity_id: uuid.UUID,
    prefix: str = Query(default="param_"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Render a dynamic parameter form (partial) for an entity's DSL schema.

    Used by the manual task creation UI (planned params) and by the
    completion card (actual params — pass ``prefix=actual_``). The caller
    must own or have opted-in to the entity.
    """
    locale = detect_locale(request, user.locale)
    theme = detect_theme(user.theme)
    t = get_translations(locale)

    ent_result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user.id),
        )
    )
    entity = ent_result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    try:
        defs = normalize_schema(entity.params_schema)
    except ValueError:
        defs = []

    return templates.TemplateResponse(
        request=request,
        name="partials/params_form.html",
        context={
            "request": request,
            "t": t,
            "user": user,
            "locale": locale,
            "theme": theme,
            "entity": entity,
            "param_defs": defs,
            "form_prefix": prefix,
        },
    )


@router.post("/create")
async def create_manual_task(
    request: Request,
    entity_id: uuid.UUID = Form(...),
    planned_comment: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a task manually from the dynamic params form (no LLM)."""
    locale = detect_locale(request, user.locale)

    ent_result = await db.execute(
        select(Entity).where(
            Entity.id == entity_id,
            Entity.is_public.is_(True) | (Entity.owner_id == user.id),
        )
    )
    entity = ent_result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Entity not found")

    try:
        defs = normalize_schema(entity.params_schema)
    except ValueError as e:
        return RedirectResponse(
            url=f"/tasks/?error={str(e)}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

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
            # custom value fallback (params_form renders an extra input)
            custom = form.get(f"param_{key}_custom")
            if custom:
                value = custom
        if value is not None:
            params[key] = value
    # Checkbox groups (multi_enum): all same-name fields → list
    for key in multi_keys:
        values = form.getlist(f"param_{key}")
        if values:
            params[key] = values

    errors = validate_params(entity.params_schema, params)
    if errors:
        return RedirectResponse(
            url=f"/tasks/?error={errors[0]}",
            status_code=status.HTTP_303_SEE_OTHER,
        )

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
        status=PLANNED,
        selected_entity_name=entity.real_name,
        selected_params=params,
        planned_comment=planned_comment.strip() or None,
        title_override=title if title != entity.real_name else None,
        user_prompt="Manual creation (no LLM)",
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
