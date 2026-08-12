"""LLM Generation Pipeline: context → LLM → repair → parse → save.

Orchestrates the full flow from user request to saved ActivityLog.
"""

import contextlib
import json
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import call_llm
from app.llm.context_builder import (
    build_context,
    filter_automation_eligible,
    format_context_abstract,
    format_context_for_prompt,
)
from app.llm.diet_prompts import (
    DIET_EVALUATE_SYSTEM,
    DIET_GENERATE_SYSTEM,
    DIET_TRAINING_SYNERGY_SYSTEM,
)
from app.llm.repair import JsonRepairError, parse_llm_json
from app.llm.tools import TOOLS
from app.llm.training_prompts import (
    ANALYZE_DAY_SYSTEM,
    PLAN_DAY_SYSTEM,
    SUGGEST_NEXT_DAY_SYSTEM,
)
from app.llm.validator import (
    get_allowed_ids,
    validate_llm_response,
    validate_params_against_schema,
)
from app.models.activity_log import ActivityLog
from app.models.body_part import TaskBodyTarget
from app.models.diet import Diet, DietConsumption, DietEvaluation, DietItem, DietTrainingReview
from app.models.llm_config import LLMProviderConfig
from app.models.task_inventory import TaskInventoryUsage
from app.models.task_location import TaskLocationUsage
from app.models.training import TrainingDay

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
# REM §7.5: TTL on retained raw LLM responses — 30 days is a sensible default
# for "debug for a while, then forget". Configurable per-companies per ADR.
RAW_RESPONSE_TTL_DAYS = 30


def _generate_task_title(
    entity_name: str,
    params: dict | None,
    schema: dict | list | None,
    template: str | dict | None = None,
    locale: str = "en",
) -> str:
    """ADR-042: readable task title via template + fallback (locale-aware)."""
    from app.title_gen import generate_title

    tpl = template if isinstance(template, str) else None
    try:
        return generate_title(
            activity_title=entity_name,
            params=params,
            schema=schema,
            template=tpl,
            locale=locale,
        )
    except Exception:
        return entity_name


def _resolve_raw_response(config: LLMProviderConfig, raw: str) -> tuple[str | None, datetime | None]:
    """Apply REM §7.5 / ADR-034 retention policy.

    Returns (raw_response_to_store, expires_at_or_None).
    If `store_raw_response` is False (or raw is empty) → returns (None, None).
    Otherwise → returns (raw, now + TTL).
    """
    if not getattr(config, "store_raw_response", True):
        return None, None
    if not raw:
        return None, None
    expires = datetime.now(UTC) + timedelta(days=RAW_RESPONSE_TTL_DAYS)
    return raw, expires


_RULES = """\
1. Choose based on user's recent history, stats, desire levels, and active penalties.
2. Prefer entities with higher desire levels (want_very_much > want > neutral > reluctant).
3. Entities with desire_level "strong_aversion" have a small chance of being suggested.
4. If there are pending penalties, consider suggesting a more challenging variation.
5. Be diverse — don't repeat the same entity or category consecutively.
6. Vary parameters within the allowed ranges for variety.
7. Output your response in {locale} language.
"""

SYSTEM_PROMPT_TEMPLATE = (
    "You are an activity suggestion assistant for a personal relationship tracker. "
    "Your job is to select ONE activity from the allowed list and suggest parameters "
    "within the defined ranges.\n\n"
    "Rules:\n" + _RULES + "\n"
    "Response format (JSON):\n"
    "{{\n"
    '  "entity_id": "<uuid>",\n'
    '  "entity_name": "<name>",\n'
    '  "params": {{ ... }},\n'
    '  "reasoning": "<why you chose this task>"\n'
    "}}\n"
)


async def generate_task(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    session_id: uuid.UUID | None = None,
    locale: str = "en",
    custom_prompt: str | None = None,
    body_part_id: str | None = None,
    location_id: str | None = None,
    inventory_item_id: str | None = None,
) -> ActivityLog:
    """Generate a task via LLM and save to ActivityLog."""
    context = await build_context(db, user_id, session_id=session_id, locale=locale)
    # REM §5.2 automation gate: not_assessed/high (and elevated without consent)
    # are never auto-selected — they must not even appear in the prompt.
    context["allowed_entities"] = filter_automation_eligible(context.get("allowed_entities", []))
    allowed_ids = get_allowed_ids(context)

    # Choose format based on LLM mode
    is_abstract = getattr(llm_config, "llm_mode", "full") == "abstract"
    context_text = format_context_abstract(context) if is_abstract else format_context_for_prompt(context)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(locale=locale)

    user_message = f"Context:\n{context_text}\n\n"
    if custom_prompt:
        user_message += f"User request: {custom_prompt}\n\n"
    # Inject preference hints into the prompt
    prefs: list[str] = []
    if body_part_id:
        prefs.append(f"preferred body zone: {body_part_id}")
    if location_id:
        prefs.append(f"preferred location: {location_id}")
    if inventory_item_id:
        prefs.append(f"available item: {inventory_item_id}")
    if prefs:
        user_message += "User preferences: " + "; ".join(prefs) + "\n\n"
    user_message += "Suggest a task from the allowed entities list."

    raw_response = ""
    usage: dict = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "cost": 0.0}
    parsed: dict = {}

    for attempt in range(MAX_RETRIES):
        is_last = attempt == MAX_RETRIES - 1
        try:
            result = await call_llm(
                config=llm_config,
                system_prompt=system_prompt,
                user_message=user_message,
                tools=TOOLS,
                json_mode=True,
            )
            raw_response = result["content"]
            usage = result["usage"]

            parsed = parse_llm_json(raw_response, is_last_attempt=is_last)

            if result.get("tool_calls"):
                for tc in result["tool_calls"]:
                    if tc["name"] == "save_activity_log":
                        with contextlib.suppress(json.JSONDecodeError):
                            parsed = json.loads(tc["arguments"])
                        break

            if parsed:
                break

        except ValueError as e:
            logger.warning(f"LLM JSON parse attempt {attempt + 1}/{MAX_RETRIES} failed: {e}")
        except JsonRepairError:
            raise
    else:
        raise JsonRepairError(f"Failed to parse LLM JSON after {MAX_RETRIES} attempts.")

    entity_id = parsed.get("entity_id")
    entity_name = parsed.get("entity_name")
    params = parsed.get("params")

    if not entity_id or not entity_name:
        raise ValueError("LLM response missing entity_id or entity_name")

    # Validate response against allowed set
    validation_errors = validate_llm_response(parsed, allowed_ids)
    if validation_errors:
        raise ValueError(f"LLM response validation failed: {'; '.join(validation_errors)}")

    # Validate params against the entity's params_schema (REM §7.4).
    # Look up schema from the context to avoid a second DB roundtrip.
    entities_by_id = {e["id"]: e for e in context.get("allowed_entities", [])}
    schema = entities_by_id.get(str(entity_id), {}).get("params_schema") if entity_id else None
    schema_errors = validate_params_against_schema(params, schema)
    if schema_errors:
        raise ValueError(f"LLM params fail entity schema: {'; '.join(schema_errors)}")

    # Safety gate: use the CANONICAL server-side name for the selected entity,
    # never the LLM-supplied one (audit: returned entity_name is not trusted).
    canonical = entities_by_id.get(str(entity_id), {})
    entity_name = canonical.get("name") or entity_name

    raw_to_store, raw_expires = _resolve_raw_response(llm_config, raw_response)
    # ADR-042: auto-generate a readable title from the entity's task_template
    # (falls back to entity name if no template/params are usable).
    auto_title = _generate_task_title(
        entity_name=entity_name,
        params=params,
        schema=canonical.get("params_schema"),
        template=canonical.get("task_template"),
        locale=locale,
    )
    log = ActivityLog(
        user_id=user_id,
        session_id=session_id,
        entity_id=uuid.UUID(entity_id) if entity_id else None,
        status="planned",
        title_override=auto_title if auto_title != entity_name else None,
        user_prompt=custom_prompt or context_text[:500],
        raw_llm_response=raw_to_store,
        raw_response_expires_at=raw_expires,
        cleaned_response=parsed,
        selected_entity_name=entity_name,
        selected_params=params,
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        total_tokens=usage["total_tokens"],
        cost=usage["cost"],
    )
    db.add(log)
    await db.flush()

    # Create link records for user preference hints (update2.md: body/location/inventory selectors)
    if body_part_id:
        try:
            bp_id = uuid.UUID(body_part_id)
            db.add(TaskBodyTarget(task_id=log.id, body_part_id=bp_id, role="target_area"))
        except (ValueError, KeyError):
            pass
    if location_id:
        try:
            loc_id = uuid.UUID(location_id)
            db.add(TaskLocationUsage(task_id=log.id, location_id=loc_id, role="primary"))
        except (ValueError, KeyError):
            pass
    if inventory_item_id:
        try:
            inv_id = uuid.UUID(inventory_item_id)
            db.add(TaskInventoryUsage(task_id=log.id, inventory_item_id=inv_id, role="required"))
        except (ValueError, KeyError):
            pass

    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)
    await db.flush()

    return log


async def generate_weekly_tasks(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    locale: str = "en",
    days: int = 7,
) -> list[ActivityLog]:
    """Generate tasks for multiple days ahead."""
    days = max(1, min(days, 14))
    start_date = date.today() + timedelta(days=1)
    target_dates = [start_date + timedelta(days=i) for i in range(days)]
    date_labels = [d.isoformat() for d in target_dates]

    context = await build_context(db, user_id, locale=locale)
    context["allowed_entities"] = filter_automation_eligible(context.get("allowed_entities", []))
    allowed_ids = get_allowed_ids(context)
    entities_by_id = {e["id"]: e for e in context.get("allowed_entities", [])}

    is_abstract = getattr(llm_config, "llm_mode", "full") == "abstract"
    context_text = format_context_abstract(context) if is_abstract else format_context_for_prompt(context)

    system_prompt = (
        "You are a weekly activity planner. Distribute activities across the upcoming days. "
        "Respect calendar windows, align with diet goals, vary activities. "
        f"Output in {locale}.\n\n"
        'Response format (JSON): {"plan": [{"date": "YYYY-MM-DD", "entity_id": "<uuid>",'
        '"entity_name": "<name>", "params": {...}, "reasoning": "..."}]}'
    )

    user_message = (
        f"Context:\n{context_text}\n\n"
        f"Plan tasks for: {', '.join(date_labels)}\n"
        f"Generate exactly ONE task per day ({days} tasks total)."
    )

    result = await call_llm(config=llm_config, system_prompt=system_prompt, user_message=user_message, json_mode=True)
    raw_response = result["content"]
    usage = result["usage"]
    parsed = parse_llm_json(raw_response, is_last_attempt=True)

    plan = parsed.get("plan", [])
    if not plan:
        raise ValueError("LLM returned empty weekly plan")

    logs: list[ActivityLog] = []
    raw_to_store, raw_expires = _resolve_raw_response(llm_config, raw_response)

    for item in plan[:days]:
        entity_id_str = str(item.get("entity_id") or "").strip()
        entity_name = item.get("entity_name", "Unknown")
        params = item.get("params", {})
        reasoning = item.get("reasoning", "")
        date_str = str(item.get("date") or "").strip()

        if entity_id_str not in allowed_ids:
            continue
        canonical = entities_by_id.get(entity_id_str, {})
        entity_name = canonical.get("name") or entity_name

        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            target_date = target_dates[len(logs)] if logs else start_date

        schema = canonical.get("params_schema")
        if validate_params_against_schema(params, schema):
            continue

        auto_title = _generate_task_title(entity_name, params, schema, canonical.get("task_template"), locale)
        log = ActivityLog(
            user_id=user_id,
            entity_id=uuid.UUID(entity_id_str),
            status="planned",
            scheduled_at=datetime(target_date.year, target_date.month, target_date.day, tzinfo=UTC),
            title_override=auto_title if auto_title != entity_name else None,
            user_prompt=f"Weekly plan: {reasoning[:200]}",
            raw_llm_response=raw_to_store,
            raw_response_expires_at=raw_expires,
            cleaned_response=parsed,
            selected_entity_name=entity_name,
            selected_params=params,
            planned_comment=reasoning[:500] if reasoning else None,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost=0.0,
        )
        db.add(log)
        logs.append(log)

    if not logs:
        raise ValueError("LLM weekly plan contained no valid tasks")

    per_tok = usage["total_tokens"] // max(len(logs), 1)
    per_cost = usage["cost"] / max(len(logs), 1)
    for lg in logs:
        lg.prompt_tokens = usage["prompt_tokens"] // max(len(logs), 1)
        lg.completion_tokens = usage["completion_tokens"] // max(len(logs), 1)
        lg.total_tokens = per_tok
        lg.cost = per_cost

    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)
    await db.flush()
    return logs


async def get_active_llm_config(db: AsyncSession, user_id: uuid.UUID) -> LLMProviderConfig | None:
    """Get the user's active LLM provider config."""
    result = await db.execute(
        select(LLMProviderConfig).where(
            LLMProviderConfig.user_id == user_id,
            LLMProviderConfig.is_active,
        )
    )
    return result.scalar_one_or_none()


# --- Training Pipeline ---


# Safety limits for LLM-generated plan content (audit fix: REM §7.1).
SUBTASK_LIMIT = 20
SUBTASK_MAX_LENGTH = 500


async def generate_daily_plan(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    target_date: date,
    locale: str = "en",
    name: str | None = None,
) -> TrainingDay:
    """Generate a full daily training plan via LLM.

    Audit hardening:
    - Every task's entity_id must belong to the user's allowed (opted-in) set
      — a foreign/private entity is rejected (cross-user protection).
    - params are validated against the entity's params_schema.
    - Subtasks are sanitized: strings only, capped count and length.
    - The TrainingDay is created only after the LLM response has been parsed
      and validated, so a failed attempt never leaves a partial plan behind.
    """
    context = await build_context(db, user_id, locale=locale)
    # REM §5.2 automation gate for training plans too.
    context["allowed_entities"] = filter_automation_eligible(context.get("allowed_entities", []))
    allowed_ids = get_allowed_ids(context)
    entities_by_id = {e["id"]: e for e in context.get("allowed_entities", [])}

    # Abstract mode (strict providers): candidates & history must stay opaque —
    # no real entity names leak into the prompt (audit: training flow ignored
    # llm_mode and revealed names even for abstract-mode users).
    is_abstract = getattr(llm_config, "llm_mode", "full") == "abstract"
    context_text = format_context_abstract(context) if is_abstract else format_context_for_prompt(context)

    system_prompt = PLAN_DAY_SYSTEM.format(locale=locale)
    user_message = f"Context:\n{context_text}\n\nGenerate a daily training plan for {target_date}."

    result = await call_llm(
        config=llm_config,
        system_prompt=system_prompt,
        user_message=user_message,
        json_mode=True,
    )
    raw_response = result["content"]
    usage = result["usage"]

    parsed = parse_llm_json(raw_response, is_last_attempt=True)

    plan_summary = parsed.get("plan_summary", "")
    tasks = parsed.get("tasks", [])

    if not tasks:
        raise ValueError("LLM returned empty plan — no tasks generated")

    # Validate + sanitize every task BEFORE persisting anything.
    prepared_tasks = []
    for task_data in tasks:
        entity_id_str = str(task_data.get("entity_id") or "").strip()
        entity_name = task_data.get("entity_name", "Unknown")
        params = task_data.get("params", {})
        raw_subtasks = task_data.get("subtasks", [])

        if entity_id_str not in allowed_ids:
            raise ValueError(f"LLM plan references unknown entity: {entity_id_str or '<missing>'}")
        schema = entities_by_id.get(entity_id_str, {}).get("params_schema")
        schema_errors = validate_params_against_schema(params, schema)
        if schema_errors:
            raise ValueError(f"LLM params fail entity schema: {'; '.join(schema_errors)}")

        # Safety gate: canonical server-side name, not the LLM-supplied one.
        canonical_entity = entities_by_id.get(entity_id_str, {})
        entity_name = canonical_entity.get("name") or entity_name

        subtasks = [
            {
                "id": i + 1,
                "desc": str(s)[:SUBTASK_MAX_LENGTH],
                "is_done": False,
            }
            for i, s in enumerate(raw_subtasks[:SUBTASK_LIMIT])
            if str(s).strip()  # drop empty/whitespace-only subtasks
        ]
        prepared_tasks.append(
            {
                "entity_id": entity_id_str,
                "entity_name": entity_name,
                "params": params,
                "subtasks": subtasks,
            }
        )

    # All validations passed — now persist the plan atomically.
    training_day = TrainingDay(
        user_id=user_id,
        target_date=target_date,
        name=(name or "").strip()[:200] or None,
        status="active",
        plan_summary=plan_summary,
    )
    db.add(training_day)
    await db.flush()

    raw_to_store, raw_expires = _resolve_raw_response(llm_config, raw_response)
    for task in prepared_tasks:
        log = ActivityLog(
            user_id=user_id,
            entity_id=uuid.UUID(task["entity_id"]),
            status="planned",
            user_prompt=f"Training day plan for {target_date}",
            raw_llm_response=raw_to_store,
            raw_response_expires_at=raw_expires,
            cleaned_response=parsed,
            selected_entity_name=task["entity_name"],
            selected_params=task["params"],
            training_day_id=training_day.id,
            subtasks=task["subtasks"],
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            cost=usage["cost"],
        )
        db.add(log)

    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)

    await db.flush()
    return training_day


async def analyze_training_day(
    db: AsyncSession,
    training_day: TrainingDay,
    llm_config: LLMProviderConfig,
    locale: str = "en",
) -> TrainingDay:
    """Run end-of-day analysis and generate next-day suggestion via LLM.

    Transactional: training_day and llm_config are only mutated after BOTH
    LLM calls succeed, so a failed second call never leaves partial state
    (audit fix: partial analysis committed after LLM error).
    """
    logs_result = await db.execute(
        select(ActivityLog).where(
            ActivityLog.training_day_id == training_day.id,
        )
    )
    logs = list(logs_result.scalars().all())

    completed = sum(1 for log_entry in logs if log_entry.status == "completed")
    stopped = sum(1 for log_entry in logs if log_entry.status == "stopped")
    planned = sum(1 for log_entry in logs if log_entry.status == "planned")
    total = len(logs)

    day_text_parts = [
        f"Training day: {training_day.target_date}",
        f"Total tasks: {total}",
        f"Completed: {completed}",
        f"Stopped: {stopped}",
        f"Remaining: {planned}",
        "",
        "Tasks:",
    ]
    # Abstract mode: never reveal real entity names in the day summary.
    is_abstract = getattr(llm_config, "llm_mode", "full") == "abstract"
    for log_entry in logs:
        sub_done = sum(1 for s in (log_entry.subtasks or []) if s.get("is_done"))
        sub_total = len(log_entry.subtasks or [])
        if is_abstract:
            label = f"entity_id={log_entry.entity_id or '?'}"
        else:
            label = log_entry.selected_entity_name or "(custom)"
        day_text_parts.append(f"- [{log_entry.status}] {label} (subtasks: {sub_done}/{sub_total})")

    day_text = "\n".join(day_text_parts)

    # 1. Analyze day
    system_prompt = ANALYZE_DAY_SYSTEM.format(locale=locale)
    user_message = f"Day results:\n{day_text}\n\nProvide analysis."

    analysis_result = await call_llm(
        config=llm_config,
        system_prompt=system_prompt,
        user_message=user_message,
        json_mode=True,
    )
    analysis_parsed = parse_llm_json(analysis_result["content"], is_last_attempt=True)
    analysis_summary = analysis_parsed.get("analysis", "Day completed.")
    usage_a = analysis_result["usage"]

    # 2. Generate next-day suggestion
    next_system = SUGGEST_NEXT_DAY_SYSTEM.format(locale=locale)
    next_message = f"Today's results:\n{day_text}\n\nAnalysis: {analysis_summary}\n\nSuggest tomorrow's plan."

    next_result = await call_llm(
        config=llm_config,
        system_prompt=next_system,
        user_message=next_message,
        json_mode=True,
    )
    next_parsed = parse_llm_json(next_result["content"], is_last_attempt=True)
    usage_n = next_result["usage"]

    # Both LLM calls succeeded — apply all mutations now (transactional).
    training_day.analysis_summary = analysis_summary
    training_day.next_day_suggestion = next_parsed
    training_day.status = "analyzed"
    training_day.analyzed_at = datetime.now(UTC)
    llm_config.total_tokens += usage_a["total_tokens"] + usage_n["total_tokens"]
    llm_config.total_cost += usage_a["cost"] + usage_n["cost"]

    db.add(training_day)
    db.add(llm_config)
    await db.flush()

    return training_day


# --- Diet Pipeline (LLM planning + adherence evaluation) ---

# Safety limits for LLM-generated diet content.
DIET_ITEM_LIMIT = 20
DIET_NAME_MAX = 200
DIET_DESC_MAX = 3000


async def generate_diet(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    locale: str = "en",
    direction: str | None = None,
    goal: str | None = None,
    preferences: str | None = None,
) -> Diet:
    """Generate a new diet plan via LLM (name, description, food items).

    The LLM output is sanitized before persistence: item count capped, field
    lengths clamped, quantities coerced to positive floats. The Diet is created
    only after the response parses and at least one valid item exists — a
    failed attempt never leaves a partial diet behind.
    """
    user_goal = " ".join(x for x in (direction, goal, preferences) if x) or "balanced healthy diet"
    system_prompt = DIET_GENERATE_SYSTEM.format(locale=locale)
    user_message = f"Direction/goal: {user_goal}\n\nCreate a daily diet plan."

    result = await call_llm(config=llm_config, system_prompt=system_prompt, user_message=user_message, json_mode=True)
    raw_response = result["content"]
    usage = result["usage"]
    parsed = parse_llm_json(raw_response, is_last_attempt=True)

    name = str(parsed.get("name") or "").strip()[:DIET_NAME_MAX]
    if not name:
        raise ValueError("LLM diet response missing name")
    description = str(parsed.get("description") or "").strip()[:DIET_DESC_MAX] or None
    raw_items = parsed.get("items", [])
    if not isinstance(raw_items, list) or not raw_items:
        raise ValueError("LLM diet response has no items")

    prepared_items = []
    for it in raw_items[:DIET_ITEM_LIMIT]:
        if not isinstance(it, dict):
            continue
        item_name = str(it.get("name") or "").strip()[:300]
        if not item_name:
            continue
        qty = it.get("quantity")
        try:
            qty = float(qty) if qty not in (None, "") else None
            if qty is not None and (qty <= 0 or qty > 100_000):
                qty = None
        except (TypeError, ValueError):
            qty = None
        meal = str(it.get("meal_time") or "").strip()[:30] or None
        unit = str(it.get("unit") or "").strip()[:20] or None
        notes = str(it.get("notes") or "").strip()[:2000] or None
        prepared_items.append(
            {
                "name": item_name,
                "quantity": qty,
                "unit": unit,
                "meal_time": meal,
                "notes": notes,
            }
        )
    if not prepared_items:
        raise ValueError("LLM diet response has no usable items")

    diet = Diet(user_id=user_id, name=name, direction=direction, goal=goal, description=description, is_active=True)
    db.add(diet)
    await db.flush()
    for pos, item in enumerate(prepared_items):
        db.add(DietItem(diet_id=diet.id, sort_order=pos, **item))

    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)
    await db.flush()
    return diet


async def evaluate_diet(
    db: AsyncSession,
    diet: Diet,
    llm_config: LLMProviderConfig,
    locale: str = "en",
    days: int = 7,
) -> dict:
    """Evaluate the user's actual consumption against a diet plan via LLM.

    Returns the parsed evaluation dict and applies sanitized plan adjustments
    (add / modify / remove of diet items matched by name). Never trusts the
    LLM with free-form item ids — matches are resolved by exact name against
    the diet's current items.
    """
    start = datetime.now(UTC).date() - timedelta(days=max(1, min(days, 30)))
    items_result = await db.execute(select(DietItem).where(DietItem.diet_id == diet.id).order_by(DietItem.sort_order))
    plan_items = list(items_result.scalars().all())
    cons_result = await db.execute(
        select(DietConsumption)
        .where(DietConsumption.user_id == diet.user_id, DietConsumption.consumed_date >= start)
        .order_by(DietConsumption.consumed_date, DietConsumption.created_at)
    )
    consumptions = list(cons_result.scalars().all())

    def _fmt_item(it: DietItem) -> str:
        qty = f"{it.quantity:g}" if it.quantity else ""
        return f"- {it.name} ({qty} {it.unit or ''}) [{it.meal_time or 'anytime'}]"

    plan_text = "\n".join(_fmt_item(it) for it in plan_items) or "- (empty plan)"
    consumed_text = (
        "\n".join(
            f"- {c.consumed_date}: {c.name} ({c.quantity or ''} {c.unit or ''}) [{c.meal_time or 'anytime'}]"
            for c in consumptions
        )
        or "- (no consumption recorded)"
    )

    system_prompt = DIET_EVALUATE_SYSTEM.format(locale=locale)
    user_message = (
        f"Diet: {diet.name} (direction: {diet.direction or '—'}, goal: {diet.goal or '—'})\n\n"
        f"Planned items:\n{plan_text}\n\n"
        f"Actual consumption (last {days} days):\n{consumed_text}\n\n"
        "Evaluate adherence and suggest plan adjustments."
    )

    result = await call_llm(config=llm_config, system_prompt=system_prompt, user_message=user_message, json_mode=True)
    raw_response = result["content"]
    usage = result["usage"]
    parsed = parse_llm_json(raw_response, is_last_attempt=True)

    # ── Apply sanitized adjustments ──
    by_name = {it.name.strip().lower(): it for it in plan_items}
    applied: list[dict] = []
    adjustments = parsed.get("adjustments", [])
    if isinstance(adjustments, list):
        for adj in adjustments[:10]:
            if not isinstance(adj, dict):
                continue
            action = str(adj.get("action") or "").strip().lower()
            if action == "add":
                item_name = str(adj.get("name") or "").strip()[:300]
                if not item_name:
                    continue
                try:
                    qty = float(adj.get("quantity")) if adj.get("quantity") not in (None, "") else None
                    if qty is not None and (qty <= 0 or qty > 100_000):
                        qty = None
                except (TypeError, ValueError):
                    qty = None
                max_o = await db.execute(
                    select(DietItem.sort_order)
                    .where(DietItem.diet_id == diet.id)
                    .order_by(DietItem.sort_order.desc())
                    .limit(1)
                )
                next_order = (max_o.scalar_one_or_none() or -1) + 1
                new_item = DietItem(
                    diet_id=diet.id,
                    name=item_name,
                    quantity=qty,
                    unit=str(adj.get("unit") or "").strip()[:20] or None,
                    meal_time=str(adj.get("meal_time") or "").strip()[:30] or None,
                    notes=str(adj.get("notes") or "").strip()[:2000] or None,
                    sort_order=next_order,
                )
                db.add(new_item)
                applied.append({"action": "add", "name": item_name})
            elif action in ("modify", "remove"):
                match_name = str(adj.get("match_name") or adj.get("name") or "").strip()
                target = by_name.get(match_name.lower())
                if target is None:
                    continue
                if action == "remove":
                    await db.delete(target)
                    applied.append({"action": "remove", "name": target.name})
                else:
                    try:
                        qty = float(adj.get("quantity")) if adj.get("quantity") not in (None, "") else None
                        if qty is not None and (qty <= 0 or qty > 100_000):
                            qty = None
                    except (TypeError, ValueError):
                        qty = None
                    if qty is not None:
                        target.quantity = qty
                    target.unit = str(adj.get("unit") or target.unit or "").strip()[:20] or None
                    target.meal_time = str(adj.get("meal_time") or target.meal_time or "").strip()[:30] or None
                    notes = str(adj.get("notes") or "").strip()[:2000]
                    if notes:
                        target.notes = notes
                    db.add(target)
                    applied.append({"action": "modify", "name": target.name})

    # Score & findings are only trusted as numbers/strings.
    try:
        score = max(0, min(100, float(parsed.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    summary = str(parsed.get("summary") or "").strip()[:5000] or "No summary."
    findings = [str(f)[:500] for f in parsed.get("findings", []) if isinstance(f, str)][:10]

    evaluation = {"score": score, "summary": summary, "findings": findings, "applied": applied}
    diet.last_evaluation = evaluation
    diet.evaluated_at = datetime.now(UTC)
    db.add(diet)
    # History: persist this evaluation so the user can see evolution over time.
    # created_at set in Python (not server_default) so consecutive evaluations
    # in the same SQLite transaction get distinct timestamps for stable ordering.
    db.add(
        DietEvaluation(
            diet_id=diet.id,
            user_id=diet.user_id,
            score=score,
            summary=summary,
            findings=findings or [],
            applied=applied or [],
            created_at=datetime.now(UTC),
        )
    )

    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)
    await db.flush()

    return evaluation


async def analyze_diet_training_synergy(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    locale: str = "en",
    days: int = 7,
) -> DietTrainingReview:
    """Analyze the mutual influence between diets and training via LLM.

    Gathers the period's diet consumption + training results and asks the LLM
    to find concrete correlations and cross-domain adjustments. The result is
    persisted as a DietTrainingReview (history is kept).
    """
    period_end = datetime.now(UTC).date()
    period_start = period_end - timedelta(days=max(1, min(days, 30)) - 1)

    # Diet side: consumptions + active diet names
    cons_result = await db.execute(
        select(DietConsumption)
        .where(DietConsumption.user_id == user_id, DietConsumption.consumed_date >= period_start)
        .order_by(DietConsumption.consumed_date, DietConsumption.created_at)
    )
    consumptions = list(cons_result.scalars().all())
    diet_result = await db.execute(
        select(Diet).where(Diet.user_id == user_id, Diet.is_active.is_(True)).order_by(Diet.created_at)
    )
    active_diets = list(diet_result.scalars().all())

    # Training side: days in period + their task statuses
    day_result = await db.execute(
        select(TrainingDay)
        .where(TrainingDay.user_id == user_id, TrainingDay.target_date >= period_start)
        .order_by(TrainingDay.target_date)
    )
    training_days = list(day_result.scalars().all())
    day_ids = [td.id for td in training_days]
    logs_by_day: dict[uuid.UUID, list[ActivityLog]] = {}
    if day_ids:
        logs_result = await db.execute(
            select(ActivityLog).where(ActivityLog.training_day_id.in_(day_ids)).order_by(ActivityLog.created_at)
        )
        for log in logs_result.scalars().all():
            logs_by_day.setdefault(log.training_day_id, []).append(log)

    # ── Build the prompt ──
    diet_text = (
        "\n".join(f"- {d.name} (direction: {d.direction or '—'}, goal: {d.goal or '—'})" for d in active_diets)
        or "- (no active diets)"
    )
    consumed_text = (
        "\n".join(
            f"- {c.consumed_date}: {c.name} ({c.quantity or ''} {c.unit or ''}) [{c.meal_time or 'anytime'}]"
            for c in consumptions
        )
        or "- (no consumption recorded)"
    )
    training_lines = []
    for td in training_days:
        logs = logs_by_day.get(td.id, [])
        completed = sum(1 for lg in logs if lg.status == "completed")
        stopped = sum(1 for lg in logs if lg.status == "stopped")
        planned = sum(1 for lg in logs if lg.status == "planned")
        training_lines.append(
            f"- {td.target_date}: {len(logs)} tasks ({completed} done, {stopped} stopped, {planned} left)"
        )
    training_text = "\n".join(training_lines) or "- (no training recorded)"

    system_prompt = DIET_TRAINING_SYNERGY_SYSTEM.format(locale=locale)
    user_message = (
        f"Period: {period_start} .. {period_end}\n\n"
        f"Active diets:\n{diet_text}\n\n"
        f"What was eaten:\n{consumed_text}\n\n"
        f"Training results:\n{training_text}\n\n"
        "Analyze the mutual influence between nutrition and training."
    )

    result = await call_llm(config=llm_config, system_prompt=system_prompt, user_message=user_message, json_mode=True)
    usage = result["usage"]
    parsed = parse_llm_json(result["content"], is_last_attempt=True)

    # ── Sanitize ──
    summary = str(parsed.get("summary") or "").strip()[:5000] or "No analysis."
    correlations = []
    for c in parsed.get("correlations", []) or []:
        if not isinstance(c, dict):
            continue
        direction = str(c.get("direction") or "").strip()
        if direction not in ("diet_to_training", "training_to_diet"):
            direction = "diet_to_training"
        text = str(c.get("text") or "").strip()[:1000]
        if text:
            correlations.append({"direction": direction, "text": text})
    raw_adj = [str(a).strip()[:1000] for a in (parsed.get("adjustments") or []) if isinstance(a, str) and a.strip()]
    adjustments = raw_adj[:8]

    review = DietTrainingReview(
        user_id=user_id,
        period_start=period_start,
        period_end=period_end,
        analysis={"summary": summary, "correlations": correlations, "adjustments": adjustments},
    )
    db.add(review)
    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)
    await db.flush()
    return review
