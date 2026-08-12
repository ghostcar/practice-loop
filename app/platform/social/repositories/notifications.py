"""Social notifications (S2)."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.platform.social.models import SocialNotification


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
    db: AsyncSession,
    user_id: uuid.UUID,
    limit: int = 50,
) -> list[SocialNotification]:
    result = await db.execute(
        select(SocialNotification)
        .where(SocialNotification.user_id == user_id)
        .order_by(SocialNotification.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def mark_notification_read(
    db: AsyncSession,
    notification_id: uuid.UUID,
    user_id: uuid.UUID,
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
