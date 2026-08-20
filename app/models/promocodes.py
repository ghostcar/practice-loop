"""Database Model for Promotional Codes & Gift Subscriptions."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class PromoCode(Base):
    """Promotional code for tier grants & billing discounts."""

    __tablename__ = "promo_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    tier_grant: Mapped[str] = mapped_column(String(50), default="pro")  # pro, VIP
    duration_days: Mapped[int] = mapped_column(Integer, default=30)
    max_claims: Mapped[int] = mapped_column(Integer, default=100)
    claims_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<PromoCode(code={self.code}, tier={self.tier_grant}, claims={self.claims_count}/{self.max_claims})>"
