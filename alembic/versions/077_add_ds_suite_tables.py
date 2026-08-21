"""D/s Suite tables creation (Step 62 / ADR-128).

Revision ID: 077_ds_suite_tables
Revises: 076_equipment_maintenance
Create Date: 2026-08-20 02:34:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "077_ds_suite_tables"
down_revision: str | None = "076_equipment_maintenance"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Managed Submissives Table
    op.create_table(
        "managed_submissives",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("top_user_id", sa.Uuid(), nullable=False),
        sa.Column("sub_user_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("is_offline", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("chastity_status", sa.String(length=50), nullable=False, server_default="unlocked"),
        sa.Column("compliance_score", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("rules_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["top_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["sub_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_managed_submissives_top_user_id"), "managed_submissives", ["top_user_id"], unique=False)
    op.create_index(op.f("ix_managed_submissives_sub_user_id"), "managed_submissives", ["sub_user_id"], unique=False)

    # 2. Assigned Duties Table
    op.create_table(
        "assigned_duties",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("managed_sub_id", sa.Uuid(), nullable=False),
        sa.Column("assigned_by_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("proof_photo_url", sa.String(length=512), nullable=True),
        sa.Column("verification_notes", sa.Text(), nullable=True),
        sa.Column("reward_penalty_xp", sa.Integer(), nullable=False, server_default="50"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["managed_sub_id"], ["managed_submissives.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_assigned_duties_managed_sub_id"), "assigned_duties", ["managed_sub_id"], unique=False)

    # 3. Chastity Lock Logs Table
    op.create_table(
        "chastity_lock_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("managed_sub_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("performed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["managed_sub_id"], ["managed_submissives.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chastity_lock_logs_managed_sub_id"), "chastity_lock_logs", ["managed_sub_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chastity_lock_logs_managed_sub_id"), table_name="chastity_lock_logs")
    op.drop_table("chastity_lock_logs")

    op.drop_index(op.f("ix_assigned_duties_managed_sub_id"), table_name="assigned_duties")
    op.drop_table("assigned_duties")

    op.drop_index(op.f("ix_managed_submissives_sub_user_id"), table_name="managed_submissives")
    op.drop_index(op.f("ix_managed_submissives_top_user_id"), table_name="managed_submissives")
    op.drop_table("managed_submissives")
