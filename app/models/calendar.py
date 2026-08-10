"""User availability calendar: templates, time windows, date-range overrides."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from datetime import time as time_type
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, Time, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class CalendarTemplate(Base):
    """A named weekly schedule template (e.g. 'Normal Week', 'Night Shift', 'Vacation')."""

    __tablename__ = "calendar_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship("User", lazy="selectin")
    windows: Mapped[list[AvailabilityWindow]] = relationship(
        "AvailabilityWindow", back_populates="template", lazy="selectin", cascade="all, delete-orphan"
    )


class AvailabilityWindow(Base):
    """A time window within a calendar template with an activity policy."""

    __tablename__ = "availability_windows"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calendar_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Mon..6=Sun, 7=Every day
    start_time: Mapped[time_type] = mapped_column(Time, nullable=False)
    end_time: Mapped[time_type] = mapped_column(Time, nullable=False)
    label: Mapped[str] = mapped_column(String(100), default="free", nullable=False)
    # sleep / work / free / commute / exercise / restricted / ...
    policy: Mapped[str] = mapped_column(String(20), default="allowed", nullable=False)
    # allowed / disallowed / passive_only
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    template: Mapped[CalendarTemplate] = relationship("CalendarTemplate", back_populates="windows")


class CalendarOverride(Base):
    """Maps a date range to a specific calendar template (e.g. vacation, holidays, special weeks)."""

    __tablename__ = "calendar_overrides"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("calendar_templates.id", ondelete="CASCADE"),
        nullable=False,
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    label: Mapped[str | None] = mapped_column(String(200), nullable=True)  # e.g. "Summer vacation 2024"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship("User", lazy="selectin")
    template: Mapped[CalendarTemplate] = relationship("CalendarTemplate", lazy="selectin")
