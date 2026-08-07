"""LLM Generation Pipeline: context → LLM → repair → parse → save.

Orchestrates the full flow from user request to saved ActivityLog.
"""

import contextlib
import json
import logging
import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.client import call_llm
from app.llm.context_builder import build_context, format_context_for_prompt
from app.llm.repair import JsonRepairError, parse_llm_json
from app.llm.tools import TOOLS
from app.llm.training_prompts import (
    ANALYZE_DAY_SYSTEM,
    PLAN_DAY_SYSTEM,
    SUGGEST_NEXT_DAY_SYSTEM,
)
from app.models.activity_log import ActivityLog
from app.models.llm_config import LLMProviderConfig
from app.models.training import TrainingDay

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

_RULES = """\
1. Choose based on user's recent history, stats, desire levels, and active penalties.
2. Prefer entities with higher desire levels (want_very_much > want > neutral > reluctant).
3. Entities with desire_level "unacceptable" have a small chance of being suggested.
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
    "{\n"
    '  "entity_id": "<uuid>",\n'
    '  "entity_name": "<name>",\n'
    '  "params": {{ ... }},\n'
    '  "reasoning": "<why you chose this task>"\n'
    "}\n"
)


async def generate_task(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    session_id: uuid.UUID | None = None,
    locale: str = "en",
    custom_prompt: str | None = None,
) -> ActivityLog:
    """Generate a task via LLM and save to ActivityLog."""
    context = await build_context(db, user_id, session_id=session_id, locale=locale)
    context_text = format_context_for_prompt(context)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(locale=locale)

    user_message = f"Context:\n{context_text}\n\n"
    if custom_prompt:
        user_message += f"User request: {custom_prompt}\n\n"
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

    log = ActivityLog(
        user_id=user_id,
        session_id=session_id,
        entity_id=uuid.UUID(entity_id) if entity_id else None,
        status="pending",
        user_prompt=custom_prompt or context_text[:500],
        raw_llm_response=raw_response,
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

    llm_config.total_tokens += usage["total_tokens"]
    llm_config.total_cost += usage["cost"]
    db.add(llm_config)
    await db.flush()

    return log


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


async def generate_daily_plan(
    db: AsyncSession,
    user_id: uuid.UUID,
    llm_config: LLMProviderConfig,
    target_date: date,
    locale: str = "en",
) -> TrainingDay:
    """Generate a full daily training plan via LLM."""
    training_day = TrainingDay(
        user_id=user_id,
        target_date=target_date,
        status="planned",
    )
    db.add(training_day)
    await db.flush()

    context = await build_context(db, user_id, locale=locale)
    context_text = format_context_for_prompt(context)

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

    training_day.plan_summary = plan_summary
    training_day.status = "active"
    db.add(training_day)

    for task_data in tasks:
        entity_id_str = task_data.get("entity_id")
        entity_name = task_data.get("entity_name", "Unknown")
        params = task_data.get("params", {})
        raw_subtasks = task_data.get("subtasks", [])

        subtasks = [
            {
                "id": i + 1,
                "desc": s if isinstance(s, str) else str(s),
                "is_done": False,
            }
            for i, s in enumerate(raw_subtasks)
        ]

        log = ActivityLog(
            user_id=user_id,
            entity_id=uuid.UUID(entity_id_str) if entity_id_str else None,
            status="pending",
            user_prompt=f"Training day plan for {target_date}",
            raw_llm_response=raw_response,
            cleaned_response=parsed,
            selected_entity_name=entity_name,
            selected_params=params,
            training_day_id=training_day.id,
            subtasks=subtasks,
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
    """Run end-of-day analysis and generate next-day suggestion via LLM."""
    logs_result = await db.execute(
        select(ActivityLog).where(
            ActivityLog.training_day_id == training_day.id,
        )
    )
    logs = list(logs_result.scalars().all())

    completed = sum(1 for log_entry in logs if log_entry.status == "completed")
    interrupted = sum(1 for log_entry in logs if log_entry.status == "interrupted")
    pending = sum(1 for log_entry in logs if log_entry.status == "pending")
    total = len(logs)

    day_text_parts = [
        f"Training day: {training_day.target_date}",
        f"Total tasks: {total}",
        f"Completed: {completed}",
        f"Interrupted: {interrupted}",
        f"Remaining: {pending}",
        "",
        "Tasks:",
    ]
    for log_entry in logs:
        sub_done = sum(1 for s in (log_entry.subtasks or []) if s.get("is_done"))
        sub_total = len(log_entry.subtasks or [])
        day_text_parts.append(
            f"- [{log_entry.status}] {log_entry.selected_entity_name} (subtasks: {sub_done}/{sub_total})"
        )

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
    training_day.analysis_summary = analysis_parsed.get("analysis", "Day completed.")
    training_day.status = "completed"

    usage_a = analysis_result["usage"]
    llm_config.total_tokens += usage_a["total_tokens"]
    llm_config.total_cost += usage_a["cost"]

    # 2. Generate next-day suggestion
    next_system = SUGGEST_NEXT_DAY_SYSTEM.format(locale=locale)
    next_message = (
        f"Today's results:\n{day_text}\n\nAnalysis: {training_day.analysis_summary}\n\nSuggest tomorrow's plan."
    )

    next_result = await call_llm(
        config=llm_config,
        system_prompt=next_system,
        user_message=next_message,
        json_mode=True,
    )
    next_parsed = parse_llm_json(next_result["content"], is_last_attempt=True)
    training_day.next_day_suggestion = json.dumps(next_parsed, ensure_ascii=False)
    training_day.status = "analyzed"
    training_day.analyzed_at = datetime.now(UTC)

    usage_n = next_result["usage"]
    llm_config.total_tokens += usage_n["total_tokens"]
    llm_config.total_cost += usage_n["cost"]

    db.add(training_day)
    db.add(llm_config)
    await db.flush()

    return training_day
