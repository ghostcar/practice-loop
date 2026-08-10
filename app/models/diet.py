"""Diet plans: multiple diets for different goals, combinable by activation."""

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


class Diet(Base):
    """A named diet aimed at a specific goal (weight loss, energy, health...)."""

    __tablename__ = "diets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Direction = why this diet exists: weight_loss / muscle_gain / health /
    # energy / endurance / general / other. Drives LLM generation & evaluation.
    direction: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Last LLM evaluation of adherence to this diet (JSON) + when it ran.
    last_evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    evaluated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Combining diets = marking several as active at once; each remains editable
    # independently so the same diet can be reused in different combinations.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    user: Mapped[User] = relationship("User", lazy="selectin")
    items: Mapped[list[DietItem]] = relationship(
        "DietItem",
        back_populates="diet",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="DietItem.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Diet(id={self.id}, name={self.name[:30]}, active={self.is_active})>"


class DietItem(Base):
    """A single food/rule within a diet (what + quantity + when)."""

    __tablename__ = "diet_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    diet_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("diets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)  # g / ml / pcs / tbsp ...
    meal_time: Mapped[str | None] = mapped_column(String(30), nullable=True)  # breakfast / lunch / snack ...
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    diet: Mapped[Diet] = relationship("Diet", back_populates="items")

    def __repr__(self) -> str:
        return f"<DietItem(id={self.id}, name={self.name[:30]})>"


class DietConsumption(Base):
    """A single actually-eaten meal/food entry — the «fact» side of a diet.

    Planned items live in DietItem; this table records what the user actually
    consumed (snapshot of the food, optionally linked to a Diet/DietItem),
    so the LLM can evaluate adherence and adjust the plan.
    """

    __tablename__ = "diet_consumptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    diet_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("diets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("diet_items.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)  # snapshot of what was eaten
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)
    meal_time: Mapped[str | None] = mapped_column(String(30), nullable=True)
    consumed_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    diet: Mapped[Diet | None] = relationship("Diet", lazy="selectin")
    user: Mapped[User] = relationship("User", lazy="selectin")

    def __repr__(self) -> str:
        return f"<DietConsumption(id={self.id}, name={self.name[:30]})>"
