"""Database Models for Payment Engine & Subscription Invoices."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class PaymentInvoice(Base):
    """Payment invoice record for subscription tier purchases."""

    __tablename__ = "payment_invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tier_code: Mapped[str] = mapped_column(String(50), nullable=False)
    gateway: Mapped[str] = mapped_column(String(50), nullable=False)  # stripe / telegram_stars / crypto / yukassa
    external_invoice_id: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False)  # pending / paid / failed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<PaymentInvoice(id={self.id}, user_id={self.user_id}, tier={self.tier_code}, status={self.status})>"
