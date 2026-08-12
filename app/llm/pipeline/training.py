"""LLM training pipeline — daily plan generation + analysis."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import client, context_builder, validator
from app.llm.context_builder import (
    filter_automation_eligible,
    format_context_abstract,
    format_context_for_prompt,
)
from app.llm.pipeline.generate import (
    _resolve_raw_response,
)
from app.llm.repair import parse_llm_json
from app.llm.training_prompts import (
    ANALYZE_DAY_SYSTEM,
    PLAN_DAY_SYSTEM,
    SUGGEST_NEXT_DAY_SYSTEM,
)
from app.llm.validator import (
    validate_params_against_schema,
)
from app.models.activity_log import ActivityLog
from app.models.llm_config import LLMProviderConfig
from app.models.training import TrainingDay

logger = logging.getLogger(__name__)

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
    context = await context_builder.build_context(db, user_id, locale=locale)
    # REM §5.2 automation gate for training plans too.
    context["allowed_entities"] = filter_automation_eligible(context.get("allowed_entities", []))
    allowed_ids = validator.get_allowed_ids(context)
    entities_by_id = {e["id"]: e for e in context.get("allowed_entities", [])}

    # Abstract mode (strict providers): candidates & history must stay opaque —
    # no real entity names leak into the prompt (audit: training flow ignored
    # llm_mode and revealed names even for abstract-mode users).
    is_abstract = getattr(llm_config, "llm_mode", "full") == "abstract"
    context_text = format_context_abstract(context) if is_abstract else format_context_for_prompt(context)

    system_prompt = PLAN_DAY_SYSTEM.format(locale=locale)
    user_message = f"Context:\n{context_text}\n\nGenerate a daily training plan for {target_date}."

    result = await client.call_llm(
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

    analysis_result = await client.call_llm(
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

    next_result = await client.call_llm(
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
