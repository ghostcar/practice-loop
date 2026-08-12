"""Social relationships — invitations, blocks, grants (S2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.social.models import (
    SocialBlock,
    SocialGrant,
    SocialRelationship,
)

INVITE_COOLDOWN_HOURS = 24


async def _is_blocked(db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID) -> bool:
    """Check if either user has blocked the other."""
    result = await db.execute(
        select(SocialBlock)
        .where(
            ((SocialBlock.blocker_id == user_a) & (SocialBlock.blocked_id == user_b))
            | ((SocialBlock.blocker_id == user_b) & (SocialBlock.blocked_id == user_a)),
            SocialBlock.is_active,
        )
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def create_invitation(
    db: AsyncSession,
    requester_id: uuid.UUID,
    recipient_id: uuid.UUID,
    display_role: str = "viewer",
) -> SocialRelationship:
    rel = SocialRelationship(
        requester_id=requester_id,
        recipient_id=recipient_id,
        status="pending",
        display_role=display_role,
    )
    db.add(rel)
    await db.flush()
    return rel


async def get_relationship(db: AsyncSession, relationship_id: uuid.UUID) -> SocialRelationship | None:
    result = await db.execute(select(SocialRelationship).where(SocialRelationship.id == relationship_id))
    return result.scalar_one_or_none()


async def get_relationship_by_pair(
    db: AsyncSession,
    user_a: uuid.UUID,
    user_b: uuid.UUID,
) -> SocialRelationship | None:
    result = await db.execute(
        select(SocialRelationship).where(
            ((SocialRelationship.requester_id == user_a) & (SocialRelationship.recipient_id == user_b))
            | ((SocialRelationship.requester_id == user_b) & (SocialRelationship.recipient_id == user_a)),
        )
    )
    return result.scalar_one_or_none()


async def accept_invitation(
    db: AsyncSession,
    relationship_id: uuid.UUID,
    user_id: uuid.UUID,
) -> SocialRelationship | None:
    rel = await get_relationship(db, relationship_id)
    if rel is None or rel.recipient_id != user_id or rel.status != "pending":
        return None
    rel.status = "accepted"
    rel.updated_at = datetime.now(UTC)
    await db.flush()
    return rel


async def decline_invitation(
    db: AsyncSession,
    relationship_id: uuid.UUID,
    user_id: uuid.UUID,
) -> SocialRelationship | None:
    rel = await get_relationship(db, relationship_id)
    if rel is None or rel.recipient_id != user_id or rel.status != "pending":
        return None
    rel.status = "declined"
    rel.cooldown_until = datetime.now(UTC) + timedelta(hours=INVITE_COOLDOWN_HOURS)
    rel.updated_at = datetime.now(UTC)
    await db.flush()
    return rel


async def revoke_relationship(
    db: AsyncSession,
    relationship_id: uuid.UUID,
    user_id: uuid.UUID,
) -> SocialRelationship | None:
    rel = await get_relationship(db, relationship_id)
    if rel is None:
        return None
    if user_id not in (rel.requester_id, rel.recipient_id):
        return None
    if rel.status not in ("pending", "accepted"):
        return None
    rel.status = "revoked"
    rel.updated_at = datetime.now(UTC)
    await db.flush()
    return rel


async def list_user_relationships(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[SocialRelationship]:
    result = await db.execute(
        select(SocialRelationship)
        .where(
            (SocialRelationship.requester_id == user_id) | (SocialRelationship.recipient_id == user_id),
        )
        .order_by(SocialRelationship.updated_at.desc())
    )
    return list(result.scalars().all())


async def list_pending_invitations(
    db: AsyncSession,
    user_id: uuid.UUID,
) -> list[SocialRelationship]:
    result = await db.execute(
        select(SocialRelationship)
        .where(
            SocialRelationship.recipient_id == user_id,
            SocialRelationship.status == "pending",
        )
        .order_by(SocialRelationship.created_at.desc())
    )
    return list(result.scalars().all())


async def block_user(
    db: AsyncSession,
    blocker_id: uuid.UUID,
    blocked_id: uuid.UUID,
    reason: str | None = None,
) -> SocialBlock:
    block = SocialBlock(blocker_id=blocker_id, blocked_id=blocked_id, reason=reason)
    db.add(block)
    await db.flush()
    return block


async def unblock_user(
    db: AsyncSession,
    blocker_id: uuid.UUID,
    blocked_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(SocialBlock).where(
            SocialBlock.blocker_id == blocker_id,
            SocialBlock.blocked_id == blocked_id,
            SocialBlock.is_active,
        )
    )
    block = result.scalar_one_or_none()
    if block is None:
        return False
    block.is_active = False
    await db.flush()
    return True


async def list_user_blocks(db: AsyncSession, user_id: uuid.UUID) -> list[SocialBlock]:
    result = await db.execute(
        select(SocialBlock)
        .where(
            SocialBlock.blocker_id == user_id,
            SocialBlock.is_active,
        )
        .order_by(SocialBlock.created_at.desc())
    )
    return list(result.scalars().all())


async def create_grant(
    db: AsyncSession,
    relationship_id: uuid.UUID,
    scope_type: str,
    caps: dict,
    *,
    scope_namespace: str | None = None,
    subject_id: uuid.UUID | None = None,
    expires_at: datetime | None = None,
) -> SocialGrant:
    grant = SocialGrant(
        relationship_id=relationship_id,
        scope_type=scope_type,
        scope_namespace=scope_namespace,
        subject_id=subject_id,
        caps=caps,
        status="proposed",
        expires_at=expires_at,
    )
    db.add(grant)
    await db.flush()
    return grant


async def accept_grant(
    db: AsyncSession,
    grant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> SocialGrant | None:
    result = await db.execute(
        select(SocialGrant)
        .join(SocialRelationship)
        .where(
            SocialGrant.id == grant_id,
            SocialGrant.status == "proposed",
            SocialRelationship.recipient_id == user_id,
        )
    )
    grant = result.scalar_one_or_none()
    if grant is None:
        return None
    grant.status = "accepted"
    grant.updated_at = datetime.now(UTC)
    await db.flush()
    return grant


async def revoke_grant(
    db: AsyncSession,
    grant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> SocialGrant | None:
    result = await db.execute(
        select(SocialGrant)
        .join(SocialRelationship)
        .where(
            SocialGrant.id == grant_id,
            SocialGrant.status.in_(["proposed", "accepted"]),
            ((SocialRelationship.requester_id == user_id) | (SocialRelationship.recipient_id == user_id)),
        )
    )
    grant = result.scalar_one_or_none()
    if grant is None:
        return None
    grant.status = "revoked"
    grant.updated_at = datetime.now(UTC)
    await db.flush()
    return grant


async def list_grants_for_relationship(
    db: AsyncSession,
    relationship_id: uuid.UUID,
) -> list[SocialGrant]:
    result = await db.execute(
        select(SocialGrant)
        .where(
            SocialGrant.relationship_id == relationship_id,
        )
        .order_by(SocialGrant.created_at.desc())
    )
    return list(result.scalars().all())
