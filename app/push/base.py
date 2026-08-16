"""Push sender contract (M4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class PushMessage:
    title: str
    body: str | None = None
    data: dict = field(default_factory=dict)


class PushSender(Protocol):
    """A push delivery backend (FCM, APNs, logging, …)."""

    provider: str

    async def send(self, device_token: str, message: PushMessage) -> bool:
        """Deliver one message to one device token. Returns True on success."""
        ...
