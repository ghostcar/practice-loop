"""Create media_exposure_drops and dead_mans_switch_rules tables.

Revision ID: 084_add_media_exposure_and_dms
Revises: 083_community_membership
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "084_add_media_exposure_and_dms"
down_revision: str | None = "083_community_membership"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_table(name: str) -> bool:
    return name in inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    # 1. media_exposure_drops (idempotent — 083 may have created it from metadata)
    if _has_table("media_exposure_drops"):
        return
    op.create_table(
        "media_exposure_drops",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("media_asset_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("media_path", sa.String(500), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("drop_token", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("pin_hash", sa.String(128), nullable=True),
        sa.Column("exposure_type", sa.String(32), default="dynamic_timer", nullable=False),
        sa.Column("is_permanent_immutable", sa.Boolean(), default=False, nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("original_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("total_adjustments_seconds", sa.Integer(), default=0, nullable=False),
        sa.Column("max_views", sa.Integer(), nullable=True),
        sa.Column("view_count", sa.Integer(), default=0, nullable=False),
        sa.Column("is_revoked", sa.Boolean(), default=False, nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("adjustments_history", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # 2. dead_mans_switch_rules (idempotent)
    if _has_table("dead_mans_switch_rules"):
        return
    op.create_table(
        "dead_mans_switch_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("interval_hours", sa.Integer(), default=24, nullable=False),
        sa.Column("grace_period_hours", sa.Integer(), default=2, nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("next_deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), default=True, nullable=False),
        sa.Column("status", sa.String(32), default="active", nullable=False),
        sa.Column("miss_count", sa.Integer(), default=0, nullable=False),
        sa.Column("penalty_xp_per_miss", sa.Integer(), default=50, nullable=False),
        sa.Column("escalation_multiplier", sa.Float(), default=1.5, nullable=False),
        sa.Column("heartbeat_sources", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("consequences_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("dead_mans_switch_rules")
    op.drop_table("media_exposure_drops")
