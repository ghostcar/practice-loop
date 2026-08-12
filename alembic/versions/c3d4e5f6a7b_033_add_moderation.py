"""033_add_moderation

Revision ID: c3d4e5f6a7b
Revises: b2c3d4e5f6a
Create Date: 2026-08-12

Social S5 — moderation_reports + moderation_actions tables.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c3d4e5f6a7b"
down_revision: str | None = "b2c3d4e5f6a"
branch_labels: Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "moderation_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "reporter_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("target_type", sa.String(30), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reason_code", sa.String(30), nullable=False),
        sa.Column("details", sa.Text, nullable=True),
        sa.Column("state", sa.String(20), nullable=False, server_default="open"),
        sa.Column(
            "assigned_to",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_moderation_reports_reporter_id", "moderation_reports", ["reporter_id"])
    op.create_index("ix_moderation_reports_target_type", "moderation_reports", ["target_type"])
    op.create_index("ix_moderation_reports_target_id", "moderation_reports", ["target_id"])
    op.create_index("ix_moderation_reports_assigned_to", "moderation_reports", ["assigned_to"])
    op.create_index("ix_moderation_reports_state", "moderation_reports", ["state"])

    op.create_table(
        "moderation_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "report_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("moderation_reports.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "moderator_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("action_type", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("action_metadata", postgresql.JSON, nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_moderation_actions_report_id", "moderation_actions", ["report_id"])
    op.create_index("ix_moderation_actions_moderator_id", "moderation_actions", ["moderator_id"])


def downgrade() -> None:
    op.drop_index("ix_moderation_actions_moderator_id", table_name="moderation_actions")
    op.drop_index("ix_moderation_actions_report_id", table_name="moderation_actions")
    op.drop_table("moderation_actions")

    op.drop_index("ix_moderation_reports_state", table_name="moderation_reports")
    op.drop_index("ix_moderation_reports_assigned_to", table_name="moderation_reports")
    op.drop_index("ix_moderation_reports_target_id", table_name="moderation_reports")
    op.drop_index("ix_moderation_reports_target_type", table_name="moderation_reports")
    op.drop_index("ix_moderation_reports_reporter_id", table_name="moderation_reports")
    op.drop_table("moderation_reports")
