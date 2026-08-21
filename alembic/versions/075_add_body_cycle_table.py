"""Body Cycle Logs table creation (Step 56 / ADR-126).

Revision ID: 075_body_cycle_table
Revises: 074_adaptive_training_tables
Create Date: 2026-08-20 02:22:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "075_body_cycle_table"
down_revision: str | None = "074_adaptive_training_tables"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "body_cycle_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("cycle_phase", sa.String(length=30), nullable=False, server_default="neutral"),
        sa.Column("energy_level", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("soreness_level", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("logged_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_body_cycle_logs_user_id"), "body_cycle_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_body_cycle_logs_user_id"), table_name="body_cycle_logs")
    op.drop_table("body_cycle_logs")
