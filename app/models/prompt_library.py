"""Prompt Library Models — Dual System & User Prompt Catalog (Step 49 / ADR-124)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class PromptLibraryItem(Base):
    """Catalog of central System and User prompt templates."""

    __tablename__ = "prompt_library"
    __table_args__ = (UniqueConstraint("key", name="uq_prompt_library_key"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    library_type: Mapped[str] = mapped_column(String(20), nullable=False)  # system or user
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(500), nullable=False)
    template_content: Mapped[str] = mapped_column(Text, nullable=False)
    is_customized: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
