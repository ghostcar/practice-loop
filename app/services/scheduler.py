"""Soft scheduler: deterministic due-practice selector (R8.1 audit).

Uses UserEntityOptIn.next_due_at and retry_not_before_at to determine
which enabled practices are due for the user. Doesn't replace LLM — just
provides a deterministic fallback and due-awareness.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.entity import Entity
from app.models.opt_in import UserEntityOptIn
from app.services.capability import ActorContext

logger = logging.getLogger(__name__)


async def get_due_practices(
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 10,
) -> list[dict]:
    """Return enabled practices that are due (next_due_at <= now) and not blocked by retry."""
    now = datetime.now(UTC)

    # ADR-106: personal entities (owner_id == user.id) are approved by default
    # and auto-opt-in at creation — the opt-in join already covers them.
    result = await db.execute(
        select(UserEntityOptIn, Entity)
        .join(Entity, UserEntityOptIn.entity_id == Entity.id)
        .where(
            UserEntityOptIn.user_id == user_id,
            UserEntityOptIn.is_opted_in.is_(True),
            (UserEntityOptIn.next_due_at <= now) | (UserEntityOptIn.next_due_at.is_(None)),
            (UserEntityOptIn.retry_not_before_at.is_(None)) | (UserEntityOptIn.retry_not_before_at <= now),
        )
        .order_by(UserEntityOptIn.next_due_at.asc().nulls_first())
        .limit(limit)
    )

    practices = []
    for opt_in, entity in result:
        practices.append({
            "entity_id": str(entity.id),
            "entity_name": entity.real_name,
            "category": entity.category,
            "type": entity.type,
            "desire_level": opt_in.desire_level,
            "rating": opt_in.rating,
            "next_due_at": opt_in.next_due_at.isoformat() if opt_in.next_due_at else None,
        })

    return practices


async def set_next_due(
    db: AsyncSession,
    user_id: uuid.UUID,
    entity_id: uuid.UUID,
    interval_hours: int = 48,
    actor: ActorContext | None = None,
) -> None:
    """Set next_due_at for a practice after completion. Clears retry block (R8.1 audit)."""
    _ctx = actor or ActorContext(actor_id=user_id, actor_type="human", source="web")
    now = datetime.now(UTC)

    result = await db.execute(
        select(UserEntityOptIn).where(
            UserEntityOptIn.user_id == user_id,
            UserEntityOptIn.entity_id == entity_id,
        )
    )
    opt_in = result.scalar_one_or_none()
    if opt_in:
        opt_in.next_due_at = now + timedelta(hours=interval_hours)
        opt_in.retry_not_before_at = None
        db.add(opt_in)

    logger.debug("set_next_due entity=%s interval=%dh by actor %s", entity_id, interval_hours, _ctx.actor_id)


async def set_retry_block(
    db: AsyncSession,
    user_id: uuid.UUID,
    entity_id: uuid.UUID,
    block_hours: int = 24,
    actor: ActorContext | None = None,
) -> None:
    """Block a practice from being re-scheduled for block_hours (after stop/skip) (R8.1 audit)."""
    _ctx = actor or ActorContext(actor_id=user_id, actor_type="human", source="web")
    now = datetime.now(UTC)

    result = await db.execute(
        select(UserEntityOptIn).where(
            UserEntityOptIn.user_id == user_id,
            UserEntityOptIn.entity_id == entity_id,
        )
    )
    opt_in = result.scalar_one_or_none()
    if opt_in:
        opt_in.retry_not_before_at = now + timedelta(hours=block_hours)
        db.add(opt_in)
        await db.flush()

    logger.debug("set_retry_block entity=%s block=%dh by actor %s", entity_id, block_hours, _ctx.actor_id)