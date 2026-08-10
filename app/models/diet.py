"""Diet plans: multiple diets for different goals, combinable by activation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
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
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
