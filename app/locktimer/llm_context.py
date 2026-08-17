"""Timer-aware LLM context builder — C7.

Builds a structured prompt context from lock session config (rules, slots,
tasks, calendar) for LLM proposal generation.  Reuses the generic app.llm.client
for the actual API call.
"""

from __future__ import annotations

import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.locktimer.repositories import get_session, list_slot_rules, list_task_rules
from app.models.locktimer import LockSession


async def build_timer_context(
    db: AsyncSession,
    session_id: uuid.UUID,
    owner_id: uuid.UUID,
    locale: str = "en",
) -> dict:
    """Build the prompt context for a specific timer session."""
    session = await get_session(db, session_id, owner_id)
    if session is None:
        raise ValueError("Session not found")

    slot_rules = await list_slot_rules(db, session_id)
    task_rules = await list_task_rules(db, session_id)

    return {
        "session": _serialize_session(session),
        "slot_rules": [_serialize_slot_rule(r) for r in slot_rules],
        "task_rules": [_serialize_task_rule(r) for r in task_rules],
        "locale": locale,
    }


def format_timer_prompt(context: dict, user_brief: str | None = None) -> str:
    """Render timer context into an LLM prompt string."""
    parts = []

    parts.append("## Timer Session")
    s = context["session"]
    parts.append(f"- Duration type: {s['duration_type']}")
    parts.append(f"- Timezone: {s['timezone']}")
    if s.get("started_at"):
        parts.append(f"- Started at: {s['started_at']}")
    if s.get("max_end_at"):
        parts.append(f"- Max end: {s['max_end_at']}")
    parts.append("")

    if context["slot_rules"]:
        parts.append("## Current Slot Rules")
        for r in context["slot_rules"]:
            parts.append(
                f"- [{r['rule_type']}] {r['name']}: duration={r['duration_seconds']}s,"
                f" schedule={json.dumps(r['schedule'])}"
            )
        parts.append("")

    if context["task_rules"]:
        parts.append("## Current Task Rules")
        for r in context["task_rules"]:
            parts.append(
                f"- [{r['schedule_type']}] {r['title']}: due_window={r['due_window_seconds']}s,"
                f" schedule={json.dumps(r['schedule'])}"
            )
        parts.append("")

    if user_brief:
        parts.append("## User Request")
        parts.append(user_brief)
        parts.append("")

    parts.append("## Instructions")
    parts.append(
        "Generate a set of proposal items that improve or extend the timer session.\n"
        "Each item must have a type (slot_rule / task_rule / inner_period / param_override),\n"
        "a human-readable title, and structured data matching the rule type schema.\n"
        "Do NOT invent types, IDs, or parameters that don't exist in the allowed schemas.\n"
        "Respect the session's duration constraints and max_end_at if set."
    )

    return "\n".join(parts)


TIMER_SYSTEM_PROMPT = (
    "You are a chastity timer assistant. The user has an active (or draft) chastity session "
    "with slot rules and task rules. Your job is to suggest improvements: new slot/task rules, "
    "schedule adjustments, parameter overrides. Every suggestion must be a validated, structured "
    "proposal item that the user can accept or reject individually.\n\n"
    "Output format: JSON object with an 'items' array. Each item: "
    "{item_id: 'uuid-like-string', type: 'slot_rule'|'task_rule'|'param_override', "
    "title: 'short description', data: {...rule-specific-fields...}, reasoning: 'why'}"
)


SYSTEM_PROMPT = TIMER_SYSTEM_PROMPT


# ---- helpers ----


def _serialize_session(session: LockSession) -> dict:
    return {
        "id": str(session.id),
        "state": session.state,
        "duration_type": session.duration_type,
        "timezone": session.timezone,
        "started_at": session.started_at.isoformat() if session.started_at else None,
        "max_end_at": session.max_end_at.isoformat() if session.max_end_at else None,
        "effective_end_at": session.effective_end_at.isoformat() if session.effective_end_at else None,
        "merge_gap_seconds": session.merge_gap_seconds,
        "can_extend_duration": session.can_extend_duration,
    }


def _serialize_slot_rule(rule) -> dict:
    return {
        "id": str(rule.id),
        "name": rule.name,
        "rule_type": rule.rule_type,
        "schedule": rule.schedule,
        "duration_seconds": rule.duration_seconds,
        "allow_late_open": rule.allow_late_open,
        "max_late_seconds": rule.max_late_seconds,
        "extend_on_late_open": rule.extend_on_late_open,
        "close_grace_seconds": rule.close_grace_seconds,
    }


def _serialize_task_rule(rule) -> dict:
    return {
        "id": str(rule.id),
        "title": rule.title,
        "schedule_type": rule.schedule_type,
        "schedule": rule.schedule,
        "due_window_seconds": rule.due_window_seconds,
        "hide_until_due": rule.hide_until_due,
        "requires_report": rule.requires_report,
    }
