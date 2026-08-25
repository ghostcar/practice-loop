"""Capability Grant V2 ORM Model (Ports & Adapters / Revision 2).

Unified actor-to-actor capability authorization across D/s, Social, Protocols, and AI agents.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class CapabilityGrantV2(Base):
    """Granular capability grant authorizing an actor to perform actions on a user's resources."""

    __tablename__ = "capability_grants_v2"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    issuer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    actor_type: Mapped[str] = mapped_column(String(30), default="human", nullable=False)  # human | agent | community
    capability_code: Mapped[str] = mapped_column(String(100), nullable=False, index=True)

    # Scopes: {"protocol_id": "...", "all_protocols": true}
    resource_scope: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Boundaries: {"max_extension_hours": 24, "allowed_window": "09:00-18:00"}
    constraints: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    valid_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    # active | revoked | expired

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<CapabilityGrantV2(issuer={self.issuer_id}, recipient={self.recipient_id}, code={self.capability_code})>"
        )
