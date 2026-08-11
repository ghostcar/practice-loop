"""TaskLocation — hierarchical location reference (system + user-custom).
TaskLocationUsage — links a task to one or more locations.
ActivityLocationRequirement — activity-level constraints on locations.
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
    from app.models.user import User


class TaskLocation(Base):
    """Reference of locations: system (read-only) and user-custom (update2.md §3)."""

    __tablename__ = "task_locations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    title_ru: Mapped[str] = mapped_column(String(200), nullable=False)
    title_en: Mapped[str | None] = mapped_column(String(200), nullable=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    location_type: Mapped[str] = mapped_column(
        String(20), default="other", nullable=False
    )  # home / room / furniture / bathroom / training / outdoor / remote / virtual / other
    privacy_level: Mapped[str] = mapped_column(
        String(10), default="private", nullable=False
    )  # private / shared / public / remote
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_custom: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )  # null = system
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    parent: Mapped[TaskLocation | None] = relationship(
        "TaskLocation", remote_side=[id], lazy="selectin", back_populates="children"
    )
    children: Mapped[list[TaskLocation]] = relationship("TaskLocation", lazy="selectin", back_populates="parent")
    owner: Mapped[User | None] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TaskLocation(id={self.id}, slug={self.slug}, title={self.title_ru[:30]})>"


class TaskLocationUsage(Base):
    """Link between a task and one or more locations (update2.md §4)."""

    __tablename__ = "task_location_usages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_locations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    location_role: Mapped[str] = mapped_column(
        String(30), default="primary_location", nullable=False
    )  # primary_location / secondary_location / start_location / end_location / training_location / remote_channel
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    location_name_snapshot: Mapped[str] = mapped_column(String(200), nullable=False)
    planned_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    task: Mapped[ActivityLog] = relationship("ActivityLog", lazy="selectin")
    location: Mapped[TaskLocation | None] = relationship("TaskLocation", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TaskLocationUsage(task={self.task_id}, location={self.location_id}, role={self.location_role})>"


class ActivityLocationRequirement(Base):
    """Template-level location constraints for an Activity (update2.md §7)."""

    __tablename__ = "activity_location_requirements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    location_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("task_locations.id", ondelete="SET NULL"),
        nullable=True,
    )
    location_role: Mapped[str] = mapped_column(String(30), default="primary_location", nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    activity: Mapped[Entity] = relationship("Entity", lazy="selectin")
    location: Mapped[TaskLocation | None] = relationship("TaskLocation", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ActivityLocationRequirement(activity={self.activity_id}, location={self.location_id})>"
