"""Database Models for Dynamic Subscription Tier Constructor & Promotional Override Engine."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class SubscriptionTier(Base):
    """Dynamic Subscription Tier definition."""

    __tablename__ = "subscription_tiers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # Tier hierarchy rank (1..5)
    price_monthly: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    grants: Mapped[list[TierFeatureGrant]] = relationship(
        "TierFeatureGrant", back_populates="tier", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<SubscriptionTier(code={self.code!r}, rank={self.rank})>"


class TierFeatureGrant(Base):
    """Feature permission or limit assigned to a Subscription Tier."""

    __tablename__ = "tier_feature_grants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tier_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("subscription_tiers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    feature_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    limit_value: Mapped[int | None] = mapped_column(Integer, nullable=True)  # NULL = unlimited access
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tier: Mapped[SubscriptionTier] = relationship("SubscriptionTier", back_populates="grants")


class TemporaryFeaturePromotion(Base):
    """Temporary marketing promotional override opening a feature code to lower tiers."""

    __tablename__ = "temporary_feature_promotions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    feature_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    target_min_tier_code: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
