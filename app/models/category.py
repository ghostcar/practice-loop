"""ActivityCategory — hierarchical catalog categories (ADR-035).

Replaces the free-string ``entities.category`` with a proper table that
supports slugs, descriptions, ordering and a parent hierarchy so the
catalog can be organised into the 16 top-level categories from
``examples/update.md`` with nested subcategories.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.entity import Entity


class ActivityCategory(Base):
    """A catalog category: top-level or nested (parent_id)."""

    __tablename__ = "activity_categories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    parent: Mapped[ActivityCategory | None] = relationship(
        "ActivityCategory", remote_side=[id], lazy="selectin", back_populates="children"
    )
    children: Mapped[list[ActivityCategory]] = relationship(
        "ActivityCategory", lazy="selectin", back_populates="parent"
    )
    entities: Mapped[list[Entity]] = relationship("Entity", back_populates="category_rel", lazy="selectin")

    def __repr__(self) -> str:
        return f"<ActivityCategory(id={self.id}, slug={self.slug}, title={self.title[:30]})>"
