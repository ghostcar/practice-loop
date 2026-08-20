"""Equipment & Device Maintenance Log Model (Step 58 / ADR-127)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

if TYPE_CHECKING:
    pass


class EquipmentMaintenanceLog(Base):
    """Log entries for cleaning, sanitization, inspection, and maintenance of physical devices."""

    __tablename__ = "equipment_maintenance_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    maintenance_type: Mapped[str] = mapped_column(String(50), default="sanitization")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
