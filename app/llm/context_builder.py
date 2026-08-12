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
from app.models.diet import Diet
from app.models.entity import Entity
from app.models.opt_in import UserEntityOptIn
from app.models.training import TrainingDay


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

    # 6. Active diets — what nutrition plans are currently active
    active_diets = await _get_active_diets(db, user_id)

    # 7. Today's training status — what's planned/completed today
    today_training = await _get_today_training(db, user_id)

    return {
        "allowed_entities": allowed_entities,
        "recent_history": recent_logs,
        "stats": stats,
        "active_penalties": active_penalties,
        "calendar_schedule": calendar_schedule,
        "active_diets": active_diets,
        "today_training": today_training,
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
                "task_template": entity.task_template,
                "desire_level": opt_in.desire_level,
                "rating": opt_in.rating,
                "risk_level": entity.risk_level or "not_assessed",
            }
        )
    return entities


# REM §5.2 automation gate: entities that may be picked by the LLM without
# extra confirmation. not_assessed (never reviewed) and high (too risky) are
# excluded; elevated requires confirmation, so it is included only when the
# caller opts in (e.g. explicit user request).
def filter_automation_eligible(
    entities: list[dict],
    allow_elevated: bool = False,
) -> list[dict]:
    """Keep only entities the LLM may auto-select (REM §5.2 safety gate).

    - not_assessed / high → always excluded from automatic selection;
    - elevated → excluded unless ``allow_elevated=True`` (explicit confirmation);
    - low → always allowed.
    """
    result = []
    for e in entities:
        level = e.get("risk_level") or "not_assessed"
        if level == "low" or level == "elevated" and allow_elevated:
            result.append(e)
        # not_assessed / high / elevated-without-consent → skip
    return result


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
                "entity_id": str(log.entity_id) if log.entity_id else None,
                "entity_name": log.selected_entity_name,
                "status": log.status,
                "params": log.selected_params,
                # ADR-041: actual parameters (what was really done) — lets the
                # LLM calibrate future suggestions against reality, not just plans
                "actual_parameters": log.actual_parameters,
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
            func.sum(case((ActivityLog.status == "stopped", 1), else_=0)).label("stopped"),
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
        "stopped": row.stopped or 0,
        "week_activities": week_count,
    }


async def _get_active_penalties(db: AsyncSession, user_id: uuid.UUID, session_id: uuid.UUID | None) -> list[dict]:
    """Return active penalties (escalation count, stopped tasks)."""
    stopped_count = await db.execute(
        select(func.count(ActivityLog.id)).where(
            ActivityLog.user_id == user_id,
            ActivityLog.status == "stopped",
        )
    )
    total_interruptions = stopped_count.scalar() or 0

    recent = await db.execute(
        select(ActivityLog.status)
        .where(ActivityLog.user_id == user_id)
        .order_by(ActivityLog.created_at.desc())
        .limit(10)
    )
    statuses = [row[0] for row in recent.all()]
    consecutive_interruptions = 0
    for s in statuses:
        if s == "stopped":
            consecutive_interruptions += 1
        else:
            break

    return [
        {"type": "total_interruptions", "count": total_interruptions},
        {"type": "consecutive_interruptions", "count": consecutive_interruptions},
    ]


async def _get_active_diets(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    """Return the user's active diet plans."""
    result = await db.execute(
        select(Diet).where(Diet.user_id == user_id, Diet.is_active.is_(True)).order_by(Diet.created_at)
    )
    diets = result.scalars().all()
    return [
        {
            "name": d.name,
            "direction": d.direction,
            "goal": d.goal,
        }
        for d in diets
    ]


async def _get_today_training(db: AsyncSession, user_id: uuid.UUID) -> dict | None:
    """Return today's training summary."""
    today = date.today()
    day_result = await db.execute(
        select(TrainingDay).where(
            TrainingDay.user_id == user_id,
            TrainingDay.target_date == today,
        )
    )
    days = list(day_result.scalars().all())
    if not days:
        return None

    day_ids = [d.id for d in days]
    logs_result = await db.execute(select(ActivityLog).where(ActivityLog.training_day_id.in_(day_ids)))
    logs = list(logs_result.scalars().all())

    completed = sum(1 for lg in logs if lg.status == "completed")
    stopped = sum(1 for lg in logs if lg.status == "stopped")
    planned = sum(1 for lg in logs if lg.status == "planned")

    return {
        "plan_count": len(days),
        "completed": completed,
        "stopped": stopped,
        "planned": planned,
    }


def format_context_abstract(context: dict) -> str:
    """Render context with opaque IDs — no real names. For strict providers."""
    parts = []
    parts.append("## User Stats")
    stats = context["stats"]
    parts.append(f"- Completed: {stats['completed']}")
    parts.append(f"- Stopped: {stats['stopped']}")
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
        # Abstract mode: real entity names MUST NOT be revealed (audit: the
        # abstract context previously leaked them from history).
        eid = h.get("entity_id") or h.get("id") or "?"
        line = f"- [{h['status']}] entity_id={eid} at {h.get('created_at')}"
        actual = h.get("actual_parameters")
        if actual:
            line += f" | actual: {json.dumps(actual, ensure_ascii=False)}"
        parts.append(line)
    parts.append("")

    return "\n".join(parts)


def format_context_for_prompt(context: dict) -> str:
    """Render the context dict into a prompt string for the LLM."""
    parts = []
    parts.append("## User Stats")
    stats = context["stats"]
    parts.append(f"- Total activities: {stats['total_activities']}")
    parts.append(f"- Completed: {stats['completed']}")
    parts.append(f"- Stopped: {stats['stopped']}")
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
        line = f"- [{h['status']}] {h.get('entity_name') or '(custom)'} at {h.get('created_at')}"
        actual = h.get("actual_parameters")
        if actual:
            line += f" | actual: {json.dumps(actual, ensure_ascii=False)}"
        parts.append(line)
    parts.append("")

    # Active diets
    diets = context.get("active_diets", [])
    if diets:
        parts.append("## Active Diet Plans")
        for d in diets:
            parts.append(f"- {d['name']} (direction: {d.get('direction') or 'general'}, goal: {d.get('goal') or '—'})")
        parts.append("Consider diet goals when selecting activities — align intensity and type.")
        parts.append("")

    # Today's training
    training = context.get("today_training")
    if training:
        parts.append("## Today's Training Status")
        parts.append(f"- Plans: {training.get('plan_count', 0)}")
        parts.append(f"- Tasks completed: {training.get('completed', 0)}")
        parts.append(f"- Tasks remaining: {training.get('planned', 0)}")
        parts.append(f"- Tasks stopped: {training.get('stopped', 0)}")
        parts.append("Avoid overloading an already busy training day.")
        parts.append("")

    parts.append("## Active Penalties")
    penalties = context.get("active_penalties", [])
    if penalties:
        for p in penalties:
            parts.append(f"- {p['type']}: {p['count']}")
    else:
        parts.append("- None")

    return "\n".join(parts)
