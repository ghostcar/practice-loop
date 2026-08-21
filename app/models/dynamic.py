"""Dynamic Orchestration Engine ORM Models (Revision 2 / ADR-068 / ADR-106).

Encapsulates orchestrated operating modes:
- DynamicDefinition: reusable profile composing Persona, Agency Overlays, Protocols, and Grants.
- DynamicRun: active execution instance with immutable Frozen Snapshot of rules.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class DynamicDefinition(Base):
    """Reusable blueprint/definition for an orchestrated dynamic mode."""

    __tablename__ = "dynamic_definitions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    persona_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Agency policy constraints overlay (e.g. {"timer": {"max_extension_hours": 48}})
    agency_overlay: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Linked protocols included in this dynamic mode
    included_protocol_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Included session templates
    included_session_template_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Capabilities granted to trusted partner / agent during this dynamic
    granted_capabilities: Mapped[list] = mapped_column(JSON, default=list, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<DynamicDefinition(id={self.id}, title={self.title})>"


class DynamicRun(Base):
    """Active or historical run of a dynamic mode with frozen rules snapshot."""

    __tablename__ = "dynamic_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    dynamic_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dynamic_definitions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False, index=True)
    # active | paused | completed | aborted
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Immutable frozen rules snapshot taken at start
    frozen_dynamic_snapshot: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<DynamicRun(id={self.id}, dynamic={self.dynamic_id}, status={self.status})>"
