from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class Achievement(Base):
    """Achievement definition — code, name, conditions, SVG icon."""

    __tablename__ = "achievements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    condition_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # streak / count / diversity / intensity / joint / anniversary
    condition_value: Mapped[int] = mapped_column(nullable=True)
    # threshold value (e.g. 7 for 7-day streak, 100 for 100 tasks)
    condition_extra: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # extra params (e.g. {"category": "..."} for diversity)
    icon_svg: Mapped[str | None] = mapped_column(Text, nullable=True)
    color: Mapped[str] = mapped_column(String(20), default="indigo", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<Achievement(code={self.code})>"


class UserAchievement(Base):
    """Awarded achievement for a specific user."""

    __tablename__ = "user_achievements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    achievement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("achievements.id", ondelete="CASCADE"),
        nullable=False,
    )
    obtained_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    # e.g. "Completed task: Massage 10 min"
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user: Mapped[User] = relationship("User", lazy="selectin")
    achievement: Mapped[Achievement] = relationship("Achievement", lazy="selectin")

    def __repr__(self) -> str:
        return f"<UserAchievement(user={self.user_id}, ach={self.achievement_id})>"
