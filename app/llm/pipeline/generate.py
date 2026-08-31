"""LLM task generation — single + weekly + helpers."""

from __future__ import annotations

import contextlib
import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import client, context_builder, validator
from app.llm.context_builder import (
    filter_automation_eligible,
    format_context_abstract,
    format_context_for_prompt,
)
from app.llm.mode import llm_mode_hint
from app.llm.repair import JsonRepairError, parse_llm_json
from app.llm.tools import TOOLS
from app.llm.validator import (
    validate_llm_response,
    validate_params_against_schema,
)
from app.models.activity_log import ActivityLog
from app.models.body_part import TaskBodyTarget
from app.models.llm_config import LLMProviderConfig
from app.models.task_inventory import TaskInventoryUsage
from app.models.task_location import TaskLocationUsage
from app.timeutils import local_today

logger = logging.getLogger(__name__)

MAX_RETRIES = 3
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
    llm_mode: str | None = None,
) -> ActivityLog:
    """Generate a task via LLM and save to ActivityLog."""
    context = await context_builder.build_context(db, user_id, session_id=session_id, locale=locale)
    # ADR-106: the user's opt-in is the approval boundary. Opted-in entities are
    # auto-eligible regardless of risk_level/automation_allowed (informational).
    context["allowed_entities"] = filter_automation_eligible(context.get("allowed_entities", []))
    allowed_ids = validator.get_allowed_ids(context)

    # Choose format based on LLM mode
    is_abstract = getattr(llm_config, "llm_mode", "full") == "abstract"
    context_text = format_context_abstract(context) if is_abstract else format_context_for_prompt(context)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(locale=locale) + llm_mode_hint(llm_mode)

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
            result = await client.call_llm(
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
    llm_mode: str | None = None,
) -> list[ActivityLog]:
    """Generate tasks for multiple days ahead (audit P1-2 hardened).

    Validation contract (audit PROJECT_REVIEW 2026-08-13, P1-2):
      - dates must belong to the requested target set (exact dates);
      - each requested day covered exactly once (uniqueness + completeness);
      - entity must be in the allowed (opt-in) set, params valid against schema;
      - on any invalid item the whole plan is rejected atomically — nothing is
        written (no silent partial plan).
    """
    days = max(1, min(days, 14))
    start_date = local_today() + timedelta(days=1)
    target_dates = [start_date + timedelta(days=i) for i in range(days)]
    target_set = set(target_dates)
    date_labels = [d.isoformat() for d in target_dates]

    context = await context_builder.build_context(db, user_id, locale=locale)
    context["allowed_entities"] = filter_automation_eligible(context.get("allowed_entities", []))
    allowed_ids = validator.get_allowed_ids(context)
    entities_by_id = {e["id"]: e for e in context.get("allowed_entities", [])}

    is_abstract = getattr(llm_config, "llm_mode", "full") == "abstract"
    context_text = format_context_abstract(context) if is_abstract else format_context_for_prompt(context)

    system_prompt = (
        "You are a weekly activity planner. Distribute activities across the upcoming days. "
        "Respect calendar windows, align with diet goals, vary activities. "
        f"Output in {locale}.\n\n"
        'Response format (JSON): {"plan": [{"date": "YYYY-MM-DD", "entity_id": "<uuid>",'
        '"entity_name": "<name>", "params": {...}, "reasoning": "..."}]}'
        f"\nThe dates MUST be exactly one of: {', '.join(date_labels)}. "
        "Exactly one task per date, every date covered, no duplicates."
    ) + llm_mode_hint(llm_mode)

    user_message = (
        f"Context:\n{context_text}\n\n"
        f"Plan tasks for: {', '.join(date_labels)}\n"
        f"Generate exactly ONE task per day ({days} tasks total)."
    )

    result = await client.call_llm(
        config=llm_config, system_prompt=system_prompt, user_message=user_message, json_mode=True
    )
    raw_response = result["content"]
    usage = result["usage"]
    parsed = parse_llm_json(raw_response, is_last_attempt=True)

    plan = parsed.get("plan", [])
    if not plan:
        raise ValueError("LLM returned empty weekly plan")

    # ── Validate the whole plan BEFORE writing anything (P1-2) ──
    seen_dates: set[datetime.date] = set()
    validated: list[tuple[datetime.date, str, dict, dict, str]] = []  # date, entity_id, params, canonical, reasoning

    for idx, item in enumerate(plan[: days * 2]):  # cap scan; still require exact coverage below
        entity_id_str = str(item.get("entity_id") or "").strip()
        entity_name = item.get("entity_name", "Unknown")
        params = item.get("params", {})
        reasoning = item.get("reasoning", "")
        date_str = str(item.get("date") or "").strip()

        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except (ValueError, TypeError) as exc:
            raise ValueError(f"Weekly plan item {idx}: invalid date {date_str!r}") from exc

        if target_date not in target_set:
            raise ValueError(
                f"Weekly plan item {idx}: date {date_str} is outside the requested range "
                f"({date_labels[0]}..{date_labels[-1]})"
            )
        if target_date in seen_dates:
            raise ValueError(f"Weekly plan item {idx}: duplicate date {date_str} — exactly one task per day")
        seen_dates.add(target_date)

        if entity_id_str not in allowed_ids:
            raise ValueError(f"Weekly plan item {idx}: entity {entity_id_str!r} is not in the allowed set")
        canonical = entities_by_id.get(entity_id_str, {})
        if not canonical:
            raise ValueError(f"Weekly plan item {idx}: entity {entity_id_str!r} not found")
        if validate_params_against_schema(params, canonical.get("params_schema")):
            raise ValueError(f"Weekly plan item {idx}: params invalid for entity schema")

        validated.append((target_date, entity_id_str, params, canonical, reasoning or entity_name))

    if len(validated) != days or seen_dates != target_set:
        missing = sorted(target_set - seen_dates)
        raise ValueError(
            f"Weekly plan must cover exactly {days} days ({len(validated)} provided; missing: "
            f"{[d.isoformat() for d in missing]})"
        )

    # ── All valid — write atomically ──
    raw_to_store, raw_expires = _resolve_raw_response(llm_config, raw_response)
    logs: list[ActivityLog] = []
    for target_date, entity_id_str, params, canonical, reasoning in validated:
        entity_name = canonical.get("name") or "Unknown"
        schema = canonical.get("params_schema")
        auto_title = _generate_task_title(entity_name, params, schema, canonical.get("task_template"), locale)
        log = ActivityLog(
            user_id=user_id,
            entity_id=uuid.UUID(entity_id_str),
            status="planned",
            scheduled_at=datetime(target_date.year, target_date.month, target_date.day, tzinfo=UTC),
            title_override=auto_title if auto_title != entity_name else None,
            user_prompt=f"Weekly plan: {str(reasoning)[:200]}",
            raw_llm_response=raw_to_store,
            raw_response_expires_at=raw_expires,
            cleaned_response=parsed,
            selected_entity_name=entity_name,
            selected_params=params,
            planned_comment=str(reasoning)[:500] if reasoning else None,
            prompt_tokens=0,
            completion_tokens=0,
            total_tokens=0,
            cost=0.0,
        )
        db.add(log)
        logs.append(log)

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


async def get_active_llm_config(
    db: AsyncSession, user_id: uuid.UUID, capability: str = "text"
) -> LLMProviderConfig | None:
    """Resolve the user's selected capability, with legacy active-config fallback."""
    from app.models.llm_catalog import LLMUserSelection

    selection = await db.scalar(
        select(LLMUserSelection).where(
            LLMUserSelection.user_id == user_id,
            LLMUserSelection.capability == capability,
        )
    )
    if selection and selection.user_config_id:
        return await db.scalar(
            select(LLMProviderConfig).where(
                LLMProviderConfig.id == selection.user_config_id,
                LLMProviderConfig.user_id == user_id,
            )
        )
    result = await db.execute(
        select(LLMProviderConfig).where(
            LLMProviderConfig.user_id == user_id,
            LLMProviderConfig.is_active,
        )
    )
    return result.scalars().first()
