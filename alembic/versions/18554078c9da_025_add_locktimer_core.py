"""025_add_locktimer_core — Core tables for LockTimer (ADR-047, 05_DATA_MODEL.md).

Revision ID: 18554078c9da
Revises: 75e1419980bd  (024_add_user_timezone)
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "18554078c9da"
down_revision: str | None = "75e1419980bd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. lock_timer_templates
    op.create_table(
        "lock_timer_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("config", sa.JSON, nullable=False),
        sa.Column("config_sha256", sa.String(64), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lock_timer_templates_owner_id", "lock_timer_templates", ["owner_id"])

    # 2. lock_sessions
    op.create_table(
        "lock_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_timer_templates.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("state", sa.String(24), nullable=False, server_default="draft"),
        sa.Column("duration_type", sa.String(24), nullable=False, server_default="duration_from_start"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.Column("requested_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("max_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("can_extend_duration", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("merge_gap_seconds", sa.Integer, nullable=False, server_default="3600"),
        sa.Column("random_seed_encrypted", sa.Text, nullable=False),
        sa.Column("random_seed_commitment", sa.String(64), nullable=False),
        sa.Column("privacy_mode", sa.String(20), nullable=False, server_default="private"),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("safety_stopped_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("safety_stop_reason_code", sa.String(40), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lock_sessions_owner_id", "lock_sessions", ["owner_id"])
    op.create_check_constraint(
        "ck_lock_sessions_merge_gap", "lock_sessions", "merge_gap_seconds >= 0 AND merge_gap_seconds <= 86400"
    )
    # Partial unique: one active session per owner
    op.execute("CREATE UNIQUE INDEX uq_lock_sessions_active_owner ON lock_sessions (owner_id) WHERE state = 'active'")

    # 3. lock_session_snapshots
    op.create_table(
        "lock_session_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_sessions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("canonical_config", sa.JSON, nullable=False),
        sa.Column("config_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 4. lock_inner_periods
    op.create_table(
        "lock_inner_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("rule_type", sa.String(32), nullable=False),
        sa.Column("rule_data", sa.JSON, nullable=False),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_lock_inner_periods_session_client", "lock_inner_periods", ["session_id", "client_key"]
    )

    # 5. lock_slot_rules
    op.create_table(
        "lock_slot_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "inner_period_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_inner_periods.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("rule_type", sa.String(32), nullable=False),
        sa.Column("schedule", sa.JSON, nullable=False),
        sa.Column("duration_seconds", sa.Integer, nullable=False),
        sa.Column("allow_late_open", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("max_late_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("extend_on_late_open", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("require_close_media", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("close_grace_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("late_close_policy", sa.JSON, nullable=True),
        sa.Column("llm_flags", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_check_constraint(
        "ck_lock_slot_rules_duration", "lock_slot_rules", "duration_seconds >= 60 AND duration_seconds <= 86400"
    )
    op.create_check_constraint(
        "ck_lock_slot_rules_late", "lock_slot_rules", "max_late_seconds >= 0 AND max_late_seconds <= 604800"
    )
    op.create_check_constraint(
        "ck_lock_slot_rules_grace", "lock_slot_rules", "close_grace_seconds >= 0 AND close_grace_seconds <= 604800"
    )
    op.create_unique_constraint("uq_lock_slot_rules_session_client", "lock_slot_rules", ["session_id", "client_key"])

    # 6. lock_slot_occurrences
    op.create_table(
        "lock_slot_occurrences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_slot_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("occurrence_key", sa.String(64), nullable=False),
        sa.Column("planned_open_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("planned_close_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("eligible_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("eligible_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("close_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("materialized_utc_offset_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("state", sa.String(24), nullable=False, server_default="pending"),
        sa.Column("actual_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("extension_applied_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("blocked_reason_code", sa.String(40), nullable=True),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_lock_slot_occurrences_session_key", "lock_slot_occurrences", ["session_id", "occurrence_key"]
    )
    op.create_index("ix_lock_slot_occurrences_planned", "lock_slot_occurrences", ["session_id", "planned_open_at"])
    op.create_index("ix_lock_slot_occurrences_rule", "lock_slot_occurrences", ["rule_id"])

    # 7. lock_task_rules
    op.create_table(
        "lock_task_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "inner_period_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_inner_periods.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "source_entity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("category", sa.String(100), nullable=False, server_default="general"),
        sa.Column("schedule_type", sa.String(32), nullable=False),
        sa.Column("schedule", sa.JSON, nullable=False),
        sa.Column("due_window_seconds", sa.Integer, nullable=False),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("hide_until_due", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("requires_report", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("media_policy", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("verification_policy", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("penalty_policy", sa.JSON, nullable=True),
        sa.Column("availability_policy", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("llm_flags", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("schema_version", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_check_constraint(
        "ck_lock_task_rules_window", "lock_task_rules", "due_window_seconds >= 60 AND due_window_seconds <= 2592000"
    )
    op.create_unique_constraint("uq_lock_task_rules_session_client", "lock_task_rules", ["session_id", "client_key"])

    # 8. lock_task_occurrences
    op.create_table(
        "lock_task_occurrences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "rule_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_task_rules.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("occurrence_key", sa.String(64), nullable=False),
        sa.Column("appears_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(24), nullable=False, server_default="scheduled"),
        sa.Column("content_visible", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("occurrence_snapshot", sa.JSON, nullable=False),
        sa.Column("revealed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("final_reason_code", sa.String(40), nullable=True),
        sa.Column("selected_submission_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("row_version", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint(
        "uq_lock_task_occurrences_session_key", "lock_task_occurrences", ["session_id", "occurrence_key"]
    )
    op.create_index("ix_lock_task_occurrences_appears", "lock_task_occurrences", ["session_id", "appears_at"])
    op.create_index("ix_lock_task_occurrences_rule", "lock_task_occurrences", ["rule_id"])

    # 9. lock_penalty_events
    op.create_table(
        "lock_penalty_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_kind", sa.String(32), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("penalty_type", sa.String(32), nullable=False),
        sa.Column("requested_value", sa.Integer, nullable=True),
        sa.Column("applied_value", sa.Integer, nullable=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="applied"),
        sa.Column("reason_code", sa.String(60), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("penalty_metadata", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_lock_penalty_events_key", "lock_penalty_events", ["idempotency_key"])

    # 10. lock_audit_events
    op.create_table(
        "lock_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("object_type", sa.String(40), nullable=False),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("correlation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=True),
        sa.Column("from_version", sa.Integer, nullable=True),
        sa.Column("to_version", sa.Integer, nullable=True),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_lock_audit_events_session", "lock_audit_events", ["session_id", "created_at"])
    op.create_index("ix_lock_audit_events_actor", "lock_audit_events", ["actor_user_id"])

    # 11. lock_job_receipts
    op.create_table(
        "lock_job_receipts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("job_key", sa.String(200), nullable=False),
        sa.Column("job_type", sa.String(60), nullable=False),
        sa.Column("state", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("run_after", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.String(100), nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_unique_constraint("uq_lock_job_receipts_key", "lock_job_receipts", ["job_key"])

    # 12. lock_outbox_events
    op.create_table(
        "lock_outbox_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("aggregate_type", sa.String(40), nullable=False),
        sa.Column("aggregate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("state", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    # Drop in reverse order to respect FK dependencies.
    op.drop_table("lock_outbox_events")
    op.drop_table("lock_job_receipts")
    op.drop_table("lock_audit_events")
    op.drop_table("lock_penalty_events")
    op.drop_table("lock_task_occurrences")
    op.drop_table("lock_task_rules")
    op.drop_table("lock_slot_occurrences")
    op.drop_table("lock_slot_rules")
    op.drop_table("lock_inner_periods")
    op.drop_table("lock_session_snapshots")
    op.drop_table("lock_sessions")
    op.drop_table("lock_timer_templates")
