"""TaskInventoryUsage — links a task to inventory items with role and quantity.
ActivityInventoryRequirement — activity-level constraints on inventory.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.activity_log import ActivityLog
    from app.models.entity import Entity
    from app.models.inventory_category import InventoryCategory
    from app.models.life import InventoryItem


class TaskInventoryUsage(Base):
    """Link between a task and one or more inventory items (update2.md §6)."""

    __tablename__ = "task_inventory_usages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_logs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inventory_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    usage_role: Mapped[str] = mapped_column(String(30), default="primary_tool", nullable=False)
    # roles: primary_tool / secondary_tool / wearable / restraint /
    #        consumable / support_equipment / measurement_tool /
    #        service_item / aftercare_item
    planned_quantity: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    actual_quantity: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    inventory_name_snapshot: Mapped[str] = mapped_column(String(300), nullable=False)
    inventory_category_snapshot: Mapped[str | None] = mapped_column(String(100), nullable=True)
    planned_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    actual_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    task: Mapped[ActivityLog] = relationship("ActivityLog", lazy="selectin")
    inventory_item: Mapped[InventoryItem | None] = relationship("InventoryItem", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TaskInventoryUsage(task={self.task_id}, item={self.inventory_item_id}, role={self.usage_role})>"


class ActivityInventoryRequirement(Base):
    """Template-level inventory constraints for an Activity (update2.md §7)."""

    __tablename__ = "activity_inventory_requirements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    inventory_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    inventory_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_items.id", ondelete="SET NULL"),
        nullable=True,
    )  # only for system-preset items
    usage_role: Mapped[str] = mapped_column(String(30), default="primary_tool", nullable=False)
    is_required: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    min_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    activity: Mapped[Entity] = relationship("Entity", lazy="selectin")
    inventory_category: Mapped[InventoryCategory | None] = relationship("InventoryCategory", lazy="selectin")
    inventory_item: Mapped[InventoryItem | None] = relationship("InventoryItem", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ActivityInventoryRequirement(activity={self.activity_id}, cat={self.inventory_category_id})>"
