"""Push sender registry (M4)."""

from __future__ import annotations

from app.push.logging import LoggingPushSender


class PushRegistry:
    def __init__(self) -> None:
        self._senders: dict[str, object] = {}
        self.register(LoggingPushSender())

    def register(self, sender) -> None:
        self._senders[sender.provider] = sender

    def get(self, provider: str):
        return self._senders.get(provider)


_registry = PushRegistry()


def get_push_registry() -> PushRegistry:
    return _registry
