"""Push dispatch — send a message to a user's active devices (best-effort).

Called from the notification flow (gamification/handler.py) next to the
Telegram hook. Never raises: a failure to deliver a push must not break the
underlying domain operation.
"""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.push_device import PushDevice
from app.push.base import PushMessage
from app.push.registry import get_push_registry

logger = logging.getLogger(__name__)


async def dispatch_push(
    db: AsyncSession,
    user_id: uuid.UUID,
    title: str,
    body: str | None = None,
    data: dict | None = None,
) -> int:
    """Deliver ``title``/``body`` to the user's active devices.

    Returns the number of devices the message was successfully sent to.
    ``PUSH_PROVIDER=none`` short-circuits to 0 (disabled).
    """
    provider = settings.push_provider
    if provider == "none":
        return 0

    sender = get_push_registry().get(provider)
    if sender is None:
        logger.warning("Push provider %r is not registered; skipping dispatch", provider)
        return 0

    result = await db.execute(
        select(PushDevice).where(
            PushDevice.user_id == user_id,
            PushDevice.is_active.is_(True),
        )
    )
    devices = result.scalars().all()
    if not devices:
        return 0

    message = PushMessage(title=title, body=body, data=data or {})
    sent = 0
    for device in devices:
        try:
            if await sender.send(device.device_token, message):  # type: ignore[attr-defined]
                sent += 1
        except Exception:
            logger.debug("Push send failed", exc_info=True)
    return sent
