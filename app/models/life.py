"""Schedule, measurements, and inventory models."""

from __future__ import annotations

import uuid
from datetime import date, datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.user import User


class ScheduleRule(Base):
    """A recurring or one-time schedule slot for a task."""

    __tablename__ = "schedule_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    # 0=Mon, 1=Tue, ..., 6=Sun, 7=Every day
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    task_type: Mapped[str] = mapped_column(String(30), default="mandatory", nullable=False)
    # mandatory / optional_mandatory / optional / penalty_reducing
    recurring: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship("User", lazy="selectin")
    entity: Mapped[Entity | None] = relationship("Entity", lazy="selectin")


class BodyMeasurement(Base):
    """Daily body measurements: weight, circumferences."""

    __tablename__ = "body_measurements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    measured_date: Mapped[date] = mapped_column(Date, nullable=False)
    time_of_day: Mapped[str] = mapped_column(String(10), default="morning", nullable=False)
    weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    chest: Mapped[float | None] = mapped_column(Float, nullable=True)
    under_chest: Mapped[float | None] = mapped_column(Float, nullable=True)
    waist: Mapped[float | None] = mapped_column(Float, nullable=True)
    hips: Mapped[float | None] = mapped_column(Float, nullable=True)
    thigh: Mapped[float | None] = mapped_column(Float, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship("User", lazy="selectin")


class InventoryItem(Base):
    """Equipment, clothing, cosmetics inventory with shopping list support.

    ``status`` = shopping-list status (need / ordered / bought / built).
    ``inventory_status`` = operational availability (available / in_use /
    cleaning / charging / maintenance / unavailable / archived).
    """

    __tablename__ = "inventory_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # legacy free string — kept; prefer inventory_category_id for new items
    inventory_category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("inventory_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    quantity_needed: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    is_shopping_list: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="need", nullable=False)
    # need / ordered / bought / built (shopping-list)
    inventory_status: Mapped[str] = mapped_column(
        String(20), default="available", nullable=False
    )  # available / in_use / cleaning / charging / maintenance / unavailable / archived
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)  # /uploads/inventory/<uuid>.jpg
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")
