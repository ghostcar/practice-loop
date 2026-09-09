"""Wear open-ended events ORM models (ADR-195).

Tracks open-ended wear lifecycle events, inspection check-ins, unlock reasons,
and reactive trigger outputs with second-level precision.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class WearEventDefinition(Base):
    """Catalog of wear event reasons and triggers (ADR-195)."""

    __tablename__ = "wear_event_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)
    is_valid_reason: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    default_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    trigger_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<WearEventDefinition(code={self.code!r}, title={self.title!r})>"


class WearEventLog(Base):
    """Log of open-ended wear events and state changes with second-level timestamps (ADR-195)."""

    __tablename__ = "wear_event_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lock_sessions.id", ondelete="CASCADE"), nullable=True, index=True
    )
    event_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    event_def_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("wear_event_definitions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    state_before: Mapped[str] = mapped_column(String(20), nullable=False)
    state_after: Mapped[str] = mapped_column(String(20), nullable=False)
    opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expected_relock_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    relocked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comfort_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tag_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    reactions_applied: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    definition: Mapped[WearEventDefinition | None] = relationship("WearEventDefinition", lazy="selectin")
    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return (
            f"<WearEventLog(id={self.id}, code={self.event_code!r}, "
            f"before={self.state_before}, after={self.state_after})>"
        )
