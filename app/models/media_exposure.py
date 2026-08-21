"""Database Model for Media Showcase & Dynamic/Immutable Exposure Drops."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class MediaExposureDrop(Base):
    """Universal Showcase & Exposure drop with dynamic timer, PIN, or permanent immutable lock."""

    __tablename__ = "media_exposure_drops"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="SET NULL"), nullable=True, index=True
    )
    media_path: Mapped[str] = mapped_column(String(512), nullable=False)

    token: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Exposure type: "one_time" | "dynamic_timer" | "permanent_immutable"
    exposure_type: Mapped[str] = mapped_column(String(50), nullable=False, default="dynamic_timer", index=True)

    initial_duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Optional 4-6 digit PIN code protection
    pin_code_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Burning & Immobility flags
    is_burned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_permanent_immutable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    # Viewer stats
    view_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    views_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Dynamic timer adjustments log: [{"delta_minutes": 15, "adjusted_at": "...", "by": "user"}]
    extension_history: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<MediaExposureDrop(token={self.token}, type={self.exposure_type}, perm={self.is_permanent_immutable})>"
