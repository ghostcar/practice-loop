"""Wear Check-Ins and Tag Seals creation (Step 65 / ADR-100).

Revision ID: 079_wear_check_ins
Revises: 078_capability_grants
Create Date: 2026-08-20 03:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "079_wear_check_ins"
down_revision: str | None = "078_capability_grants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "wear_check_in_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("managed_sub_id", sa.Uuid(), nullable=False),
        sa.Column("tag_number", sa.String(length=50), nullable=True),
        sa.Column("comfort_score", sa.Integer(), nullable=False, server_default="5"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("photo_url", sa.String(length=512), nullable=True),
        sa.Column("is_verified_closed", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["managed_sub_id"], ["managed_submissives.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_wear_check_in_logs_managed_sub_id"), "wear_check_in_logs", ["managed_sub_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_wear_check_in_logs_managed_sub_id"), table_name="wear_check_in_logs")
    op.drop_table("wear_check_in_logs")
