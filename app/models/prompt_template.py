"""PromptTemplate — пользовательские приватные промпт-шаблоны (ADR-070, Step 6).

Два типа:
- ``text`` — LLM генерирует текстовый ответ по шаблону с переменными;
- ``task`` — как generate_task, но с кастомным системным промптом: LLM выбирает
  задачу из допустимого набора, параметры валидируются по entity.params_schema.

Переменные в ``system_prompt`` объявляются через ``{{var}}``; их типы/диапазоны
описываются в ``params_schema`` (формат ADR-041 — переиспользует
``app.params.validate_params``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User


class PromptTemplate(Base):
    """A user-owned prompt template for parametric LLM generation."""

    __tablename__ = "prompt_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    template_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)  # text | task
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # Параметры/переменные шаблона — формат ADR-041 (list of definitions).
    params_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Откуда создан (для шаблонов, порождённых из библиотеки).
    source_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # Relationships
    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<PromptTemplate(id={self.id}, name={self.name!r}, type={self.template_type})>"
