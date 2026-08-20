"""Database Models for Community Roles & Multi-Top Co-Governance."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class CommunityMemberRole(Base):
    """Granular role assignment for Community Co-Governance."""

    __tablename__ = "community_member_roles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    community_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("communities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # co_top / keyholder / trainer / care_curator / tournament_organizer

    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (UniqueConstraint("community_id", "user_id", "role_type", name="uq_community_user_role"),)

    def __repr__(self) -> str:
        return f"<CommunityMemberRole(community={self.community_id}, user={self.user_id}, role={self.role_type})>"
