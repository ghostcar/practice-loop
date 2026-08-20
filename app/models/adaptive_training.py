"""Dynamic Adaptive Training Program Models (Step 54 / ADR-125)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    pass


class AdaptiveProgram(Base):
    """Catalog of active dynamic adaptive training programs for users."""

    __tablename__ = "adaptive_programs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    focus_domain: Mapped[str] = mapped_column(String(50), nullable=False, default="bladder_control")
    total_days: Mapped[int] = mapped_column(Integer, default=14)
    current_day: Mapped[int] = mapped_column(Integer, default=1)
    difficulty_level: Mapped[int] = mapped_column(Integer, default=2)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active, paused, completed
    adaptive_rules: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    steps: Mapped[list[AdaptiveProgramStep]] = relationship(
        "AdaptiveProgramStep",
        back_populates="program",
        cascade="all, delete-orphan",
        order_by="AdaptiveProgramStep.day_number",
    )

    __table_args__ = (
        CheckConstraint("total_days BETWEEN 1 AND 365", name="ck_adaptive_program_total_days"),
        CheckConstraint("current_day BETWEEN 1 AND total_days", name="ck_adaptive_program_current_day"),
        CheckConstraint("difficulty_level BETWEEN 1 AND 5", name="ck_adaptive_program_difficulty"),
        CheckConstraint("status IN ('active', 'paused', 'completed')", name="ck_adaptive_program_status"),
    )


class AdaptiveProgramStep(Base):
    """Single daily step inside an adaptive program with target & AI adjusted parameters."""

    __tablename__ = "adaptive_program_steps"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    program_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("adaptive_programs.id"), nullable=False, index=True
    )
    day_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    target_parameters: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    actual_feedback: Mapped[dict[str, Any]] = mapped_column(JSON().with_variant(JSONB, "postgresql"), default=dict)
    ai_adjustment_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending, completed, adapted, skipped

    program: Mapped[AdaptiveProgram] = relationship("AdaptiveProgram", back_populates="steps")

    __table_args__ = (
        UniqueConstraint("program_id", "day_number", name="uq_adaptive_step_program_day"),
        CheckConstraint("day_number >= 1", name="ck_adaptive_step_day_number"),
        CheckConstraint("status IN ('pending', 'completed', 'adapted', 'skipped')", name="ck_adaptive_step_status"),
    )
