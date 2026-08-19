"""Native Agent Tools Registry for PracticeLoop Agent (Step 44-45 / ADR-123)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.pipeline import generate_task
from app.models.care import CareRoutine
from app.models.health import HealthState
from app.models.journal import JournalPartner
from app.models.session import ActivitySession
from app.timeutils import local_today

logger = logging.getLogger(__name__)

AGENT_TOOLS_SCHEMA = [
    {
        "type": "function",
        "function": {
            "name": "get_active_session",
            "description": "Get current active session and locktimer details for the user.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_optin_task",
            "description": "Generate a new task candidate from the user's explicit opt-in catalog.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Optional category filter"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "trigger_aftercare",
            "description": "Launch Aftercare recovery routine and return available care items.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_health_state",
            "description": "Log daily health, mood, and energy state for the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "mood": {"type": "integer", "description": "Mood score 1-5"},
                    "energy": {"type": "integer", "description": "Energy score 1-5"},
                    "notes": {"type": "string", "description": "Optional notes or symptoms"},
                },
                "required": ["mood", "energy"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_partner_limits",
            "description": "Retrieve partner profile safety limits, hard limits, soft limits, and safewords.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_health_context",
            "description": "Retrieve recent health state, mood, energy, and cycle context for safety checks.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


async def execute_agent_tool(
    tool_name: str,
    arguments: dict[str, Any],
    user_id: uuid.UUID,
    db: AsyncSession,
) -> dict[str, Any]:
    """Executes native tool by name and returns structured result."""
    if tool_name == "get_active_session":
        result = await db.execute(
            select(ActivitySession)
            .where(ActivitySession.owner_id == user_id, ActivitySession.status == "active")
            .order_by(ActivitySession.created_at.desc())
            .limit(1)
        )
        session = result.scalar_one_or_none()
        if session:
            return {
                "status": "found",
                "session_id": str(session.id),
                "title": session.title,
                "created_at": session.created_at.isoformat(),
            }
        return {"status": "none", "message": "No active session currently."}

    elif tool_name == "generate_optin_task":
        try:
            task_log = await generate_task(db=db, user_id=user_id)
            return {
                "status": "generated",
                "task_id": str(task_log.id),
                "prompt": task_log.user_prompt,
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    elif tool_name == "trigger_aftercare":
        routines = (
            await db.execute(select(CareRoutine).where(CareRoutine.user_id == user_id))
        ).scalars().all()
        return {
            "status": "aftercare_launched",
            "routines_count": len(routines),
            "advice": "Rest, hydrate, maintain warmth, and engage in gentle recovery.",
        }

    elif tool_name == "record_health_state":
        today = local_today()
        state = (
            await db.execute(
                select(HealthState).where(HealthState.user_id == user_id, HealthState.event_date == today)
            )
        ).scalar_one_or_none()

        if not state:
            state = HealthState(user_id=user_id, event_date=today)
            db.add(state)

        state.mood = arguments.get("mood", 3)
        state.energy = arguments.get("energy", 3)
        if arguments.get("notes"):
            state.notes = arguments["notes"]

        await db.commit()
        return {"status": "recorded", "event_date": str(today), "mood": state.mood, "energy": state.energy}

    elif tool_name == "get_partner_limits":
        partners = (
            await db.execute(select(JournalPartner).where(JournalPartner.user_id == user_id))
        ).scalars().all()
        p_list = []
        for p in partners:
            p_list.append({
                "alias": p.alias,
                "hard_limits": p.hard_limits or [],
                "soft_limits": p.soft_limits or [],
                "safewords": p.safewords or [],
            })
        return {"status": "success", "partners_count": len(p_list), "partners": p_list}

    elif tool_name == "get_health_context":
        today = local_today()
        recent_health = (
            await db.execute(
                select(HealthState)
                .where(HealthState.user_id == user_id)
                .order_by(HealthState.event_date.desc())
                .limit(5)
            )
        ).scalars().all()

        h_list = [
            {"date": str(h.event_date), "mood": h.mood, "energy": h.energy, "notes": h.notes}
            for h in recent_health
        ]
        return {"status": "success", "recent_entries_count": len(h_list), "entries": h_list}

    return {"status": "error", "message": f"Unknown tool '{tool_name}'"}
