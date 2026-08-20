"""D/s Suite & Submissive Management Models (Step 62 / ADR-128)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class ManagedSubmissive(Base):
    """Profile of a submissive managed by a Top/Keyholder (registered or offline)."""

    __tablename__ = "managed_submissives"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    top_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sub_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    is_offline: Mapped[bool] = mapped_column(Boolean, default=True)
    chastity_status: Mapped[str] = mapped_column(String(50), default="unlocked")
    compliance_score: Mapped[int] = mapped_column(Integer, default=100)
    rules_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    top_user: Mapped[User] = relationship("User", foreign_keys=[top_user_id])
    sub_user: Mapped[User | None] = relationship("User", foreign_keys=[sub_user_id])
    duties: Mapped[list[AssignedDuty]] = relationship(
        "AssignedDuty", back_populates="managed_submissive", cascade="all, delete-orphan"
    )
    lock_logs: Mapped[list[ChastityLockLog]] = relationship(
        "ChastityLockLog", back_populates="managed_submissive", cascade="all, delete-orphan"
    )


class AssignedDuty(Base):
    """Task or order assigned by a Top/Keyholder to a ManagedSubmissive."""

    __tablename__ = "assigned_duties"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    managed_sub_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("managed_submissives.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_by_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")
    proof_photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    verification_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    reward_penalty_xp: Mapped[int] = mapped_column(Integer, default=50)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    managed_submissive: Mapped[ManagedSubmissive] = relationship("ManagedSubmissive", back_populates="duties")


class ChastityLockLog(Base):
    """Log of key actions, lock inspections, and duration extensions."""

    __tablename__ = "chastity_lock_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    managed_sub_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("managed_submissives.id", ondelete="CASCADE"), nullable=False, index=True
    )

    action: Mapped[str] = mapped_column(String(50), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    performed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    managed_submissive: Mapped[ManagedSubmissive] = relationship("ManagedSubmissive", back_populates="lock_logs")
