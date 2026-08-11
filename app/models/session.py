from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.activity_log import ActivityLog
    from app.models.user import User


class ActivitySession(Base):
    """A tracking session — a bounded set of interrelated activities (ADR-037).

    A session is a group of tasks that must be performed together within a
    limited time (e.g. an evening scenario: several acts within one hour).
    While the session is in the planning phase (status=created) its content
    can be freely edited; once accepted (``accepted_at`` set) any change to
    the task set or parameters carries a penalty.
    """

    __tablename__ = "activity_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(20), default="created", nullable=False)  # created / active / ended
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llm_provider_configs.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # JSON: штраф, лимиты, получатели уведомлений, эскалация, параллельные задачи
    planned_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    planned_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # ADR-037: once set, the session is "accepted" — later content changes are penalized
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    owner: Mapped[User] = relationship("User", lazy="selectin")
    logs: Mapped[list[ActivityLog]] = relationship("ActivityLog", back_populates="session", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Session(id={self.id}, status={self.status})>"
