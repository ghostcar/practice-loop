"""Dynamic Orchestration Service (Revision 2 / ADR-068 / ADR-106 / R8.1 audit).

Manages active operational modes and applies frozen agency & protocol snapshots.
"""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dynamic import DynamicDefinition, DynamicRun
from app.services.capability import ActorContext

logger = logging.getLogger(__name__)


async def create_dynamic_definition(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    description: str | None = None,
    persona_id: uuid.UUID | None = None,
    agency_overlay: dict[str, Any] | None = None,
    included_protocol_ids: list[str] | None = None,
    included_session_template_ids: list[str] | None = None,
    granted_capabilities: list[str] | None = None,
    actor: ActorContext | None = None,
) -> DynamicDefinition:
    """Create a new reusable dynamic mode specification (R8.1 audit)."""
    _ctx = actor or ActorContext(actor_id=user_id, actor_type="human", source="web")
    dynamic_def = DynamicDefinition(
        user_id=user_id,
        title=title,
        description=description,
        persona_id=persona_id,
        agency_overlay=agency_overlay or {},
        included_protocol_ids=included_protocol_ids or [],
        included_session_template_ids=included_session_template_ids or [],
        granted_capabilities=granted_capabilities or [],
    )
    db.add(dynamic_def)
    logger.debug("DynamicDefinition '%s' created by actor %s", title, _ctx.actor_id)
    await db.flush()
    return dynamic_def


async def get_active_dynamic_run(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> DynamicRun | None:
    """Retrieve currently active dynamic run for the user."""
    now = datetime.datetime.now(datetime.UTC)
    query = select(DynamicRun).where(
        DynamicRun.user_id == user_id,
        DynamicRun.status == "active",
        (DynamicRun.expires_at.is_(None) | (DynamicRun.expires_at >= now)),
    )
    res = await db.execute(query)
    return res.scalar_one_or_none()


async def start_dynamic_run(
    db: AsyncSession,
    user_id: uuid.UUID,
    dynamic_id: uuid.UUID,
    duration_days: int | None = None,
    actor: ActorContext | None = None,
) -> DynamicRun:
    """Start a dynamic run, creating an immutable snapshot (R8.1 audit)."""
    _ctx = actor or ActorContext(actor_id=user_id, actor_type="human", source="web")
    res = await db.execute(select(DynamicDefinition).where(DynamicDefinition.id == dynamic_id))
    dynamic_def = res.scalar_one_or_none()
    if dynamic_def is None:
        raise ValueError(f"DynamicDefinition {dynamic_id} not found")

    existing_active = await get_active_dynamic_run(db, user_id)
    if existing_active is not None:
        existing_active.status = "completed"
        existing_active.ended_at = datetime.datetime.now(datetime.UTC)

    now = datetime.datetime.now(datetime.UTC)
    expires_at = now + datetime.timedelta(days=duration_days) if duration_days else None

    snapshot = {
        "dynamic_id": str(dynamic_def.id),
        "title": dynamic_def.title,
        "persona_id": str(dynamic_def.persona_id) if dynamic_def.persona_id else None,
        "agency_overlay": dynamic_def.agency_overlay,
        "included_protocol_ids": dynamic_def.included_protocol_ids,
        "included_session_template_ids": dynamic_def.included_session_template_ids,
        "granted_capabilities": dynamic_def.granted_capabilities,
        "started_at": now.isoformat(),
        "__audit__": {"actor_id": str(_ctx.actor_id), "source": _ctx.source},
    }

    run = DynamicRun(
        user_id=user_id,
        dynamic_id=dynamic_id,
        status="active",
        started_at=now,
        expires_at=expires_at,
        frozen_dynamic_snapshot=snapshot,
    )
    db.add(run)
    logger.debug("DynamicRun started by actor %s", _ctx.actor_id)
    await db.flush()
    return run


async def end_dynamic_run(
    db: AsyncSession,
    run_id: uuid.UUID,
    actor: ActorContext | None = None,
) -> DynamicRun:
    """Explicitly conclude an active dynamic run (R8.1 audit)."""
    res = await db.execute(select(DynamicRun).where(DynamicRun.id == run_id))
    run = res.scalar_one_or_none()
    if run is None:
        raise ValueError(f"DynamicRun {run_id} not found")

    run.status = "completed"
    run.ended_at = datetime.datetime.now(datetime.UTC)
    if isinstance(run.frozen_dynamic_snapshot, dict):
        run.frozen_dynamic_snapshot = dict(run.frozen_dynamic_snapshot)
        if actor:
            run.frozen_dynamic_snapshot["__audit__"] = {
                "actor_id": str(actor.actor_id),
                "source": actor.source,
            }

    logger.debug("DynamicRun %s ended by actor %s", run_id, (actor and actor.actor_id) or "system")
    await db.flush()
    return run