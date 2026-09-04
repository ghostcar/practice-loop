"""TrainingLogEntry — per-window training log with planned vs actual values."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.training import TrainingDay
    from app.models.user import User


class TrainingLogEntry(Base):
    """A single log entry within a training day — planned vs actual for a time window."""

    __tablename__ = "training_log_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    training_day_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("training_days.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    time_label: Mapped[str] = mapped_column(String(20), nullable=False)
    # "00:00", "09:00", "16:30–20:00", "03:00–03:30"
    entry_type: Mapped[str] = mapped_column(String(20), default="fluid_intake", nullable=False)
    # fluid_intake / micro_leak / pressure_check / general_note
    planned_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # "400 мл", "100–150 мл", "≤ 150–200 мл"
    actual_value: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # "380 мл", "12 сек", "8/10"
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # ml, sec, level, text
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Sensations, reasoning, deviations
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_extra: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True = ad-hoc entry added by user (not from original plan)
    equipment_item_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Inventory items used for this entry (migration 069)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    training_day: Mapped[TrainingDay] = relationship("TrainingDay", backref="log_entries", lazy="selectin")
    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<TrainingLogEntry(id={self.id}, time={self.time_label}, type={self.entry_type})>"
