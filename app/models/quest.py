"""Quest and Gamification Challenge Models (Step 43 / ADR-120)."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class Quest(Base):
    """Catalog of daily/weekly gamification quests."""

    __tablename__ = "quests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    quest_type: Mapped[str] = mapped_column(String(50), default="daily")  # daily, weekly, streak
    category: Mapped[str] = mapped_column(String(50), default="general")
    target_count: Mapped[int] = mapped_column(Integer, default=1)
    reward_xp: Mapped[int] = mapped_column(Integer, default=100)
    badge_icon: Mapped[str] = mapped_column(String(50), default="trophy")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    user_quests: Mapped[list["UserQuest"]] = relationship(
        "UserQuest", back_populates="quest", cascade="all, delete-orphan"
    )


class UserQuest(Base):
    """User progress on assigned quests."""

    __tablename__ = "user_quests"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    quest_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("quests.id", ondelete="CASCADE"), nullable=False, index=True)
    current_progress: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="active")  # active, completed, claimed
    obtained_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))

    quest: Mapped["Quest"] = relationship("Quest", back_populates="user_quests")
