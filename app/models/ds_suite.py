"""D/s Suite & Submissive Management Models (Step 62 / ADR-128)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
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

    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    telegram_link_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    telegram_link_code_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    top_user: Mapped[User] = relationship("User", foreign_keys=[top_user_id])
    sub_user: Mapped[User | None] = relationship("User", foreign_keys=[sub_user_id])
    duties: Mapped[list[AssignedDuty]] = relationship(
        "AssignedDuty", back_populates="managed_submissive", cascade="all, delete-orphan"
    )
    lock_logs: Mapped[list[ChastityLockLog]] = relationship(
        "ChastityLockLog", back_populates="managed_submissive", cascade="all, delete-orphan"
    )

    __table_args__ = (UniqueConstraint("top_user_id", "sub_user_id", name="uq_managed_sub_registered_pair"),)


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


class CapabilityGrant(Base):
    """Delegated capability grant from a registered Submissive to a Top/Keyholder (ADR-129)."""

    __tablename__ = "capability_grants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    sub_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    top_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True
    )

    invite_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), default="pending")  # pending, active, paused, revoked

    scope_chastity: Mapped[bool] = mapped_column(Boolean, default=True)
    scope_tasks: Mapped[bool] = mapped_column(Boolean, default=True)
    scope_training: Mapped[bool] = mapped_column(Boolean, default=True)
    scope_medication: Mapped[bool] = mapped_column(Boolean, default=True)
    scope_aftercare: Mapped[bool] = mapped_column(Boolean, default=True)
    scope_inventory: Mapped[bool] = mapped_column(Boolean, default=True)
    scope_health_view: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    sub_user: Mapped[User] = relationship("User", foreign_keys=[sub_user_id])
    top_user: Mapped[User | None] = relationship("User", foreign_keys=[top_user_id])


class CapabilityGrantClaimAttempt(Base):
    """Durable, secret-free audit record used to rate-limit invite claims."""

    __tablename__ = "capability_grant_claim_attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invite_code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    succeeded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), index=True)


class WearCheckInLog(Base):
    """Log of regular wear check-ins, tag seals, and physical comfort (Step 65 / ADR-100)."""

    __tablename__ = "wear_check_in_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    managed_sub_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("managed_submissives.id", ondelete="CASCADE"), nullable=False, index=True
    )

    tag_number: Mapped[str | None] = mapped_column(String(50), nullable=True)  # Seal number / tag ID
    comfort_score: Mapped[int] = mapped_column(Integer, default=5)  # 1-5 scale
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    is_verified_closed: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    managed_submissive: Mapped[ManagedSubmissive] = relationship("ManagedSubmissive")
