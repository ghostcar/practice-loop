"""Personal Care (M3 Personal Suite, ROADMAP §7 4B).

Уход, косметика, гигиена, процедуры и внешность (PRODUCT_OVERVIEW §8) —
**relief-only** (PD-013): никакой игровой интеграции (XP/баллы/штрафы).
Все записи — Private Record (DATA_LIFECYCLE.md): отдельное удаление,
связи с Health/Timer — по ID без раскрытия (мягкие ссылки без FK).

Таблицы:
- ``care_routines`` — каталог процедур/рутин (лицо/тело/волосы/руки/ноги,
  бритьё и депиляция, массаж, маникюр/педикюр, стрижки/окрашивание, домашние
  и салонные), частота, заметки;
- ``care_entries``  — факты выполнения процедуры: дата, длительность,
  реакция кожи, заметки, снимок расчётной фазы Cycle и мягкая связь с
  медиа (фото динамики) через owner_type=care_entry.

Расчётная фаза Cycle никогда не выдаётся за факт (§9.4).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User

# зоны ухода
CARE_AREAS = ("face", "body", "hair", "hands", "feet", "other")
# тип процедуры: домашняя / салонная
CARE_KINDS = ("home", "salon")
# реакция кожи — 1..5 (лучше/хуже)
SCALE_1_5 = (1, 2, 3, 4, 5)


class CareRoutine(Base):
    """Каталог процедур/рутин ухода (PRODUCT_OVERVIEW §8)."""

    __tablename__ = "care_routines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # ссылка на универсальный каталог (ADR-091) — вид процедуры ухода
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_catalog.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # face | body | hair | hands | feet | other
    area: Mapped[str] = mapped_column(String(20), default="other", nullable=False)
    # home | salon
    kind: Mapped[str] = mapped_column(String(20), default="home", nullable=False)
    # частота в днях (например 7 = раз в неделю) — необязательно
    frequency_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<CareRoutine(id={self.id}, name={self.name!r})>"


class CareEntry(Base):
    """Факт выполнения процедуры ухода (PRODUCT_OVERVIEW §8).

    Мягкая связь с медиа (фото динамики) — через owner_type=care_entry в
    media registry; связь с Cycle — снимок расчётной фазы на дату процедуры.
    """

    __tablename__ = "care_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    routine_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("care_routines.id", ondelete="SET NULL"), nullable=True
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # реакция кожи — 1..5 (1 = хуже, 5 = лучше)
    skin_reaction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # снимок расчётной фазы Cycle (не выдаётся за факт, §9.4)
    cycle_phase: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cycle_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")
    routine: Mapped[CareRoutine | None] = relationship("CareRoutine", lazy="selectin")

    def __repr__(self) -> str:
        return f"<CareEntry(id={self.id}, date={self.entry_date})>"
