from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.opt_in import UserEntityOptIn
    from app.models.user import User


class Entity(Base):
    """Catalog task/activity entity with hierarchy and gamification config."""

    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="one_time")  # one_time / series / infinite
    real_name: Mapped[str] = mapped_column(String(500), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    params_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    gamification_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # gamification_config JSON structure:
    # {
    #   "points": {"base": 10, "max_per_day": 50, "profile_id": "uuid"},
    #   "penalties": {"enabled": true, "levels": [
    #     {"level": 1, "deduction": 5, "condition": "missed",
    #      "redemption": {"type": "clothespins", "duration_min": 10}},
    #     ...
    #   ]},
    #   "bonuses": [
    #     {"code": "extra_fluid", "condition": "extra_fluid_ml > 0",
    #      "reward": 20, "description": "Per extra glass"},
    #     ...
    #   ],
    #   "thresholds": {"negative": -100, "warning": 0, "good": 100}
    # }
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    parent: Mapped[Entity | None] = relationship("Entity", remote_side=[id], lazy="selectin", back_populates="children")
    children: Mapped[list[Entity]] = relationship("Entity", lazy="selectin", back_populates="parent")
    owner: Mapped[User | None] = relationship("User", foreign_keys=[owner_id], lazy="selectin")
    author: Mapped[User | None] = relationship("User", foreign_keys=[author_id], lazy="selectin")
    opt_ins: Mapped[list[UserEntityOptIn]] = relationship("UserEntityOptIn", back_populates="entity", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Entity(id={self.id}, name={self.real_name[:30]}, lvl={self.level})>"
