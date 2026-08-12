"""Social profiles — CRUD (S0)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.social.models import SocialProfile


async def get_profile(db: AsyncSession, user_id: uuid.UUID) -> SocialProfile | None:
    result = await db.execute(select(SocialProfile).where(SocialProfile.user_id == user_id))
    return result.scalar_one_or_none()


async def get_profile_by_alias(db: AsyncSession, alias_normalized: str) -> SocialProfile | None:
    result = await db.execute(select(SocialProfile).where(SocialProfile.alias_normalized == alias_normalized))
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
