"""Aftercare module (C1, PRODUCT_OVERVIEW §5.3/§7 — «aftercare и дебриф»).

Структурированный журнал заботы после сцены/активности: физическое состояние,
эмоциональный дебриф, гидратация, отдых. **Relief-only** (PD-013): никакой
игровой интеграции. Записи — Private Record (DATA_LIFECYCLE.md): отдельное
удаление, мягкие связи с Sexual Journal и Chastity Timer по ID без раскрытия.

``journal_entry_id`` — мягкая ссылка на запись журнала (SET NULL);
``timer_session_id`` — мягкая ссылка на сессию ношения (без FK, по ID).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

# тип заботы: физическая / эмоциональная / дебриф / гидратация / отдых / другое
AFTERCARE_KINDS = ("physical", "emotional", "debrief", "hydration", "rest", "other")


class AftercareEntry(Base):
    """Запись aftercare (физическая/эмоциональная забота после сцены)."""

    __tablename__ = "aftercare_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    journal_entry_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sj_entries.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # мягкая ссылка на сессию ношения (без FK, по ID, DATA_LIFECYCLE.md)
    timer_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    # physical | emotional | debrief | hydration | rest | other
    kind: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # уровень комфорта/восстановления (1–5)
    comfort_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AftercareEntry(id={self.id}, date={self.entry_date})>"
