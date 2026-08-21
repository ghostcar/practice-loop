"""Create protocol engine tables.

Revision ID: 087_add_protocol_engine
Revises: 086_add_capability_grants_v2
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "087_add_protocol_engine"
down_revision: str | None = "086_add_capability_grants_v2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. protocol_definitions
    op.create_table(
        "protocol_definitions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1000), nullable=True),
        sa.Column("category", sa.String(50), nullable=False, server_default="prep", index=True),
        sa.Column("anchor_type", sa.String(30), nullable=False, server_default="session_bound"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    # 2. protocol_steps
    op.create_table(
        "protocol_steps",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "protocol_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("protocol_definitions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("step_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("step_type", sa.String(30), nullable=False, server_default="activity"),
        sa.Column("reference_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "timing_spec",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "custom_params",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 3. protocol_runs
    op.create_table(
        "protocol_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "protocol_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("protocol_definitions.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("lock_session_id", postgresql.UUID(as_uuid=True), nullable=True, index=True),
        sa.Column("anchor_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="scheduled", index=True),
        sa.Column(
            "frozen_steps_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # 4. protocol_step_logs
    op.create_table(
        "protocol_step_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("protocol_runs.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("step_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("step_title", sa.String(255), nullable=False),
        sa.Column("step_type", sa.String(30), nullable=False),
        sa.Column("planned_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column(
            "result_payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "actor_context",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("protocol_step_logs")
    op.drop_table("protocol_runs")
    op.drop_table("protocol_steps")
    op.drop_table("protocol_definitions")
