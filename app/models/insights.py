"""Personal Insights (M3 Personal Suite, ROADMAP §7 4E).

Явно запрошенный кросс-модульный LLM-анализ личных данных (PRODUCT_OVERVIEW §12):
тенденции и связи между активностями (Tracker), Chastity Timer, сексуальной
жизнью (Journal), состоянием (Health), уходом (Care), тренировками и диетами.

Правила (PRODUCT_OVERVIEW §12 / TARGET_ARCHITECTURE §3.10):
- анализ запускается **явно** (пользователь выбирает разделы и период);
- показывает, какие данные были использованы (used_data);
- **не объявляет корреляцию причиной** (промпт-ограничение);
- пользователь может исключить раздел или период из анализа.

Insights — **relief-only** (PD-013): никакой игровой интеграции
(XP/баллы/штрафы не применяются). Все записи — Private Record (DATA_LIFECYCLE.md).

Таблицы:
- ``insight_runs``    — запуск анализа: период, выбранные разделы, статус, usage;
- ``insight_findings``— находки анализа (по разделу): заголовок, текст, used_data.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.user import User

# разделы, доступные для кросс-модульного анализа
INSIGHT_SECTIONS = ("tracker", "timer", "journal", "health", "care", "training", "diet", "cycle")


class InsightRun(Base):
    """Запуск кросс-модульного анализа (PRODUCT_OVERVIEW §12)."""

    __tablename__ = "insight_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # выбранные разделы (подмножество INSIGHT_SECTIONS)
    sections: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # completed | failed
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    # общий вывод анализа (top-level)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    usage_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    usage_cost: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped[User] = relationship("User", lazy="selectin")
    findings: Mapped[list[InsightFinding]] = relationship(
        "InsightFinding", back_populates="run", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<InsightRun(id={self.id}, {self.period_start}..{self.period_end})>"


class InsightFinding(Base):
    """Находка анализа по разделу (PRODUCT_OVERVIEW §12)."""

    __tablename__ = "insight_findings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("insight_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # раздел, к которому относится находка (tracker/timer/journal/health/care/training/diet)
    section: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    # какие данные использованы (список строк) — прозрачность анализа
    used_data: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    run: Mapped[InsightRun] = relationship("InsightRun", back_populates="findings")

    def __repr__(self) -> str:
        return f"<InsightFinding(id={self.id}, section={self.section}, title={self.title!r})>"
