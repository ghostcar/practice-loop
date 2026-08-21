"""Dynamic Orchestration Service (Revision 2 / ADR-068 / ADR-106).

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
) -> DynamicDefinition:
    """Create a new reusable dynamic mode specification."""
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
) -> DynamicRun:
    """Start a dynamic run, creating an immutable snapshot of all rules at launch."""
    res = await db.execute(select(DynamicDefinition).where(DynamicDefinition.id == dynamic_id))
    dynamic_def = res.scalar_one_or_none()
    if dynamic_def is None:
        raise ValueError(f"DynamicDefinition {dynamic_id} not found")

    # Deactivate existing active runs
    existing_active = await get_active_dynamic_run(db, user_id)
    if existing_active is not None:
        existing_active.status = "completed"
        existing_active.ended_at = datetime.datetime.now(datetime.UTC)

    now = datetime.datetime.now(datetime.UTC)
    expires_at = now + datetime.timedelta(days=duration_days) if duration_days else None

    # Immutable frozen snapshot of rules
    snapshot = {
        "dynamic_id": str(dynamic_def.id),
        "title": dynamic_def.title,
        "persona_id": str(dynamic_def.persona_id) if dynamic_def.persona_id else None,
        "agency_overlay": dynamic_def.agency_overlay,
        "included_protocol_ids": dynamic_def.included_protocol_ids,
        "included_session_template_ids": dynamic_def.included_session_template_ids,
        "granted_capabilities": dynamic_def.granted_capabilities,
        "started_at": now.isoformat(),
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
    await db.flush()
    return run


async def end_dynamic_run(
    db: AsyncSession,
    run_id: uuid.UUID,
) -> DynamicRun:
    """Explicitly conclude an active dynamic run."""
    res = await db.execute(select(DynamicRun).where(DynamicRun.id == run_id))
    run = res.scalar_one_or_none()
    if run is None:
        raise ValueError(f"DynamicRun {run_id} not found")

    run.status = "completed"
    run.ended_at = datetime.datetime.now(datetime.UTC)
    await db.flush()
    return run
