"""Protocol Engine ORM Models (Revision 2 / Ports & Adapters / ADR-106).

Structured sequential and anchor-relative routines (Prep, Recovery, Daily Routines)
connecting activities, medications, care products, and timer milestones without hard coupling.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class ProtocolAnchorType(enum.StrEnum):
    INDEPENDENT = "independent"  # Independent standalone schedule
    SESSION_BOUND = "session_bound"  # Relative to session start/end (T - 2h .. T + 4h)
    TIMER_BOUND = "timer_bound"  # Relative to LockTimer lock/unlock milestones


class ProtocolStepType(enum.StrEnum):
    ACTIVITY = "activity"  # Entity / practice
    MEDICATION = "medication"  # MedIntake / supplement
    CARE = "care"  # Care product / skin routine
    MEASUREMENT = "measurement"  # Body / weight / vitals
    PHOTO_CHECKIN = "photo_checkin"  # Verification photo
    TIMER_ACTION = "timer_action"  # LockTimer action


class TimingSpecType(enum.StrEnum):
    ABSOLUTE = "absolute"  # Fixed datetime
    REL_ANCHOR_BEFORE = "rel_before"  # T - offset_seconds
    REL_ANCHOR_AFTER = "rel_after"  # T + offset_seconds
    AFTER_PREV_STEP = "after_step"  # offset_seconds after step N
    DAILY = "daily"  # Specific time of day
    WINDOW = "window"  # Window between start_time and end_time


class ProtocolDefinition(Base):
    """Reusable blueprint/template of a protocol routine."""

    __tablename__ = "protocol_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="prep", nullable=False, index=True)
    # prep | recovery | routine | discipline
    anchor_type: Mapped[str] = mapped_column(
        String(30), default=ProtocolAnchorType.SESSION_BOUND.value, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    steps: Mapped[list[ProtocolStep]] = relationship(
        "ProtocolStep",
        back_populates="protocol",
        cascade="all, delete-orphan",
        order_by="ProtocolStep.step_order",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<ProtocolDefinition(id={self.id}, title={self.title})>"


class ProtocolStep(Base):
    """Individual step within a protocol definition."""

    __tablename__ = "protocol_steps"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    protocol_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("protocol_definitions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    step_type: Mapped[str] = mapped_column(String(30), default=ProtocolStepType.ACTIVITY.value, nullable=False)

    # Soft reference to external resource (Entity, CareProduct, MedicationItem)
    reference_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Typed timing specification: {"type": "rel_before", "offset_seconds": 3600}
    timing_spec: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Parameter overrides / instructions: {"duration_seconds": 900, "reps": 20, "dose": "50ml"}
    custom_params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    protocol: Mapped[ProtocolDefinition] = relationship("ProtocolDefinition", back_populates="steps")

    def __repr__(self) -> str:
        return f"<ProtocolStep(order={self.step_order}, title={self.title}, type={self.step_type})>"


class ProtocolRun(Base):
    """Active or historical execution run of a protocol with frozen rules snapshot."""

    __tablename__ = "protocol_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    protocol_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("protocol_definitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    lock_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)

    anchor_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="scheduled", nullable=False, index=True)
    # scheduled | active | completed | aborted

    # Frozen snapshot of all steps at launch time (immutable history)
    frozen_steps_snapshot: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    step_logs: Mapped[list[ProtocolStepLog]] = relationship(
        "ProtocolStepLog",
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ProtocolStepLog.planned_at",
        lazy="selectin",
    )


class ProtocolStepLog(Base):
    """Log entry of an executed step in a protocol run."""

    __tablename__ = "protocol_step_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("protocol_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    step_title: Mapped[str] = mapped_column(String(255), nullable=False)
    step_type: Mapped[str] = mapped_column(String(30), nullable=False)

    planned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)
    # pending | completed | skipped | substituted

    result_payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    actor_context: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run: Mapped[ProtocolRun] = relationship("ProtocolRun", back_populates="step_logs")
