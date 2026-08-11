"""LockTimer ORM models — Core tables (05_DATA_MODEL.md).

Media, verification, challenges, results, LLM proposals are deferred to C6-C7.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
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

# ---------------------------------------------------------------------------
# lock_timer_templates
# ---------------------------------------------------------------------------


class LockTimerTemplate(Base):
    __tablename__ = "lock_timer_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    config: Mapped[dict] = mapped_column(JSON, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# lock_sessions — main aggregate root
# ---------------------------------------------------------------------------


class LockSession(Base):
    __tablename__ = "lock_sessions"
    __table_args__ = (
        CheckConstraint("merge_gap_seconds >= 0 AND merge_gap_seconds <= 86400", name="ck_lock_sessions_merge_gap"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lock_timer_templates.id", ondelete="SET NULL"), nullable=True
    )

    state: Mapped[str] = mapped_column(String(24), nullable=False, default="draft")
    duration_type: Mapped[str] = mapped_column(String(24), nullable=False, default="duration_from_start")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")

    requested_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    original_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    max_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    can_extend_duration: Mapped[bool] = mapped_column(default=False, nullable=False)
    merge_gap_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=3600)
    random_seed_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    random_seed_commitment: Mapped[str] = mapped_column(String(64), nullable=False)
    privacy_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="private")

    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    safety_stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    safety_stop_reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# lock_session_snapshots
# ---------------------------------------------------------------------------


class LockSessionSnapshot(Base):
    __tablename__ = "lock_session_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lock_sessions.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    canonical_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    config_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# lock_inner_periods
# ---------------------------------------------------------------------------


class LockInnerPeriod(Base):
    __tablename__ = "lock_inner_periods"
    __table_args__ = (UniqueConstraint("session_id", "client_key", name="uq_lock_inner_periods_session_client"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lock_sessions.id", ondelete="CASCADE"), nullable=False)
    client_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    rule_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# lock_slot_rules
# ---------------------------------------------------------------------------


class LockSlotRule(Base):
    __tablename__ = "lock_slot_rules"
    __table_args__ = (
        CheckConstraint("duration_seconds >= 60 AND duration_seconds <= 86400", name="ck_lock_slot_rules_duration"),
        CheckConstraint("max_late_seconds >= 0 AND max_late_seconds <= 604800", name="ck_lock_slot_rules_late"),
        CheckConstraint("close_grace_seconds >= 0 AND close_grace_seconds <= 604800", name="ck_lock_slot_rules_grace"),
        UniqueConstraint("session_id", "client_key", name="uq_lock_slot_rules_session_client"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lock_sessions.id", ondelete="CASCADE"), nullable=False)
    client_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    inner_period_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lock_inner_periods.id", ondelete="SET NULL"), nullable=True
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    rule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    schedule: Mapped[dict] = mapped_column(JSON, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    allow_late_open: Mapped[bool] = mapped_column(default=False, nullable=False)
    max_late_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    extend_on_late_open: Mapped[bool] = mapped_column(default=False, nullable=False)
    require_close_media: Mapped[bool] = mapped_column(default=False, nullable=False)
    close_grace_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    late_close_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    llm_flags: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# lock_slot_occurrences
# ---------------------------------------------------------------------------


class LockSlotOccurrence(Base):
    __tablename__ = "lock_slot_occurrences"
    __table_args__ = (UniqueConstraint("session_id", "occurrence_key", name="uq_lock_slot_occurrences_session_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lock_sessions.id", ondelete="CASCADE"), nullable=False)
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lock_slot_rules.id", ondelete="CASCADE"), nullable=False)

    occurrence_key: Mapped[str] = mapped_column(String(64), nullable=False)
    planned_open_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planned_close_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    eligible_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    eligible_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    close_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    materialized_utc_offset_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    state: Mapped[str] = mapped_column(String(24), nullable=False, default="pending")
    actual_opened_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    actual_closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    extension_applied_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    blocked_reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)

    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# lock_task_rules
# ---------------------------------------------------------------------------


class LockTaskRule(Base):
    __tablename__ = "lock_task_rules"
    __table_args__ = (
        CheckConstraint("due_window_seconds >= 60 AND due_window_seconds <= 2592000", name="ck_lock_task_rules_window"),
        UniqueConstraint("session_id", "client_key", name="uq_lock_task_rules_session_client"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lock_sessions.id", ondelete="CASCADE"), nullable=False)
    client_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    inner_period_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lock_inner_periods.id", ondelete="SET NULL"), nullable=True
    )
    source_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("entities.id", ondelete="SET NULL"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, default="general")
    schedule_type: Mapped[str] = mapped_column(String(32), nullable=False)
    schedule: Mapped[dict] = mapped_column(JSON, nullable=False)
    due_window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    hide_until_due: Mapped[bool] = mapped_column(default=False, nullable=False)
    requires_report: Mapped[bool] = mapped_column(default=False, nullable=False)
    media_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    verification_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    penalty_policy: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    availability_policy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    llm_flags: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# lock_task_occurrences
# ---------------------------------------------------------------------------


class LockTaskOccurrence(Base):
    __tablename__ = "lock_task_occurrences"
    __table_args__ = (UniqueConstraint("session_id", "occurrence_key", name="uq_lock_task_occurrences_session_key"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lock_sessions.id", ondelete="CASCADE"), nullable=False)
    rule_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lock_task_rules.id", ondelete="CASCADE"), nullable=False)

    occurrence_key: Mapped[str] = mapped_column(String(64), nullable=False)
    appears_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    due_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, default="scheduled")
    content_visible: Mapped[bool] = mapped_column(default=False, nullable=False)
    occurrence_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False)
    revealed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    final_reason_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    selected_submission_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)  # FK later

    row_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# lock_penalty_events
# ---------------------------------------------------------------------------


class LockPenaltyEvent(Base):
    __tablename__ = "lock_penalty_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lock_sessions.id", ondelete="CASCADE"), nullable=False)
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    penalty_type: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    applied_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="applied")
    reason_code: Mapped[str] = mapped_column(String(60), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    penalty_metadata: Mapped[dict] = mapped_column("penalty_metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# lock_audit_events
# ---------------------------------------------------------------------------


class LockAuditEvent(Base):
    __tablename__ = "lock_audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lock_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)  # user, system, adapter
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    object_type: Mapped[str] = mapped_column(String(40), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    correlation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    from_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# lock_job_receipts — durable background jobs
# ---------------------------------------------------------------------------


class LockJobReceipt(Base):
    __tablename__ = "lock_job_receipts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_key: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    job_type: Mapped[str] = mapped_column(String(60), nullable=False)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    run_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_owner: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


# ---------------------------------------------------------------------------
# lock_outbox_events — transactionally-persisted domain events
# ---------------------------------------------------------------------------


class LockOutboxEvent(Base):
    __tablename__ = "lock_outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    aggregate_type: Mapped[str] = mapped_column(String(40), nullable=False)
    aggregate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    state: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    available_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
