"""Platform Social — SQLAlchemy models (11_SOCIAL_SPEC.md §3–4).

All tables live under the platform, NOT under app/locktimer or app/models/entity.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# S0 — Identity & consent
# ---------------------------------------------------------------------------


class SocialProfile(Base):
    """Public identity — separate from User (email never exposed)."""

    __tablename__ = "social_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        unique=True, nullable=False, index=True,
    )

    # Public alias — case-insensitive unique, 3..80 chars.
    alias: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    alias_normalized: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)

    # Optional neutral bio.
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Privacy settings (JSON for extensibility, typed keys).
    discoverable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    show_in_feed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )


class SocialConsent(Base):
    """Versioned consent record — adult attestation + privacy terms acceptance."""

    __tablename__ = "social_consents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    consent_version: Mapped[int] = mapped_column(Integer, nullable=False)
    accepted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    ip_address_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "consent_version", name="uq_social_consent_user_version"),
    )


# ---------------------------------------------------------------------------
# S1 — Subject registry
# ---------------------------------------------------------------------------


class SocialSubject(Base):
    """Opaque registry entry for a domain subject exposed through an adapter.

    Social never reads the private domain table directly — it resolves
    subjects through the registered adapter.
    """

    __tablename__ = "social_subjects"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Namespaced type: "tracker.*" or "timer.*"
    subject_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    # Opaque reference to the domain object (adapter resolves it).
    domain_object_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Immutable projection snapshot (schema version frozen at creation).
    projection_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    projection_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Lifecycle
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    tombstoned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "subject_type", "domain_object_id",
            name="uq_social_subject_type_object",
        ),
    )
