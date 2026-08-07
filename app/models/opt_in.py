from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.entity import Entity
    from app.models.user import User


class UserEntityOptIn(Base):
    """User's opt-in preference for a catalog entity.

    Desire levels: want_very_much / want / neutral / reluctant / unacceptable
    - "unacceptable" — non-zero probability of LLM suggesting it
    - "no" (is_opted_in=False) — complete exclusion
    """

    __tablename__ = "user_entity_opt_ins"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_opted_in: Mapped[bool] = mapped_column(default=True, nullable=False)
    rating: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 1–5
    desire_level: Mapped[str] = mapped_column(String(30), default="neutral", nullable=False)
    # want_very_much / want / neutral / reluctant / unacceptable
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="opt_ins", lazy="selectin")
    entity: Mapped[Entity] = relationship("Entity", back_populates="opt_ins", lazy="selectin")

    def __repr__(self) -> str:
        return f"<OptIn(user={self.user_id}, entity={self.entity_id}, desire={self.desire_level})>"
