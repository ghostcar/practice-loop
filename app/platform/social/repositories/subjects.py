"""Social subjects — registry (S1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.social.models import SocialSubject


async def get_subject(db: AsyncSession, subject_id: uuid.UUID) -> SocialSubject | None:
    result = await db.execute(select(SocialSubject).where(SocialSubject.id == subject_id, SocialSubject.is_active))
    return result.scalar_one_or_none()


async def list_owner_subjects(
    db: AsyncSession,
    owner_id: uuid.UUID,
) -> list[SocialSubject]:
    result = await db.execute(
        select(SocialSubject)
        .where(SocialSubject.owner_id == owner_id, SocialSubject.is_active)
        .order_by(SocialSubject.created_at.desc())
    )
    return list(result.scalars().all())


async def register_subject(
    db: AsyncSession,
    owner_id: uuid.UUID,
    subject_type: str,
    domain_object_id: str,
    projection_snapshot: dict | None = None,
    projection_version: int = 1,
) -> SocialSubject:
    subject = SocialSubject(
        owner_id=owner_id,
        subject_type=subject_type,
        domain_object_id=domain_object_id,
        projection_snapshot=projection_snapshot,
        projection_version=projection_version,
    )
    db.add(subject)
    await db.flush()
    return subject


async def tombstone_subject(db: AsyncSession, subject_id: uuid.UUID) -> SocialSubject | None:
    subject = await get_subject(db, subject_id)
    if subject is None:
        return None
    subject.is_active = False
    subject.tombstoned_at = datetime.now(UTC)
    await db.flush()
    return subject


async def update_projection(
    db: AsyncSession,
    subject_id: uuid.UUID,
    projection_snapshot: dict,
    projection_version: int,
) -> SocialSubject | None:
    subject = await get_subject(db, subject_id)
    if subject is None:
        return None
    subject.projection_snapshot = projection_snapshot
    subject.projection_version = projection_version
    await db.flush()
    return subject
