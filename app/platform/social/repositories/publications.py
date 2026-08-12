"""Social publications — feed + CRUD (S3)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.social.models import SocialBlock, SocialPublication, SocialRelationship


async def create_publication(
    db: AsyncSession,
    owner_id: uuid.UUID,
    subject_id: uuid.UUID,
    visibility: str,
    snapshot: dict,
    snapshot_hash: str,
    subject_namespace: str,
) -> SocialPublication:
    pub = SocialPublication(
        owner_id=owner_id,
        subject_id=subject_id,
        visibility=visibility,
        snapshot=snapshot,
        snapshot_hash=snapshot_hash,
        subject_namespace=subject_namespace,
    )
    db.add(pub)
    await db.flush()
    return pub


async def withdraw_publication(
    db: AsyncSession,
    publication_id: uuid.UUID,
    owner_id: uuid.UUID,
) -> SocialPublication | None:
    result = await db.execute(
        select(SocialPublication).where(
            SocialPublication.id == publication_id,
            SocialPublication.owner_id == owner_id,
            SocialPublication.is_active,
        )
    )
    pub = result.scalar_one_or_none()
    if pub is None:
        return None
    pub.is_active = False
    pub.withdrawn_at = datetime.utcnow()
    await db.flush()
    return pub


async def list_feed(
    db: AsyncSession,
    viewer_id: uuid.UUID,
    *,
    namespace: str | None = None,
    cursor: datetime | None = None,
    limit: int = 20,
) -> list[SocialPublication]:
    """Cursor-based feed.

    Shows:
    - public publications from anyone (not blocked)
    - relationship_only publications from accepted relationships (not blocked)
    - unlisted publications: same rules as public but not shown in default feed

    Never joins private Tracker/Timer tables.
    """
    # Subquery: users who have an accepted relationship with viewer
    accepted_rel = (
        select(SocialRelationship.requester_id)
        .where(
            SocialRelationship.recipient_id == viewer_id,
            SocialRelationship.status == "accepted",
        )
        .union(
            select(SocialRelationship.recipient_id).where(
                SocialRelationship.requester_id == viewer_id,
                SocialRelationship.status == "accepted",
            )
        )
    ).subquery()

    # Subquery: users blocked by or blocking viewer
    blocked = (
        select(SocialBlock.blocked_id)
        .where(SocialBlock.blocker_id == viewer_id, SocialBlock.is_active)
        .union(select(SocialBlock.blocker_id).where(SocialBlock.blocked_id == viewer_id, SocialBlock.is_active))
    ).subquery()

    query = (
        select(SocialPublication)
        .where(
            SocialPublication.is_active,
            SocialPublication.owner_id.not_in(select(blocked.c.blocked_id)),
            (
                (SocialPublication.visibility == "public")
                | (SocialPublication.owner_id.in_(select(accepted_rel.c.requester_id)))
            ),
        )
        .order_by(SocialPublication.created_at.desc())
        .limit(limit)
    )

    if namespace:
        query = query.where(SocialPublication.subject_namespace == namespace)
    if cursor:
        query = query.where(SocialPublication.created_at < cursor)

    result = await db.execute(query)
    return list(result.scalars().all())


async def get_publication(
    db: AsyncSession,
    publication_id: uuid.UUID,
) -> SocialPublication | None:
    result = await db.execute(select(SocialPublication).where(SocialPublication.id == publication_id))
    return result.scalar_one_or_none()


async def list_owner_publications(
    db: AsyncSession,
    owner_id: uuid.UUID,
) -> list[SocialPublication]:
    result = await db.execute(
        select(SocialPublication)
        .where(SocialPublication.owner_id == owner_id)
        .order_by(SocialPublication.created_at.desc())
    )
    return list(result.scalars().all())
