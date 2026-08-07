"""Add penalty redemptions table.

Revision ID: 008
Revises: 007
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "008"
down_revision: str | None = "007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "penalty_redemptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("activity_log_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("redemption_type", sa.String(50), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("escalation_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("points_value", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["activity_log_id"], ["activity_logs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_penalty_redemptions_user_id", "penalty_redemptions", ["user_id"])
    op.create_index("ix_penalty_redemptions_status", "penalty_redemptions", ["status"])


def downgrade() -> None:
    op.drop_index("ix_penalty_redemptions_status", "penalty_redemptions")
    op.drop_index("ix_penalty_redemptions_user_id", "penalty_redemptions")
    op.drop_table("penalty_redemptions")
