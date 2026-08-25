"""Notification Dispatcher & Channel Adapters (Ports & Adapters / Revision 2).

Dispatches notifications across In-App logs, Telegram Bot, Email, and Push channels.

Channels (ADR-153):
  - in_app   : writes a row into the ``notifications`` table (visible in the
               in-app bell / /notifications page). No external dependency.
  - telegram : sends via the aiogram bot to the user's linked chat. Best-effort:
               returns False when the bot is unavailable or the user has no
               linked chat (never raises).
  - email    : no SMTP infrastructure is configured (ADR-153) — logs a warning
               and returns False. Registered as a placeholder so callers that
               request it get a truthful "not delivered" instead of a lie.
  - push     : best-effort push delivery via the M4 push registry.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.capability import ActorContext

logger = logging.getLogger(__name__)


class NotificationChannelAdapter(Protocol):
    """Port for individual notification delivery channels."""

    async def send(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        event_type: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        """Deliver notification through channel. Returns True if successfully sent."""
        ...


class InAppChannel:
    """In-app notification channel storing alerts in the notifications table."""

    async def send(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        event_type: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        from app.models.notification import Notification

        try:
            db.add(
                Notification(
                    user_id=user_id,
                    type=(event_type or "general")[:50],
                    title=title[:300],
                    body=message,
                    link=(payload or {}).get("link"),
                )
            )
            await db.flush()
            logger.debug("[InAppNotification] user=%s event=%s", user_id, event_type)
            return True
        except Exception as exc:
            logger.warning("In-app notification write failed: %s", exc)
            return False


class TelegramBotChannel:
    """Telegram Bot delivery channel via aiogram (webhook or polling)."""

    async def send(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        event_type: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        try:
            from app.models.user import User
            from app.telegram.bot import send_telegram_notification

            result = await db.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
            if user is None or not user.telegram_chat_id:
                logger.debug("[TelegramNotification] user=%s has no linked chat", user_id)
                return False

            text = f"*{title}*\n{message or ''}"
            ok = await send_telegram_notification(user.telegram_chat_id, text)
            if ok:
                logger.debug("[TelegramNotification] sent to chat %s", user.telegram_chat_id)
            return ok
        except Exception as exc:
            logger.warning("[TelegramNotification] send failed: %s", exc)
            return False


class EmailChannel:
    """SMTP Email delivery channel.

    ADR-153: no SMTP infrastructure is configured in this deployment. The
    channel is registered so callers requesting it get an honest False
    (not delivered) instead of a silent fake success.
    """

    async def send(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        event_type: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        logger.warning(
            "[EmailNotification] SMTP not configured — email delivery skipped (user=%s event=%s title=%s)",
            user_id,
            event_type,
            title,
        )
        return False


class PushChannel:
    """Best-effort push delivery via the M4 push registry."""

    async def send(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        event_type: str,
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        try:
            from app.push import dispatch_push

            ok = await dispatch_push(
                db,
                user_id,
                title,
                message,
                data={"type": event_type, "link": (payload or {}).get("link")},
            )
            return bool(ok)
        except Exception as exc:
            logger.warning("[PushNotification] send failed: %s", exc)
            return False


# ─────────────────────────────────────────────────────────────────────────────
# Dispatcher & Registry
# ─────────────────────────────────────────────────────────────────────────────

NOTIFICATION_CHANNELS: dict[str, NotificationChannelAdapter] = {
    "in_app": InAppChannel(),
    "telegram": TelegramBotChannel(),
    "email": EmailChannel(),
    "push": PushChannel(),
}


def register_notification_channel(name: str, adapter: NotificationChannelAdapter) -> None:
    """Pluggably register a notification delivery channel."""
    NOTIFICATION_CHANNELS[name] = adapter


async def _resolve_user_channels(
    db: AsyncSession,
    user_id: uuid.UUID,
    requested: list[str] | None,
) -> list[str]:
    """Determine the effective channel list for a user.

    Rules (ADR-153):
      - If ``requested`` is given, use it as-is (caller decides; the DMS
        worker, reminders and gamification pass explicit lists).
      - Otherwise fall back to the user's preference: linked Telegram chat
        means ``telegram`` + ``in_app``; otherwise just ``in_app``.
    """
    if requested:
        return requested

    from app.models.user import User

    try:
        result = await db.execute(select(User.telegram_chat_id).where(User.id == user_id))
        chat_id = result.scalar_one_or_none()
    except Exception:
        chat_id = None

    channels = ["in_app"]
    if chat_id:
        channels.append("telegram")
    return channels


async def dispatch_notification(
    db: AsyncSession,
    user_id: uuid.UUID,
    event_type: str,
    title: str,
    message: str,
    channels: list[str] | None = None,
    payload: dict[str, Any] | None = None,
    actor: ActorContext | None = None,
) -> dict[str, bool]:
    """Dispatch an alert to the effective notification channels.

    Returns a map {channel_name: delivered}. Never raises: a failing channel
    is recorded as False so callers can observe delivery without the whole
    operation blowing up.
    """
    # Attach actor context to payload for audit (R8.1).
    _ctx = actor or ActorContext(actor_id=user_id, actor_type="system", source="scheduler")
    audit_payload = dict(payload or {})
    audit_payload["__audit__"] = {"actor_id": str(_ctx.actor_id), "source": _ctx.source}

    target_channels = await _resolve_user_channels(db, user_id, channels)
    results: dict[str, bool] = {}

    for ch_name in target_channels:
        channel = NOTIFICATION_CHANNELS.get(ch_name)
        if channel is None:
            logger.warning("Unknown notification channel '%s' requested", ch_name)
            results[ch_name] = False
            continue
        try:
            results[ch_name] = await channel.send(
                db=db,
                user_id=user_id,
                event_type=event_type,
                title=title,
                message=message,
                payload=audit_payload,
            )
        except Exception as exc:
            logger.warning("Failed delivery on channel '%s': %s", ch_name, exc)
            results[ch_name] = False

    return results
