"""Social consent — record/check (S0)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.social.models import SocialConsent


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
