"""Reminder log — deduplication of scheduled reminders (M3 Personal Suite, ADR-095).

The reminder engine runs periodically and computes due reminders (medication
doses, low stock/expiry, care products, care routines, timer slots/tasks).
To avoid re-notifying the same thing on every cycle, each delivered reminder is
recorded here. The engine checks ``(user_id, kind, dedupe_key)`` before sending.

``dedupe_key`` semantics:
- daily items re-fire each day: ``med_due:{schedule_id}:{date}``,
  ``care_routine_due:{routine_id}:{date}``;
- state items fire once per item: ``med_low:{stock_id}``,
  ``care_product_low:{product_id}``;
- occurrence items fire once per occurrence: ``timer_slot:{occurrence_id}``,
  ``timer_task:{occurrence_id}``.

Relief-only (PD-013): reminders never apply points/penalties.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class ReminderLog(Base):
    """A delivered reminder, keyed for idempotency."""

    __tablename__ = "reminder_log"
    __table_args__ = (
        UniqueConstraint("user_id", "kind", "dedupe_key", name="uq_reminder_log_user_kind_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # med_due | med_dose | med_low | med_expiring | care_product_low
    # | care_product_expiring | care_routine_due | care_course_session
    # | timer_slot_upcoming | timer_task_due
    kind: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    dedupe_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ReminderLog(user={self.user_id}, kind={self.kind}, key={self.dedupe_key})>"
