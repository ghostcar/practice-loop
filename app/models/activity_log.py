from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base
from app.models.task_status import PLANNED

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.session import ActivitySession
    from app.models.training import TrainingDay
    from app.models.user import User


class ActivityLog(Base):
    """A single activity instance — the ActivityTask (ADR-036).

    Evolved from a pure LLM log into a full task: title_override,
    scheduled_at, planned/actual parameters and comments, plus the strict
    11-state status machine (ADR-040).
    """

    __tablename__ = "activity_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Strict status enum (ADR-040): draft / planned / in_progress / completed /
    # partially_completed / skipped / cancelled / stopped / substituted /
    # not_applicable / review_needed. Legacy pending→planned, interrupted→stopped.
    status: Mapped[str] = mapped_column(String(30), default=PLANNED, nullable=False)
    # ADR-036: free override of the generated title (nullable = auto-generated)
    title_override: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # ADR-036: scheduled date/time — for free daily tasks and session tasks
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    user_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_llm_response: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )  # REM §7.5 — TTL on raw payload (None = no expiry / retained)
    cleaned_response: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # cleaned_response: {"entity_id": ..., "params": ..., "reasoning": ...}
    selected_entity_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    selected_params: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # ADR-041: actual parameters — what was really done (separate from planned)
    actual_parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    penalty_applied: Mapped[bool] = mapped_column(default=False, nullable=False)
    penalty_details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Plan vs Actual (legacy string fields, kept for compatibility)
    planned_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    actual_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # ADR-036: comments — planned (before execution) and completion (after)
    planned_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    completion_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Points awarded for this task (for economy system)
    points_awarded: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Training
    training_day_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_days.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    subtasks: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)
    # [{"id": 1, "desc": "Step 1", "is_done": false}, ...]
    # Usage tracking
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    session: Mapped[ActivitySession | None] = relationship("ActivitySession", back_populates="logs", lazy="selectin")
    training_day: Mapped[TrainingDay | None] = relationship(
        "TrainingDay", foreign_keys=[training_day_id], lazy="selectin"
    )
    user: Mapped[User] = relationship("User", lazy="selectin")
    entity: Mapped[Entity | None] = relationship("Entity", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ActivityLog(id={self.id}, status={self.status})>"
