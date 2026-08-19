"""Sexual Journal (M3 Personal Suite, ROADMAP §7 4A).

Приватная запись фактической сексуальной жизни (PRODUCT_OVERVIEW §7) —
**relief-only** (PD-013): никакой игровой интеграции (XP/баллы/штрафы).
Все записи — Private Record (DATA_LIFECYCLE.md): отдельное удаление,
связи с Timer/Health — по ID без раскрытия.

Таблицы:
- ``sj_partners`` — локальные псевдонимы партнёров (никогда не раскрываются наружу);
- ``sj_entries``  — записи журнала: вид активности, дата/длительность, желание и
  возбуждение до начала, защита/контрацепция, оргазмы, интенсивность,
  удовлетворённость, реакции, эмоциональное состояние, aftercare, личные заметки,
  снимок расчётной фазы Cycle и мягкие связи с Timer/Health по ID.

Общая проекция не заменяет личные записи и не открывает журналы друг друга
(PRODUCT_OVERVIEW §7). Расчётная фаза Cycle никогда не выдаётся за факт (§9.4).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User

# желание / возбуждение / интенсивность / удовлетворённость / удовольствие / восстановление — 1..5
SCALE_1_5 = (1, 2, 3, 4, 5)
# защита и контрацепция
PROTECTION_TYPES = ("none", "condom", "birth_control", "withdrawal", "other")
# типичные реакции (подсказки в форме, свободный набор)
REACTION_CHOICES = ("pleasure", "pain", "irritation", "discomfort", "other")
# статус записи: draft — авто-создана (детали не заполнены), completed — заполнена
JOURNAL_STATUSES = ("draft", "completed")
# источник записи: manual | activity (из задачи Tracker) | timer_slot (из окна таймера)
JOURNAL_SOURCES = ("manual", "activity", "timer_slot")


class JournalPartner(Base):
    """Локальный псевдоним партнёра (Private Record, никогда не раскрывается наружу)."""

    __tablename__ = "sj_partners"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Step 24: Inclusive Partner Profile fields (migration 071)
    roles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    identity_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    hard_limits: Mapped[list | None] = mapped_column(JSON, nullable=True)
    soft_limits: Mapped[list | None] = mapped_column(JSON, nullable=True)
    safewords: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    aftercare_preferences: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<JournalPartner(id={self.id}, name={self.name!r})>"


class JournalEntry(Base):
    """Запись Sexual Journal (PRODUCT_OVERVIEW §7)."""

    __tablename__ = "sj_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sj_partners.id", ondelete="SET NULL"), nullable=True
    )
    # вид активности — ссылка на универсальный каталог (ADR-091);
    # activity_type остаётся денормализованным снимком названия для отображения
    # и обратной совместимости (старые записи без catalog_item_id).
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_catalog.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    activity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # желание и возбуждение до начала — 1..5
    desire_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    arousal_before: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # none | condom | birth_control | withdrawal | other
    protection: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    orgasms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intensity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    satisfaction: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pleasure: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # реакции: удовольствие/боль/раздражение/другое (JSON-список строк)
    reactions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # эмоциональное состояние (JSON-список строк)
    emotional_state: Mapped[list | None] = mapped_column(JSON, nullable=True)
    aftercare: Mapped[str | None] = mapped_column(Text, nullable=True)
    recovery: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # связи по ID без раскрытия (DATA_LIFECYCLE.md) — мягкие ссылки, без FK
    timer_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    health_state_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # связь с задачей Tracker (ActivityLog) и окном таймера (LockSlotOccurrence)
    activity_log_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    slot_occurrence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # draft — авто-создана (детали обязан внести при закрытии), completed — заполнена
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False, index=True)
    # manual | activity | timer_slot
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    # Шаг 17b: использованные средства/косметика (мягкие ссылки на care_products
    # по ID, DATA_LIFECYCLE.md)
    care_product_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # снимок расчётной фазы Cycle на момент записи (не выдаётся за факт, §9.4)
    cycle_phase: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cycle_day: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<JournalEntry(id={self.id}, date={self.entry_date})>"
