"""Log-only push sender — development default (PUSH_PROVIDER=logging)."""

from __future__ import annotations

import logging

from app.push.base import PushMessage

logger = logging.getLogger(__name__)


class LoggingPushSender:
    provider = "logging"

    async def send(self, device_token: str, message: PushMessage) -> bool:
        logger.info("PUSH [logging] device=%.8s… title=%r", device_token, message.title)
        return True
