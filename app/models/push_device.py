from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class PushDevice(Base):
    """A device registered to receive push notifications (Mobile Foundation, M4).

    The device token is opaque to this service — it is handed to the configured
    push sender (FCM/APNs) which owns its meaning. A user may have multiple
    active devices; a given token is unique per (user, platform).
    """

    __tablename__ = "push_devices"
    __table_args__ = (UniqueConstraint("user_id", "platform", "device_token", name="uq_push_device_token"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    platform: Mapped[str] = mapped_column(String(30), nullable=False)  # fcm_android / apns_ios / web / other
    device_token: Mapped[str] = mapped_column(String(512), nullable=False)
    app_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<PushDevice(user={self.user_id}, platform={self.platform})>"
