"""Agency Policy ORM Model (Revision 2 / ADR-068 / ADR-106).

Governs user-defined autonomy levels for AI, Persona, and Human actors per domain & operation.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class AgencyLevel(enum.StrEnum):
    MANUAL = "manual"  # Only user manually
    ANALYZE_ONLY = "analyze_only"  # Read & analyze data without actions
    ASSISTED = "assisted"  # Suggestions & guidance
    PROPOSE_AND_CONFIRM = "propose_and_confirm"  # Draft proposal requiring explicit user apply
    AUTOMATED_WITHIN_POLICY = "automated"  # Autonomous actions strictly within user constraints
    DELEGATED_AI = "delegated_ai"  # Virtual persona dynamic actions
    DELEGATED_HUMAN = "delegated_human"  # Delegated to trusted partner / keyholder


class AgencyPolicy(Base):
    """Granular user autonomy policy per domain and operation."""

    __tablename__ = "agency_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    domain: Mapped[str] = mapped_column(String(50), nullable=False)  # sessions, timer, diet, training, care, protocols
    default_level: Mapped[str] = mapped_column(
        String(30), default=AgencyLevel.MANUAL.value, nullable=False
    )
    # Typed operation overrides: {"analyze": "automated", "propose": "assisted", "apply": "propose_and_confirm"}
    operation_overrides: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # User-defined hard boundaries: {"max_duration_min": 60, "max_extension_hours": 24, "allowed_categories": [...]}
    constraints: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("user_id", "domain", name="uq_user_agency_domain"),)

    def __repr__(self) -> str:
        return f"<AgencyPolicy(user={self.user_id}, domain={self.domain}, default={self.default_level})>"
