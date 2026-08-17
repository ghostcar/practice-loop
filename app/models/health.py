"""Health + Cycle foundation (M3 Personal Suite, ROADMAP §7 4D).

Health-модуль — **relief-only** (PD-013): никакой игровой интеграции
(XP/баллы/штрафы не применяются). Все записи — Private Record (DATA_LIFECYCLE.md).

Таблицы:
- ``health_states``   — ежедневный check-in: настроение, энергия, сон, симптомы, восстановление;
- ``lab_records``     — лабораторные записи с оригинальным диапазоном конкретной лаборатории;
- ``cycle_settings``  — настройки Cycle (длина цикла/периода, контрацепция);
- ``cycle_events``    — факты Cycle: кровотечение, симптомы, состояние, тесты, наблюдения.

Расчётная фаза Cycle никогда не выдаётся за достоверный факт (PRODUCT_OVERVIEW §9.4).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User

# mood / energy / sleep_quality / recovery — 1..5
SCALE_1_5 = (1, 2, 3, 4, 5)
# event_type события Cycle
CYCLE_EVENT_TYPES = ("bleeding", "symptom", "state", "sleep", "energy", "libido", "skin", "test", "note")
# contraception
CONTRACEPTION_TYPES = ("none", "hormonal", "non_hormonal", "iud", "other")


class HealthState(Base):
    """Ежедневный check-in состояния (PRODUCT_OVERVIEW §9.2)."""

    __tablename__ = "health_states"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # 1..5
    mood: Mapped[int | None] = mapped_column(Integer, nullable=True)
    energy: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sleep_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    sleep_quality: Mapped[int | None] = mapped_column(Integer, nullable=True)
    recovery: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # список симптомов (строки), напр. ["headache", "back_pain"]
    symptoms: Mapped[list | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<HealthState(id={self.id}, date={self.event_date})>"


class LabRecord(Base):
    """Лабораторная запись с оригинальным диапазоном лаборатории (§9.3).

    Значение, единица и диапазон конкретной лаборатории остаются первичными.
    """

    __tablename__ = "lab_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)  # напр. "Hemoglobin"
    measured_at: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ref_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    ref_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    lab_name: Mapped[str | None] = mapped_column(String(200), nullable=True)  # конкретная лаборатория
    # пометка лаборатории об отклонении (если есть в исходном документе)
    flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<LabRecord(id={self.id}, name={self.name!r}, value={self.value})>"


class CycleSettings(Base):
    """Настройки Cycle (одна строка на пользователя)."""

    __tablename__ = "cycle_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    cycle_length: Mapped[int] = mapped_column(Integer, default=28, nullable=False)
    period_length: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # none | hormonal | non_hormonal | iud | other
    contraception: Mapped[str] = mapped_column(String(20), default="none", nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<CycleSettings(user_id={self.user_id}, cycle={self.cycle_length})>"


class CycleEvent(Base):
    """Факт Cycle: кровотечение, симптом, состояние, сон, энергия, тест, наблюдение."""

    __tablename__ = "cycle_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # bleeding | symptom | state | sleep | energy | libido | skin | test | note
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    # для bleeding: "light"|"medium"|"heavy"; для state: "good"|"ok"|"bad"; для test: "+"/"-"
    value: Mapped[str | None] = mapped_column(String(50), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<CycleEvent(id={self.id}, type={self.event_type}, date={self.event_date})>"
