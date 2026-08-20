"""Database Model for User AI Agent Persona & Tone-of-Voice Settings."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class UserAgentPersona(Base):
    """User-customized AI Agent persona configuration."""

    __tablename__ = "user_agent_personas"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    persona_type: Mapped[str] = mapped_column(
        String(50), default="caring_curator"
    )  # strict_keyholder, caring_curator, endurance_trainer, anonymous_observer
    strictness_level: Mapped[int] = mapped_column(Integer, default=3)  # 1..5
    tone_of_voice: Mapped[str] = mapped_column(String(100), default="supportive_formal")
    proactive_frequency: Mapped[str] = mapped_column(String(30), default="daily")  # off, daily, high

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("user_id", name="uq_user_agent_persona"),)

    def __repr__(self) -> str:
        return (
            f"<UserAgentPersona(user={self.user_id}, persona={self.persona_type}, strictness={self.strictness_level})>"
        )
