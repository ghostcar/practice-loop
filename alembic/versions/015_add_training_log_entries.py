"""Add training_log_entries table.

Revision ID: 015
Revises: 014_fix_migration_types
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "training_log_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column(
            "training_day_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("training_days.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("time_label", sa.String(20), nullable=False),
        sa.Column("entry_type", sa.String(20), server_default="fluid_intake", nullable=False),
        sa.Column("planned_value", sa.String(100), nullable=True),
        sa.Column("actual_value", sa.String(100), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("sort_order", sa.Integer, server_default="0", nullable=False),
        sa.Column("is_extra", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("training_log_entries")
