"""Platform Social — repositories (S0–S1).

Data access layer that ONLY touches social_* tables — never private domain tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.social.models import SocialConsent, SocialProfile, SocialSubject

# ---------------------------------------------------------------------------
# S0 — Profiles
# ---------------------------------------------------------------------------


async def get_profile(db: AsyncSession, user_id: uuid.UUID) -> SocialProfile | None:
    result = await db.execute(
        select(SocialProfile).where(SocialProfile.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def get_profile_by_alias(db: AsyncSession, alias_normalized: str) -> SocialProfile | None:
    result = await db.execute(
        select(SocialProfile).where(SocialProfile.alias_normalized == alias_normalized)
    )
    return result.scalar_one_or_none()


async def create_profile(
    db: AsyncSession,
    user_id: uuid.UUID,
    alias: str,
    alias_normalized: str,
    bio: str | None = None,
) -> SocialProfile:
    profile = SocialProfile(
        user_id=user_id,
        alias=alias,
        alias_normalized=alias_normalized,
        bio=bio,
    )
    db.add(profile)
    await db.flush()
    return profile


async def update_profile(
    db: AsyncSession,
    user_id: uuid.UUID,
    *,
    bio: str | None = None,
    discoverable: bool | None = None,
    show_in_feed: bool | None = None,
) -> SocialProfile | None:
    profile = await get_profile(db, user_id)
    if profile is None:
        return None
    if bio is not None:
        profile.bio = bio
    if discoverable is not None:
        profile.discoverable = discoverable
    if show_in_feed is not None:
        profile.show_in_feed = show_in_feed
    profile.updated_at = datetime.utcnow()
    await db.flush()
    return profile


async def delete_profile(db: AsyncSession, user_id: uuid.UUID) -> bool:
    profile = await get_profile(db, user_id)
    if profile is None:
        return False
    await db.delete(profile)
    await db.flush()
    return True


# ---------------------------------------------------------------------------
# S0 — Consent
# ---------------------------------------------------------------------------


async def get_latest_consent(db: AsyncSession, user_id: uuid.UUID) -> SocialConsent | None:
    result = await db.execute(
        select(SocialConsent)
        .where(SocialConsent.user_id == user_id)
        .order_by(SocialConsent.consent_version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def record_consent(
    db: AsyncSession,
    user_id: uuid.UUID,
    consent_version: int,
    ip_address_hash: str | None = None,
) -> SocialConsent:
    consent = SocialConsent(
        user_id=user_id,
        consent_version=consent_version,
        ip_address_hash=ip_address_hash,
    )
    db.add(consent)
    await db.flush()
    return consent


async def has_accepted_consent(db: AsyncSession, user_id: uuid.UUID, min_version: int = 1) -> bool:
    latest = await get_latest_consent(db, user_id)
    return latest is not None and latest.consent_version >= min_version


# ---------------------------------------------------------------------------
# S1 — Subjects
# ---------------------------------------------------------------------------


async def get_subject(db: AsyncSession, subject_id: uuid.UUID) -> SocialSubject | None:
    result = await db.execute(
        select(SocialSubject).where(
            SocialSubject.id == subject_id, SocialSubject.is_active
        )
    )
    return result.scalar_one_or_none()


async def list_owner_subjects(
    db: AsyncSession, owner_id: uuid.UUID,
) -> list[SocialSubject]:
    result = await db.execute(        select(SocialSubject).where(
            SocialSubject.owner_id == owner_id, SocialSubject.is_active
        )
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
    subject.tombstoned_at = datetime.utcnow()
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
