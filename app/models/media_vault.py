"""Database Model for Media Vault Security v2 (One-Time Viewing Tokens)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class OneTimeMediaToken(Base):
    """Self-destructing burn-on-read media token for secure proof viewing."""

    __tablename__ = "one_time_media_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    media_path: Mapped[str] = mapped_column(String(512), nullable=False)
    is_burned: Mapped[bool] = mapped_column(Boolean, default=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<OneTimeMediaToken(token={self.token}, is_burned={self.is_burned})>"
