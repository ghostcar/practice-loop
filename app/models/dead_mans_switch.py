"""Database Model for Cross-Activity Dead Man's Switch Engine."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class DeadMansSwitchRule(Base):
    """Monitors continuous activity deadlines across Chastity, Tasks, Meds, and Check-ins."""

    __tablename__ = "dead_mans_switch_rules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Activity type: "wear_checkin" | "daily_task" | "medication" | "training" | "general_heartbeat"
    switch_type: Mapped[str] = mapped_column(String(50), nullable=False, default="wear_checkin", index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="Daily Heartbeat")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    interval_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=24)
    grace_period_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    next_deadline_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    # Status: "active" | "warning" | "triggered_penalty" | "paused"
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)

    penalty_xp: Mapped[int] = mapped_column(Integer, nullable=False, default=50)
    # Action on miss: "penalty_xp" | "tg_alert_only" | "notify_keyholder" | "escalate_lock"
    action_on_miss: Mapped[str] = mapped_column(String(50), nullable=False, default="penalty_xp")

    miss_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<DeadMansSwitchRule(user_id={self.user_id}, type={self.switch_type}, status={self.status})>"
