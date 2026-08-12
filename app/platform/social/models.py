"""Platform Social — SQLAlchemy models (11_SOCIAL_SPEC.md §3–4).

All tables live under the platform, NOT under app/locktimer or app/models/entity.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
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


# ---------------------------------------------------------------------------
# S2 — Relationships, blocks, grants, notifications
# ---------------------------------------------------------------------------

RELATIONSHIP_STATUSES = frozenset({"pending", "accepted", "declined", "expired", "revoked"})
ROLE_PRESETS = frozenset({"viewer", "coach", "mentor", "curator"})
GRANT_SCOPES = frozenset({"subject", "module", "global"})
GRANT_STATUSES = frozenset({"proposed", "accepted", "revoked", "expired"})
NOTIFICATION_TYPES = frozenset({
    "invitation_received", "invitation_accepted", "invitation_declined",
    "grant_proposed", "grant_accepted", "grant_revoked",
    "block_created", "block_removed",
    "relationship_revoked",
})


class SocialRelationship(Base):
    """Invitation lifecycle — single pair uniqueness across entire product."""

    __tablename__ = "social_relationships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    recipient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Status machine: pending → accepted | declined | expired | revoked
    # accepted → revoked (either side)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)

    # Display role (UI preset only — no capability grants).
    display_role: Mapped[str] = mapped_column(String(20), default="viewer", nullable=False)

    # Cooldown for re-invite after decline/expiry.
    cooldown_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "requester_id", "recipient_id",
            name="uq_social_relationship_pair",
        ),
    )


class SocialBlock(Base):
    """Cross-product block — shuts down all interactions immediately."""

    __tablename__ = "social_blocks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    blocker_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    blocked_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "blocker_id", "blocked_id",
            name="uq_social_block_pair",
        ),
    )


class SocialGrant(Base):
    """Scoped capability grant — requires relationship acceptance + recipient accept."""

    __tablename__ = "social_grants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    relationship_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_relationships.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Scope: subject (specific social_subjects.id), module (tracker.*), global (platform)
    scope_type: Mapped[str] = mapped_column(String(20), default="subject", nullable=False)
    scope_namespace: Mapped[str | None] = mapped_column(String(80), nullable=True)
    subject_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_subjects.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    # Capabilities JSON: {caps: ["tracker.activity.view_summary", ...]}
    caps: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    # Status: proposed → accepted | revoked | expired
    status: Mapped[str] = mapped_column(String(20), default="proposed", nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False,
    )


class SocialNotification(Base):
    """In-app notification outbox for social events."""

    __tablename__ = "social_notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Type from NOTIFICATION_TYPES
    notification_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Flexible payload: {actor_alias, relationship_id, grant_id, ...}
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )


# ---------------------------------------------------------------------------
# S3 — Publications
# ---------------------------------------------------------------------------

VISIBILITY_LEVELS = frozenset({"relationship_only", "unlisted", "public"})


class SocialPublication(Base):
    """Immutable redacted snapshot — published through domain adapter.

    Social never reads private domain tables directly. The adapter builds a
    preview, owner confirms the hash, and the immutable snapshot is stored here.
    Feed queries ONLY this table — never joins Tracker/Timer private tables.
    """

    __tablename__ = "social_publications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    subject_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("social_subjects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # Visibility: relationship_only | unlisted | public
    visibility: Mapped[str] = mapped_column(String(20), default="relationship_only", nullable=False)

    # Immutable redacted snapshot (built by adapter, confirmed by owner)
    snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    snapshot_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    # Subject namespace for feed filtering (tracker.* / timer.*)
    subject_namespace: Mapped[str] = mapped_column(String(80), nullable=False, index=True)

    # Lifecycle: active → withdrawn (never edited)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
