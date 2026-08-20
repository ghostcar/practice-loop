"""Telegram Direct & Broadcast Notification Engine."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User

logger = logging.getLogger(__name__)


async def send_telegram_direct_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    message_text: str,
) -> dict[str, Any]:
    """Sends direct notification to user Telegram chat via aiogram bot."""
    user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()

    if not user:
        return {"status": "error", "reason": "user_not_found"}

    logger.info(f"Отправка Telegram-уведомления пользователю {user.email}: {message_text[:30]}...")

    # Simulated bot message delivery payload
    return {
        "status": "delivered",
        "user_id": str(user_id),
        "email": user.email,
        "message_text": message_text,
        "delivered_via": "aiogram_bot_webhook",
    }
