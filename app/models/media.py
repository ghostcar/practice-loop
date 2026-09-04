"""Universal platform media assets — shared across Tracker, Timer, Social.

media_assets: staged upload → ready → archived pipeline with SHA-256,
              MIME detection, dimensions, thumbnail generation.
verification_challenges: one-time codes with HMAC-SHA256.
media_verification_results: LLM-based photo evaluation (ADR-075, Step 7).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models import Base


class MediaAsset(Base):
    """A platform-level media asset — image, video placeholder.

    Shared across Tracker (owner_type=activity_log, training_day, inventory_item,
    diet, measurement, training_log_entry), Timer (lock_session, lock_slot_occurrence,
    lock_task_occurrence), and future Social.

    Pipeline: staged (just uploaded, can be deleted) → ready (finalized, immutable for
    owner) → archived (soft-deleted for retention policy).
    """

    __tablename__ = "media_assets"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    owner_ref_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )  # bound to domain object when finalized

    state: Mapped[str] = mapped_column(String(20), nullable=False, default="staged")  # staged, ready, archived

    file_path: Mapped[str] = mapped_column(String(500), nullable=False)  # /uploads/media/<uuid>.<ext>
    thumbnail_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    original_filename: Mapped[str | None] = mapped_column(String(500), nullable=True)

    mime_type: Mapped[str] = mapped_column(String(100), nullable=False, default="application/octet-stream")
    file_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sha256_hex: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Image-specific metadata (nullable — video support deferred)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)

    caption: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "file_size_bytes >= 0 AND file_size_bytes <= 209715200", name="ck_media_assets_size"
        ),  # max 200 MB
        CheckConstraint("state IN ('staged', 'ready', 'archived')", name="ck_media_assets_state"),
    )


class VerificationChallenge(Base):
    """One-time verification code with HMAC protection.

    Attached to any domain object via owner_type + owner_id (e.g., lock_session,
    lock_task_occurrence, or future social verification). The plaintext code is
    returned only once at creation; subsequent access returns status only.

    OCR is available for seal/media flows through ADR-181, but this challenge
    endpoint remains the authoritative manual HMAC verification mechanism;
    OCR output must not replace constant-time code verification.
    """

    __tablename__ = "verification_challenges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    owner_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    owner_ref_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)

    code_hmac: Mapped[str] = mapped_column(String(64), nullable=False)  # HMAC-SHA256 of the code
    code_length: Mapped[int] = mapped_column(Integer, nullable=False, default=7)

    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # active, consumed, expired, failed

    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("code_length >= 4 AND code_length <= 16", name="ck_verification_code_length"),
        CheckConstraint("max_attempts >= 1 AND max_attempts <= 20", name="ck_verification_max_attempts"),
        CheckConstraint("state IN ('active', 'consumed', 'expired', 'failed')", name="ck_verification_state"),
    )


class MediaVerificationResult(Base):
    """LLM photo-evaluation result (ADR-075, Step 7).

    The LLM looks at a photo and gives a verdict for a verification request:
    - ``code_match`` — does the code shown in the photo match the expected code?
    - ``chastity_closed`` — is the chastity device visibly closed/locked?

    The verdict is assisting evidence. The authoritative completion is still
    the HMAC verification challenge (user types the code); auto-consumption of
    a challenge happens only when the owner explicitly enables it.
    """

    __tablename__ = "media_verification_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    media_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("media_assets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    verification_type: Mapped[str] = mapped_column(String(50), nullable=False)  # code_match | chastity_closed
    # Ожидаемое значение (код) хранится только HMAC-хешем — plaintext не пишется.
    expected_code_hmac: Mapped[str | None] = mapped_column(String(64), nullable=True)

    verdict: Mapped[str] = mapped_column(String(20), nullable=False)  # match | mismatch | unclear
    confidence: Mapped[float] = mapped_column(Integer, nullable=False, default=0)  # 0..100
    reasoning: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    llm_model: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Если verdict=match и challenge auto-consumed — ссылка на challenge.
    consumed_challenge_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "verification_type IN ('code_match', 'chastity_closed')",
            name="ck_media_verification_type",
        ),
        CheckConstraint("verdict IN ('match', 'mismatch', 'unclear')", name="ck_media_verdict"),
        CheckConstraint("confidence >= 0 AND confidence <= 100", name="ck_media_verification_confidence"),
    )
