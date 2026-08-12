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


# ---------------------------------------------------------------------------
# S2 — Relationships
# ---------------------------------------------------------------------------

from app.platform.social.models import (  # noqa: E402
    SocialBlock,
    SocialGrant,
    SocialNotification,
    SocialRelationship,
)

INVITE_COOLDOWN_HOURS = 24


async def _is_blocked(db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID) -> bool:
    """Check if either user has blocked the other."""
    result = await db.execute(
        select(SocialBlock).where(
            (
                (SocialBlock.blocker_id == user_a) & (SocialBlock.blocked_id == user_b)
            ) | (
                (SocialBlock.blocker_id == user_b) & (SocialBlock.blocked_id == user_a)
            ),
            SocialBlock.is_active,
        ).limit(1)
    )
    return result.scalar_one_or_none() is not None


# --- Invitations ---


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
    result = await db.execute(
        select(SocialRelationship).where(SocialRelationship.id == relationship_id)
    )
    return result.scalar_one_or_none()


async def get_relationship_by_pair(
    db: AsyncSession, user_a: uuid.UUID, user_b: uuid.UUID,
) -> SocialRelationship | None:
    result = await db.execute(
        select(SocialRelationship).where(
            (
                (SocialRelationship.requester_id == user_a)
                & (SocialRelationship.recipient_id == user_b)
            ) | (
                (SocialRelationship.requester_id == user_b)
                & (SocialRelationship.recipient_id == user_a)
            ),
        )
    )
    return result.scalar_one_or_none()


async def accept_invitation(
    db: AsyncSession, relationship_id: uuid.UUID, user_id: uuid.UUID,
) -> SocialRelationship | None:
    rel = await get_relationship(db, relationship_id)
    if rel is None or rel.recipient_id != user_id or rel.status != "pending":
        return None
    rel.status = "accepted"
    rel.updated_at = datetime.utcnow()
    await db.flush()
    return rel


async def decline_invitation(
    db: AsyncSession, relationship_id: uuid.UUID, user_id: uuid.UUID,
) -> SocialRelationship | None:
    rel = await get_relationship(db, relationship_id)
    if rel is None or rel.recipient_id != user_id or rel.status != "pending":
        return None
    rel.status = "declined"
    rel.cooldown_until = datetime.utcnow() + __import__("datetime").timedelta(hours=INVITE_COOLDOWN_HOURS)
    rel.updated_at = datetime.utcnow()
    await db.flush()
    return rel


async def revoke_relationship(
    db: AsyncSession, relationship_id: uuid.UUID, user_id: uuid.UUID,
) -> SocialRelationship | None:
    rel = await get_relationship(db, relationship_id)
    if rel is None:
        return None
    if user_id not in (rel.requester_id, rel.recipient_id):
        return None
    if rel.status not in ("pending", "accepted"):
        return None
    rel.status = "revoked"
    rel.updated_at = datetime.utcnow()
    await db.flush()
    return rel


async def list_user_relationships(
    db: AsyncSession, user_id: uuid.UUID,
) -> list[SocialRelationship]:
    result = await db.execute(
        select(SocialRelationship).where(
            (SocialRelationship.requester_id == user_id)
            | (SocialRelationship.recipient_id == user_id),
        ).order_by(SocialRelationship.updated_at.desc())
    )
    return list(result.scalars().all())


async def list_pending_invitations(
    db: AsyncSession, user_id: uuid.UUID,
) -> list[SocialRelationship]:
    result = await db.execute(
        select(SocialRelationship).where(
            SocialRelationship.recipient_id == user_id,
            SocialRelationship.status == "pending",
        ).order_by(SocialRelationship.created_at.desc())
    )
    return list(result.scalars().all())


# --- Blocks ---


async def block_user(
    db: AsyncSession, blocker_id: uuid.UUID, blocked_id: uuid.UUID, reason: str | None = None,
) -> SocialBlock:
    block = SocialBlock(blocker_id=blocker_id, blocked_id=blocked_id, reason=reason)
    db.add(block)
    await db.flush()
    return block


async def unblock_user(
    db: AsyncSession, blocker_id: uuid.UUID, blocked_id: uuid.UUID,
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
        select(SocialBlock).where(
            SocialBlock.blocker_id == user_id, SocialBlock.is_active,
        ).order_by(SocialBlock.created_at.desc())
    )
    return list(result.scalars().all())


# --- Grants ---


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
    db: AsyncSession, grant_id: uuid.UUID, user_id: uuid.UUID,
) -> SocialGrant | None:
    result = await db.execute(
        select(SocialGrant).join(SocialRelationship).where(
            SocialGrant.id == grant_id,
            SocialGrant.status == "proposed",
            SocialRelationship.recipient_id == user_id,
        )
    )
    grant = result.scalar_one_or_none()
    if grant is None:
        return None
    grant.status = "accepted"
    grant.updated_at = datetime.utcnow()
    await db.flush()
    return grant


async def revoke_grant(
    db: AsyncSession, grant_id: uuid.UUID, user_id: uuid.UUID,
) -> SocialGrant | None:
    result = await db.execute(
        select(SocialGrant).join(SocialRelationship).where(
            SocialGrant.id == grant_id,
            SocialGrant.status.in_(["proposed", "accepted"]),
            (
                (SocialRelationship.requester_id == user_id)
                | (SocialRelationship.recipient_id == user_id)
            ),
        )
    )
    grant = result.scalar_one_or_none()
    if grant is None:
        return None
    grant.status = "revoked"
    grant.updated_at = datetime.utcnow()
    await db.flush()
    return grant


async def list_grants_for_relationship(
    db: AsyncSession, relationship_id: uuid.UUID,
) -> list[SocialGrant]:
    result = await db.execute(
        select(SocialGrant).where(
            SocialGrant.relationship_id == relationship_id,
        ).order_by(SocialGrant.created_at.desc())
    )
    return list(result.scalars().all())


# --- Notifications ---


async def create_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    notification_type: str,
    payload: dict | None = None,
) -> SocialNotification:
    notif = SocialNotification(
        user_id=user_id,
        notification_type=notification_type,
        payload=payload or {},
    )
    db.add(notif)
    await db.flush()
    return notif


async def list_notifications(
    db: AsyncSession, user_id: uuid.UUID, limit: int = 50,
) -> list[SocialNotification]:
    result = await db.execute(
        select(SocialNotification)
        .where(SocialNotification.user_id == user_id)
        .order_by(SocialNotification.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_notification_read(
    db: AsyncSession, notification_id: uuid.UUID, user_id: uuid.UUID,
) -> bool:
    result = await db.execute(
        select(SocialNotification).where(
            SocialNotification.id == notification_id,
            SocialNotification.user_id == user_id,
        )
    )
    notif = result.scalar_one_or_none()
    if notif is None:
        return False
    notif.is_read = True
    await db.flush()
    return True
