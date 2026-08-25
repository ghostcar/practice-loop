"""Protocols Service — business logic extracted from app.api.protocols.

Covers: constants, steps parsing, capability checks, ownership checks,
page contexts (queries), and mutation wrappers (form → service calls).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.protocol import (
    ProtocolDefinition,
    ProtocolRun,
    ProtocolStep,
    ProtocolStepLog,
    ProtocolStepType,
    TimingSpecType,
)
from app.services.capability import ActorContext, CapabilityAuthorizer
from app.services.protocol import (
    create_protocol_definition,
    execute_protocol_step,
    start_protocol_run,
)

# ── Constants ──
STEP_TYPES = [t.value for t in ProtocolStepType]
TIMING_TYPES = [t.value for t in TimingSpecType]
CATEGORIES = ("prep", "recovery", "routine", "discipline")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def parse_steps_form(steps_json: str) -> list[dict[str, Any]]:
    """Parse steps from JSON field of the builder form."""
    try:
        raw = json.loads(steps_json or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(raw, list):
        return []
    steps: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or not item.get("title"):
            continue
        timing = item.get("timing_spec") or {}
        steps.append(
            {
                "title": str(item["title"])[:255],
                "step_type": (item.get("step_type", "activity") if item.get("step_type") in STEP_TYPES else "activity"),
                "reference_id": item.get("reference_id") or None,
                "timing_spec": {
                    "type": (timing.get("type", "rel_after") if timing.get("type") in TIMING_TYPES else "rel_after"),
                    "offset_seconds": max(0, int(timing.get("offset_seconds", 0) or 0)),
                },
                "custom_params": item.get("custom_params") or {},
            }
        )
    return steps


async def get_own_protocol(db: AsyncSession, protocol_id: uuid.UUID, user_id: uuid.UUID) -> ProtocolDefinition:
    """Ownership-checked protocol fetch. Raises HTTPException 404."""
    proto = (
        await db.execute(
            select(ProtocolDefinition).where(
                ProtocolDefinition.id == protocol_id,
                ProtocolDefinition.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if proto is None:
        raise HTTPException(status_code=404, detail="Protocol not found")
    return proto


async def require_protocol_capability(
    db: AsyncSession,
    user,
    capability_code: str,
    protocol_id: uuid.UUID | None = None,
) -> None:
    """Verify the user (or their delegate) has the required protocol capability.

    Owner always passes. Delegated partners must have a matching CapabilityGrantV2,
    D/s CapabilityGrant, SocialGrant, or CommunityMemberDelegation.
    Capability codes: protocol.view, protocol.create, protocol.start,
    protocol.confirm, protocol.edit_definition, protocol.delete.
    """
    actor = ActorContext(actor_id=user.id, actor_type="user", source="web")
    allowed, reason = await CapabilityAuthorizer.can_act(
        db=db,
        actor=actor,
        issuer_user_id=user.id,
        capability_code=capability_code,
        resource_id=protocol_id,
    )
    if not allowed:
        raise HTTPException(status_code=403, detail=reason)


# ═══════════════════════════════════════════════════════════════════════════
# Page contexts
# ═══════════════════════════════════════════════════════════════════════════


async def get_protocols_page_context(db: AsyncSession, user_id: uuid.UUID) -> dict:
    """Build template context for /protocols (list + active runs)."""
    protos_result = await db.execute(
        select(ProtocolDefinition)
        .where(ProtocolDefinition.user_id == user_id)
        .order_by(ProtocolDefinition.created_at.desc())
    )
    protos = list(protos_result.scalars().all())

    runs_result = await db.execute(
        select(ProtocolRun).where(ProtocolRun.user_id == user_id).order_by(ProtocolRun.created_at.desc())
    )
    active_runs = [r for r in runs_result.scalars().all() if r.status in ("scheduled", "active")]

    return {
        "protocols": protos,
        "active_runs": active_runs,
        "step_types": STEP_TYPES,
        "categories": CATEGORIES,
    }


def serialize_protocol_steps(proto: ProtocolDefinition | None) -> list[dict[str, Any]]:
    """Serialize steps for the builder template."""
    if proto is None:
        return []
    steps: list[dict[str, Any]] = []
    for s in proto.steps:
        steps.append(
            {
                "id": str(s.id),
                "step_order": s.step_order,
                "title": s.title,
                "step_type": s.step_type,
                "reference_id": str(s.reference_id) if s.reference_id else "",
                "timing_spec": s.timing_spec or {},
                "custom_params": s.custom_params or {},
            }
        )
    return steps


def get_builder_common_context() -> dict:
    """Return common context keys for the protocol builder page."""
    return {
        "step_types": STEP_TYPES,
        "timing_types": TIMING_TYPES,
        "categories": CATEGORIES,
    }


async def get_run_page_context(db: AsyncSession, user_id: uuid.UUID, run_id: uuid.UUID) -> dict | None:
    """Build template context for /protocols/{id}/run. Returns None if not found."""
    run = (
        await db.execute(select(ProtocolRun).where(ProtocolRun.id == run_id, ProtocolRun.user_id == user_id))
    ).scalar_one_or_none()
    if run is None:
        return None

    logs_result = await db.execute(
        select(ProtocolStepLog).where(ProtocolStepLog.run_id == run.id).order_by(ProtocolStepLog.planned_at)
    )
    logs = list(logs_result.scalars().all())

    proto = None
    if run.protocol_id:
        proto = (
            await db.execute(select(ProtocolDefinition).where(ProtocolDefinition.id == run.protocol_id))
        ).scalar_one_or_none()

    return {
        "run": run,
        "proto": proto,
        "logs": logs,
        "step_types": STEP_TYPES,
    }


# ═══════════════════════════════════════════════════════════════════════════
# Mutation wrappers
# ═══════════════════════════════════════════════════════════════════════════


async def create_protocol_from_form(
    db: AsyncSession,
    user,
    *,
    title: str,
    description: str = "",
    category: str = "prep",
    anchor_type: str = "session_bound",
    steps_json: str = "[]",
) -> ProtocolDefinition:
    """Create a protocol definition with steps from form data."""
    if category not in CATEGORIES:
        category = "prep"
    if anchor_type not in ("independent", "session_bound", "timer_bound"):
        anchor_type = "session_bound"
    await require_protocol_capability(db, user, "protocol.create")
    steps = parse_steps_form(steps_json)
    proto = await create_protocol_definition(
        db,
        user.id,
        title=title.strip()[:255],
        description=description.strip() or None,
        category=category,
        anchor_type=anchor_type,
        steps=steps,
    )
    await db.flush()
    return proto


async def update_protocol_from_form(
    db: AsyncSession,
    user,
    protocol_id: uuid.UUID,
    *,
    title: str,
    description: str = "",
    category: str = "prep",
    anchor_type: str = "session_bound",
    steps_json: str = "[]",
) -> ProtocolDefinition:
    """Update a protocol definition — replaces steps entirely."""
    await require_protocol_capability(db, user, "protocol.edit_definition", protocol_id)
    proto = await get_own_protocol(db, protocol_id, user.id)

    if category in CATEGORIES:
        proto.category = category
    if anchor_type in ("independent", "session_bound", "timer_bound"):
        proto.anchor_type = anchor_type
    proto.title = title.strip()[:255]
    proto.description = description.strip() or None

    # Replace steps entirely (cascade delete-orphan on relationship)
    proto.steps.clear()
    await db.flush()
    steps = parse_steps_form(steps_json)
    for idx, s in enumerate(steps, start=1):
        ref_id = uuid.UUID(s["reference_id"]) if s.get("reference_id") else None
        proto.steps.append(
            ProtocolStep(
                step_order=idx,
                title=s["title"],
                step_type=s["step_type"],
                reference_id=ref_id,
                timing_spec=s["timing_spec"],
                custom_params=s["custom_params"],
            )
        )
    await db.flush()
    return proto


async def delete_protocol_by_id(
    db: AsyncSession,
    user,
    protocol_id: uuid.UUID,
) -> None:
    """Delete a protocol (capability + ownership checked)."""
    await require_protocol_capability(db, user, "protocol.delete", protocol_id)
    proto = await get_own_protocol(db, protocol_id, user.id)
    await db.delete(proto)
    await db.flush()


async def start_protocol_from_form(
    db: AsyncSession,
    user,
    protocol_id: uuid.UUID,
    anchor_time: str = "",
) -> ProtocolRun:
    """Start a protocol run from form data."""
    await require_protocol_capability(db, user, "protocol.start", protocol_id)
    proto = await get_own_protocol(db, protocol_id, user.id)
    try:
        anchor = datetime.fromisoformat(anchor_time) if anchor_time else datetime.now(UTC)
    except ValueError:
        anchor = datetime.now(UTC)
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=UTC)
    run = await start_protocol_run(db, user.id, proto.id, anchor)
    await db.flush()
    return run


async def complete_protocol_step_from_form(
    db: AsyncSession,
    user,
    run_id: uuid.UUID,
    step_log_id: uuid.UUID,
    result_payload: str = "",
) -> ProtocolRun | None:
    """Complete a step in an active protocol run."""
    await require_protocol_capability(db, user, "protocol.confirm")
    run = (
        await db.execute(select(ProtocolRun).where(ProtocolRun.id == run_id, ProtocolRun.user_id == user.id))
    ).scalar_one_or_none()
    if run is None:
        return None

    actor = ActorContext(actor_id=user.id, actor_type="user", source="owner_manual")
    payload: dict[str, Any] = {}
    if result_payload:
        try:
            parsed = json.loads(result_payload)
            if isinstance(parsed, dict):
                payload = parsed
        except json.JSONDecodeError:
            payload = {}
    try:
        await execute_protocol_step(db, step_log_id, actor, payload)
        await db.flush()
    except ValueError:
        await db.rollback()
    return run
