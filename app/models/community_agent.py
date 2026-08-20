"""Database Models for Autonomous Community Top Agent & Public Tournament Engine.

Includes CommunityTopAgent persona settings, CommunityMemberDelegation for profile block control,
CommunityTournament for public competitions, and CommunityTournamentEntry for live leaderboards.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models import Base


class Community(Base):
    """Community group record."""

    __tablename__ = "communities"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CommunityPost(Base):
    """Feed announcement or post in a Community."""

    __tablename__ = "community_posts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    community_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("communities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    author_name: Mapped[str] = mapped_column(String(100), default="Domina Veritas", nullable=False)
    post_type: Mapped[str] = mapped_column(String(30), default="announcement", nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CommunityTopAgent(Base):
    """Autonomous Community Top Agent persona & governance settings."""

    __tablename__ = "community_top_agents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    community_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("communities.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    persona_name: Mapped[str] = mapped_column(String(100), default="Domina Veritas", nullable=False)
    strictness_level: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1 to 5
    auto_quests_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    lock_challenges_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    rules_manifest: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    last_audit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<CommunityTopAgent(id={self.id}, persona={self.persona_name!r}, strictness={self.strictness_level})>"


class CommunityMemberDelegation(Base):
    """Tracks member profile block delegation to the Community Top Agent."""

    __tablename__ = "community_member_delegations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    community_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("communities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    delegate_tasks: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    delegate_training: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    delegate_care: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    delegate_timer: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    compliance_score: Mapped[float] = mapped_column(Float, default=100.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CommunityTournament(Base):
    """Public tournament or competition organized by the Community Top Agent."""

    __tablename__ = "community_tournaments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    community_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("communities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    metric_type: Mapped[str] = mapped_column(
        String(50), default="compliance", nullable=False
    )  # compliance | xp | care | lock
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)  # active | completed
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    entries: Mapped[list[CommunityTournamentEntry]] = relationship(
        "CommunityTournamentEntry", back_populates="tournament", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<CommunityTournament(id={self.id}, title={self.title!r}, status={self.status})>"


class CommunityTournamentEntry(Base):
    """Member entry and live ranking in a public Community Tournament."""

    __tablename__ = "community_tournament_entries"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("community_tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    points: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    tournament: Mapped[CommunityTournament] = relationship("CommunityTournament", back_populates="entries")

    def __repr__(self) -> str:
        return (
            f"<CommunityTournamentEntry(id={self.id}, user_id={self.user_id}, points={self.points}, rank={self.rank})>"
        )
