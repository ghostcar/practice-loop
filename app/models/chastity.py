"""Chastity wear check-ins (PRODUCT_OVERVIEW §6.6, C2 + B3/Q13).

Регулярный check-in во время ношения: состояние, физический комфорт, отчёт
(текст и/или фото). Фото может быть дополнительно проверено LLM
(``chastity_closed`` / ``code_match``) через существующий конвейер
``app/llm/pipeline/media_verify`` — вердикт хранится в
``media_verification_results`` (мягкая ссылка ``verification_result_id``).

Relief-only (PD-013): без игровой интеграции. ``session_id`` — мягкая ссылка
на сессию ношения (SET NULL); ``media_id`` — фото-отчёт (SET NULL).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class ChastityCheckIn(Base):
    """Регулярный check-in ношения (состояние/комфорт/отчёт)."""

    __tablename__ = "chastity_check_ins"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("lock_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # состояние носящего (1–5), опционально
    mood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # физический комфорт (1–5), опционально
    comfort_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # текстовый отчёт
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # фото-отчёт (мягкая ссылка)
    media_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # результат LLM-верификации фото (мягкая ссылка, B3)
    verification_result_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("media_verification_results.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ChastityCheckIn(id={self.id}, session={self.session_id})>"
