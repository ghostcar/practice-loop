"""BodyPart — hierarchical body part reference (update2.md §1).
TaskBodyTarget — links a task to body zones with role, side, intensity.
ActivityBodyPartRequirement — activity-level constraints on body parts.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.activity_log import ActivityLog
    from app.models.entity import Entity


class BodyPart(Base):
    """Hierarchical reference of body zones (system, read-only for users)."""

    __tablename__ = "body_parts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    title_ru: Mapped[str] = mapped_column(String(200), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("body_parts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    body_system: Mapped[str] = mapped_column(
        String(20), default="general", nullable=False
    )  # general / head_neck / torso / upper_limb / lower_limb / intimate
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    parent: Mapped[BodyPart | None] = relationship(
        "BodyPart", remote_side=[id], lazy="selectin", back_populates="children"
    )
    children: Mapped[list[BodyPart]] = relationship("BodyPart", lazy="selectin", back_populates="parent")

    def __repr__(self) -> str:
        return f"<BodyPart(id={self.id}, slug={self.slug}, title={self.title_ru[:30]})>"


class TaskBodyTarget(Base):
    """Link between a task and one or more body zones (update2.md §2)."""

    __tablename__ = "task_body_targets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    body_part_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("body_parts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    target_role: Mapped[str] = mapped_column(
        String(30), default="primary_target", nullable=False
    )  # primary_target / secondary_target / support_area / training_target / recovery_target
    side: Mapped[str] = mapped_column(String(10), default="both", nullable=False)  # none / left / right / both
    planned_intensity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_intensity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    planned_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    body_part_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    planned_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    task: Mapped[ActivityLog] = relationship("ActivityLog", lazy="selectin")
    body_part: Mapped[BodyPart | None] = relationship("BodyPart", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TaskBodyTarget(task={self.task_id}, part={self.body_part_id}, role={self.target_role})>"


class ActivityBodyPartRequirement(Base):
    """Template-level body part constraints for an Activity (update2.md §7)."""

    __tablename__ = "activity_body_part_requirements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    body_part_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("body_parts.id", ondelete="SET NULL"),
        nullable=True,
    )
    target_role: Mapped[str] = mapped_column(String(30), default="primary_target", nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    allow_side_selection: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    activity: Mapped[Entity] = relationship("Entity", lazy="selectin")
    body_part: Mapped[BodyPart | None] = relationship("BodyPart", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ActivityBodyPartRequirement(activity={self.activity_id}, part={self.body_part_id})>"
