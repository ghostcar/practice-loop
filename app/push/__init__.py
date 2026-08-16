"""Push notification foundation (Mobile Foundation, M4).

Provider-agnostic: device tokens are registered per user, and the configured
``PUSH_PROVIDER`` sender (none/logging/fcm/apns) receives messages. The default
is ``none`` (disabled) — real FCM/APNs senders plug into the same registry once
provider credentials exist.
"""

from app.push.dispatcher import dispatch_push  # noqa: F401
from app.push.registry import get_push_registry  # noqa: F401

__all__ = ["dispatch_push", "get_push_registry"]
