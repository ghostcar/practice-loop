from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.opt_in import UserEntityOptIn


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # ADR-110: abstract/anonymous display name shown in the shell instead of the
    # email. Optional — falls back to a neutral placeholder (e.g. "User").
    display_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    subscription_tier: Mapped[str] = mapped_column(String(50), default="free", nullable=False)
    is_monetization_exempt: Mapped[bool] = mapped_column(default=False, nullable=False)
    role: Mapped[str] = mapped_column(String(20), default="user", nullable=False)  # user / moderator / admin
    locale: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    theme: Mapped[str] = mapped_column(String(10), default="dark", nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    # Step 9e (DESIGN_V2 §16): customization + discretion prefs (see app/prefs.py).
    # Generic JSON keeps SQLite-based tests green; the migration uses PG JSONB.
    prefs: Mapped[dict] = mapped_column(JSON, default=dict, server_default=text("'{}'"), nullable=False)
    # Step 23: Health adaptation user control preferences (migration 070)
    health_adaptation_mode: Mapped[str] = mapped_column(String(30), default="auto_reduce", nullable=False)
    health_adaptation_sensitivity: Mapped[str] = mapped_column(String(30), default="moderate", nullable=False)

    timezone_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Telegram linking
    telegram_chat_id: Mapped[int | None] = mapped_column(nullable=True, unique=True)
    telegram_link_code: Mapped[str | None] = mapped_column(String(12), nullable=True)
    telegram_link_code_expires: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    opt_ins: Mapped[list[UserEntityOptIn]] = relationship("UserEntityOptIn", back_populates="user", lazy="selectin")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email})>"
