"""Shared helper for points economy endpoints."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.progress import UserProgress


async def _get_progress(db: AsyncSession, user_id: uuid.UUID) -> UserProgress:
    result = await db.execute(select(UserProgress).where(UserProgress.user_id == user_id))
    p = result.scalar_one_or_none()
    if p is None:
        p = UserProgress(user_id=user_id)
        db.add(p)
        await db.flush()
    return p
