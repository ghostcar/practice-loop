"""Chastity device care tracking (PRODUCT_OVERVIEW §6.2, B2).

A device is an ``InventoryItem`` (Step 8, ADR-076) with operational
``inventory_status`` (available / in_use / ...). While a chastity session is
active the wearer logs comfort, problems and maintenance events about the
physical device. This is a *care log*, relief-only (PD-013): no points, no
penalties — it feeds the device catalogue ("комфорт, проблемы и обслуживание",
"план очистки и проверки состояния").

``device_id`` is a soft reference to an inventory item (SET NULL); ``session_id``
is a soft reference to the wear session the event occurred during (SET NULL).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

DEVICE_EVENT_TYPES = ("comfort", "problem", "maintenance", "cleaning", "inspection")
DEVICE_SEVERITIES = ("low", "medium", "high")


class ChastityDeviceEvent(Base):
    """Комфорт/проблема/обслуживание устройства во время ношения (B2)."""

    __tablename__ = "chastity_device_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("inventory_items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lock_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # comfort / problem / maintenance / cleaning / inspection
    event_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    # 1–5, only meaningful for comfort events
    comfort_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # low / medium / high, only meaningful for problem events
    severity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ChastityDeviceEvent(id={self.id}, type={self.event_type})>"
