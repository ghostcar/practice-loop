from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.activity_log import ActivityLog
    from app.models.user import User


class ActivitySession(Base):
    """A tracking session — groups activity logs under shared rules."""

    __tablename__ = "activity_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="created", nullable=False)  # created / active / ended
    llm_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llm_provider_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # JSON: штраф, лимиты, получатели уведомлений, эскалация, параллельные задачи
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    owner: Mapped[User] = relationship("User", lazy="selectin")
    logs: Mapped[list[ActivityLog]] = relationship("ActivityLog", back_populates="session", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Session(id={self.id}, status={self.status})>"
