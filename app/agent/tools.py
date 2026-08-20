"""Native Agent Tools Registry for PracticeLoop Agent (Step 44-48 / ADR-123 & ADR-075)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.memory import recall_user_memories
from app.agent.proactive import schedule_agent_reminder, trigger_event_chain
from app.agent.verify import verify_task_photo
from app.llm.pipeline import generate_task
from app.models.care import CareRoutine
from app.models.health import HealthState
from app.models.journal import JournalPartner
from app.models.session import ActivitySession

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
    {
        "type": "function",
        "function": {
            "name": "search_long_term_memory",
            "description": "Perform semantic search over user's long-term practice memory and past notes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query or topic to recall"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_dynamic_insight_finding",
            "description": "Create and persist a new AI-discovered pattern/finding into DB for the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Title of discovered pattern"},
                    "detail": {"type": "string", "description": "Empirical detail/explanation"},
                    "impact": {"type": "string", "description": "positive or warning"},
                },
                "required": ["title", "detail"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_analytics_correlation_matrix",
            "description": "Fetch pairwise correlation matrix and dynamic findings for the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days": {"type": "integer", "description": "Period days (default 30)"},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "schedule_followup_event",
            "description": "Schedule an autonomous follow-up event or practice task in the event chain.",
            "parameters": {
                "type": "object",
                "properties": {
                    "event_type": {
                        "type": "string",
                        "description": "Event type (e.g., session_completed, chastity_checkin)",
                    },
                    "delay_minutes": {"type": "integer", "description": "Delay in minutes before triggering"},
                    "description": {"type": "string", "description": "Reason or description for the follow-up"},
                },
                "required": ["event_type"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_agent_reminder",
            "description": "Create an in-app and Telegram reminder for the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Short title of the reminder"},
                    "message": {"type": "string", "description": "Detailed text or instructions"},
                    "delay_minutes": {"type": "integer", "description": "Optional delay in minutes"},
                },
                "required": ["title", "message"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "verify_session_task_completion",
            "description": "Run Vision AI verification on a submitted photo to confirm task or posture completion.",
            "parameters": {
                "type": "object",
                "properties": {
                    "media_asset_id": {"type": "string", "description": "UUID of the submitted media asset"},
                    "task_description": {"type": "string", "description": "Description of physical task to verify"},
                },
                "required": ["media_asset_id", "task_description"],
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
        routines = (await db.execute(select(CareRoutine).where(CareRoutine.user_id == user_id))).scalars().all()
        return {
            "status": "aftercare_launched",
            "routines_count": len(routines),
            "advice": "Rest, hydrate, maintain warmth, and engage in gentle recovery.",
        }

    elif tool_name == "create_dynamic_insight_finding":
        from app.models.insights import InsightFinding, InsightRun
        from app.timeutils import local_today

        today = local_today()
        run = (
            await db.execute(
                select(InsightRun).where(InsightRun.user_id == user_id).order_by(InsightRun.created_at.desc()).limit(1)
            )
        ).scalar_one_or_none()

        if not run:
            run = InsightRun(
                user_id=user_id,
                period_start=today,
                period_end=today,
                sections=["agent"],
                status="completed",
                summary="ИИ-Агент обнаружил новую закономерность в диалоге.",
            )
            db.add(run)
            await db.flush()

        finding = InsightFinding(
            run_id=run.id,
            section="agent_discovery",
            title=arguments.get("title", "Обнаруженное наблюдение"),
            summary=arguments.get("detail", "Сгенерировано ИИ-Агентом в диалоге"),
            used_data=["agent_chat"],
        )
        db.add(finding)
        return {"status": "created", "finding_id": str(finding.id), "title": finding.title}

    elif tool_name == "get_analytics_correlation_matrix":
        from app.analytics.engine import run_full_analytics_suite

        days = arguments.get("days", 30)
        suite = await run_full_analytics_suite(db, user_id, days=days)
        return {"status": "success", "analytics": suite}

    elif tool_name == "record_health_state":
        today = local_today()
        state = (
            await db.execute(select(HealthState).where(HealthState.user_id == user_id, HealthState.event_date == today))
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
        partners = (await db.execute(select(JournalPartner).where(JournalPartner.user_id == user_id))).scalars().all()
        p_list = []
        for p in partners:
            p_list.append(
                {
                    "alias": p.alias,
                    "hard_limits": p.hard_limits or [],
                    "soft_limits": p.soft_limits or [],
                    "safewords": p.safewords or [],
                }
            )
        return {"status": "success", "partners_count": len(p_list), "partners": p_list}

    elif tool_name == "get_health_context":
        today = local_today()
        recent_health = (
            (
                await db.execute(
                    select(HealthState)
                    .where(HealthState.user_id == user_id)
                    .order_by(HealthState.event_date.desc())
                    .limit(5)
                )
            )
            .scalars()
            .all()
        )

        h_list = [
            {"date": str(h.event_date), "mood": h.mood, "energy": h.energy, "notes": h.notes} for h in recent_health
        ]
        return {"status": "success", "recent_entries_count": len(h_list), "entries": h_list}

    elif tool_name == "search_long_term_memory":
        query = arguments.get("query", "")
        memories = await recall_user_memories(db=db, user_id=user_id, query=query, limit=5)
        return {"status": "success", "memories_count": len(memories), "memories": memories}

    elif tool_name == "schedule_followup_event":
        event_type = arguments.get("event_type", "custom_event")
        res = await trigger_event_chain(event_type=event_type, user_id=user_id, db=db)
        return {"status": "scheduled", "event_type": event_type, "chain_result": res}

    elif tool_name == "create_agent_reminder":
        title = arguments.get("title", "Напоминание Агента")
        message = arguments.get("message", "")
        delay = arguments.get("delay_minutes", 0)
        res = await schedule_agent_reminder(
            title=title, message=message, user_id=user_id, db=db, delay_minutes=delay, send_telegram=True
        )
        return res

    elif tool_name == "verify_session_task_completion":
        media_id_str = arguments.get("media_asset_id")
        task_desc = arguments.get("task_description", "Физическое задание")
        try:
            m_uuid = uuid.UUID(media_id_str)
            res = await verify_task_photo(media_asset_id=m_uuid, task_description=task_desc, user_id=user_id, db=db)
            return res
        except Exception as e:
            return {"status": "error", "message": str(e)}

    return {"status": "error", "message": f"Unknown tool '{tool_name}'"}
