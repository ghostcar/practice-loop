"""Context Builder: gathers user history, stats, active penalties, allowed entities, and calendar availability.

Stateless — rebuilt on every request.
"""

import json
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.calendar import get_day_schedule
from app.models.activity_log import ActivityLog
from app.models.entity import Entity
from app.models.opt_in import UserEntityOptIn


async def build_context(
    db: AsyncSession,
    user_id: uuid.UUID,
    session_id: uuid.UUID | None = None,
    locale: str = "en",
) -> dict:
    """Build the full LLM context: allowed entities, recent history, stats, calendar."""

    # 1. Allowed entities (opted-in + desire level)
    allowed_entities = await _get_allowed_entities(db, user_id)

    # 2. Recent history (last 10 activities)
    recent_logs = await _get_recent_history(db, user_id, limit=10)

    # 3. Stats summary
    stats = await _get_user_stats(db, user_id)

    # 4. Active penalties (from session or pending interrupted tasks)
    active_penalties = await _get_active_penalties(db, user_id, session_id)

    # 5. Today's calendar schedule
    calendar_schedule = await get_day_schedule(db, user_id, date.today())

    return {
        "allowed_entities": allowed_entities,
        "recent_history": recent_logs,
        "stats": stats,
        "active_penalties": active_penalties,
        "calendar_schedule": calendar_schedule,
        "locale": locale,
    }


async def _get_allowed_entities(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """Return entities the user has opted into, with desire levels and intensity."""
    result = await db.execute(
        select(UserEntityOptIn, Entity)
        .join(Entity, UserEntityOptIn.entity_id == Entity.id)
        .where(
            UserEntityOptIn.user_id == user_id,
            UserEntityOptIn.is_opted_in,
        )
    )
    rows = result.all()
    entities = []
    for opt_in, entity in rows:
        entities.append(
            {
                "id": str(entity.id),
                "name": entity.real_name,
                "type": entity.type,
                "category": entity.category,
                "tags": entity.tags or [],
                "intensity": entity.intensity or "active",
                "params_schema": entity.params_schema,
                "desire_level": opt_in.desire_level,
                "rating": opt_in.rating,
            }
        )
    return entities


async def _get_recent_history(db: AsyncSession, user_id: uuid.UUID, limit: int = 10) -> list[dict]:
    """Return recent activity logs for context."""
    result = await db.execute(
        select(ActivityLog).where(ActivityLog.user_id == user_id).order_by(ActivityLog.created_at.desc()).limit(limit)
    )
    logs = result.scalars().all()
    history = []
    for log in logs:
        history.append(
            {
                "id": str(log.id),
                "entity_name": log.selected_entity_name,
                "status": log.status,
                "params": log.selected_params,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
        )
    return history


async def _get_user_stats(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Return aggregate stats for the user."""
    result = await db.execute(
        select(
            func.count(ActivityLog.id).label("total"),
            func.sum(case((ActivityLog.status == "completed", 1), else_=0)).label("completed"),
            func.sum(case((ActivityLog.status == "interrupted", 1), else_=0)).label("interrupted"),
        ).where(ActivityLog.user_id == user_id)
    )
    row = result.one()
    total = row.total or 0
    completed = row.completed or 0

    week_ago = datetime.now(UTC) - timedelta(days=7)
    week_result = await db.execute(
        select(func.count(ActivityLog.id)).where(
            ActivityLog.user_id == user_id,
            ActivityLog.created_at >= week_ago,
        )
    )
    week_count = week_result.scalar() or 0

    return {
        "total_activities": total,
        "completed": completed,
        "interrupted": row.interrupted or 0,
        "week_activities": week_count,
    }


async def _get_active_penalties(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID | None) -> list[dict]:
    """Return active penalties (escalation count, interrupted tasks)."""
    interrupted = await db.execute(
        select(func.count(ActivityLog.id)).where(
            ActivityLog.user_id == user_id,
            ActivityLog.status == "interrupted",
        )
    )
    total_interruptions = interrupted.scalar() or 0

    recent = await db.execute(
        select(ActivityLog.status)
        .where(ActivityLog.user_id == user_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(10)
    )
    statuses = [row[0] for row in recent.all()]
    consecutive_interruptions = 0
    for s in statuses:
        if s == "interrupted":
            consecutive_interruptions += 1
        else:
            break

    return [
        {"type": "total_interruptions", "count": total_interruptions},
        {"type": "consecutive_interruptions", "count": consecutive_interruptions},
    ]


def format_context_abstract(context: dict) -> str:
    """Render context with opaque IDs — no real names. For strict providers."""
    parts = []
    parts.append("## User Stats")
    stats = context["stats"]
    parts.append(f"- Completed: {stats['completed']}")
    parts.append(f"- Interrupted: {stats['interrupted']}")
    parts.append("")

    parts.append("## Available Candidates (opaque IDs)")
    for e in context["allowed_entities"]:
        cat = e["category"]
        typ = e["type"]
        desire = e["desire_level"]
        intensity_label = e.get("intensity", "active")
        parts.append(f"- ID={e['id']} | cat={cat} | type={typ} | desire={desire} | intensity={intensity_label}")
    parts.append("")

    parts.append("## Recent History")
    for h in context["recent_history"]:
        parts.append(f"- [{h['status']}] entity={h.get('entity_name', '?')[:20]} at {h.get('created_at')}")
    parts.append("")

    return "\n".join(parts)


def format_context_for_prompt(context: dict) -> str:
    """Render the context dict into a prompt string for the LLM."""
    parts = []
    parts.append("## User Stats")
    stats = context["stats"]
    parts.append(f"- Total activities: {stats['total_activities']}")
    parts.append(f"- Completed: {stats['completed']}")
    parts.append(f"- Interrupted: {stats['interrupted']}")
    parts.append(f"- This week: {stats['week_activities']}")
    parts.append("")

    # Calendar schedule
    cal = context.get("calendar_schedule")
    if cal and cal.windows:
        parts.append("## Today's Availability Schedule")
        parts.append(f"Template: {cal.template_name}")
        for w in cal.windows:
            icon = {"allowed": "✅", "passive_only": "🟡", "disallowed": "🔴"}.get(w["policy"], "❓")
            parts.append(f"- {icon} {w['start']}-{w['end']}: {w['label']} ({w['policy']})")
        parts.append("")
        parts.append(
            "When planning tasks, respect these windows:\n"
            "- 'allowed' = any activity can be scheduled\n"
            "- 'passive_only' = only passive-intensity activities (wearing, chastity, bondage under clothes)\n"
            "- 'disallowed' = no activities at all\n"
            "- Check entity.intensity field for passive vs active"
        )
        parts.append("")

    parts.append("## Allowed Entities (opt-in, with desire levels)")
    for e in context["allowed_entities"]:
        desire = e["desire_level"]
        intensity_info = f" [intensity={e.get('intensity', 'active')}]"
        parts.append(f"- [{desire}] {e['name']} (category={e['category']}, type={e['type']}){intensity_info}")
        if e.get("params_schema"):
            parts.append(f"  params_schema: {json.dumps(e['params_schema'], ensure_ascii=False)}")
    parts.append("")

    parts.append("## Recent History (last 10)")
    for h in context["recent_history"]:
        parts.append(f"- [{h['status']}] {h.get('entity_name') or '(custom)'} at {h.get('created_at')}")
    parts.append("")

    parts.append("## Active Penalties")
    penalties = context.get("active_penalties", [])
    if penalties:
        for p in penalties:
            parts.append(f"- {p['type']}: {p['count']}")
    else:
        parts.append("- None")

    return "\n".join(parts)
