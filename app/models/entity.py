from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base

if TYPE_CHECKING:
    from app.models.category import ActivityCategory
    from app.models.opt_in import UserEntityOptIn
    from app.models.user import User


class Entity(Base):
    """Catalog task/activity entity with hierarchy and gamification config.

    Evolved per ADR-035/036/038 into the "Activity" concept: base activity
    card + typed parameter schema; instances are ActivityLog rows.
    """

    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("entities.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # ссылка на универсальный каталог (ADR-091) — задача может быть основана на
    # сквозном виде активности; мягкая ссылка, SET NULL
    catalog_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_catalog.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Шаг 17b: средства/косметика, которые использовать при выполнении задачи
    # (мягкие ссылки на care_products по ID, DATA_LIFECYCLE.md)
    care_product_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="one_time")  # one_time / series / infinite
    real_name: Mapped[str] = mapped_column(String(500), nullable=False)
    # ADR-035/036: stable machine-readable slug; short display title
    slug: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    short_title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)  # legacy string (pre-ADR-035)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("activity_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # ADR-035: role tags (e.g. dominant/submissive/self) — separate from content tags
    role_tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # ADR-036: title generation template, e.g. "{count} {unit} — {activity_title}..."
    task_template: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    params_schema: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    intensity: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    # active / passive / neutral — determines if activity can bypass calendar restrictions
    # REM §5.2 safety gate: not_assessed / high are never auto-selected by the LLM;
    # elevated requires user confirmation before inclusion in a session.
    risk_level: Mapped[str] = mapped_column(
        String(20), default="not_assessed", nullable=False, server_default="not_assessed", index=True
    )
    # not_assessed / low / elevated / high
    # ADR-038: per-activity penalty switch — allows/disallows penalties even
    # where the global rules would apply (and vice versa).
    penalty_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    gamification_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # gamification_config JSON structure:
    # {
    #   "points": {"base": 10, "max_per_day": 50, "profile_id": "uuid"},
    #   "penalties": {"enabled": true, "levels": [
    #     {"level": 1, "deduction": 5, "condition": "missed",
    #      "redemption": {"type": "clothespins", "duration_min": 10}},
    #     ...
    #   ]},
    #   "bonuses": [
    #     {"code": "extra_fluid", "condition": "extra_fluid_ml > 0",
    #      "reward": 20, "description": "Per extra glass"},
    #     ...
    #   ],
    #   "thresholds": {"negative": -100, "warning": 0, "good": 100}
    # }
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=True
    )

    # Relationships
    parent: Mapped[Entity | None] = relationship("Entity", remote_side=[id], lazy="selectin", back_populates="children")
    children: Mapped[list[Entity]] = relationship("Entity", lazy="selectin", back_populates="parent")
    owner: Mapped[User | None] = relationship("User", foreign_keys=[owner_id], lazy="selectin")
    author: Mapped[User | None] = relationship("User", foreign_keys=[author_id], lazy="selectin")
    opt_ins: Mapped[list[UserEntityOptIn]] = relationship("UserEntityOptIn", back_populates="entity", lazy="selectin")
    category_rel: Mapped[ActivityCategory | None] = relationship(
        "ActivityCategory", back_populates="entities", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Entity(id={self.id}, name={self.real_name[:30]}, lvl={self.level})>"
