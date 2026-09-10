"""Omni-Pillory and disciplinary hold models (ADR-206)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class PilloryEntry(Base):
    """Universal Discipline Pillory Entry (per-trigger).

    Tracks active and historical pillory punishments across the personal contour:
    - Independent entry per trigger (late verification, challenge failure, wheel spin, etc.)
    - Multiplier escalation and freeze penalty integration with LockSessions
    - Autonomous mode (without chastity belt) with media shame
    """

    __tablename__ = "pillory_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False)
    lock_session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lock_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    trigger: Mapped[str] = mapped_column(String(50), nullable=False, default="manual")
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)

    initial_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)
    current_duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=60)

    extensions_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    softens_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    freeze_timer_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)
    requires_repentance_photo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    repentance_photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    config: Mapped[dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )

    user: Mapped[Any] = relationship("User", foreign_keys=[user_id])
    lock_session: Mapped[Any] = relationship("LockSession", foreign_keys=[lock_session_id])
