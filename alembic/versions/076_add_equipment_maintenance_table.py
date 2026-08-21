"""Equipment Maintenance Logs table creation (Step 58 / ADR-127).

Revision ID: 076_equipment_maintenance
Revises: 075_body_cycle_table
Create Date: 2026-08-20 02:25:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "076_equipment_maintenance"
down_revision: str | None = "075_body_cycle_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "equipment_maintenance_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("device_name", sa.String(length=255), nullable=False),
        sa.Column("maintenance_type", sa.String(length=50), nullable=False, server_default="sanitization"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("next_scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_equipment_maintenance_logs_user_id"), "equipment_maintenance_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_equipment_maintenance_logs_user_id"), table_name="equipment_maintenance_logs")
    op.drop_table("equipment_maintenance_logs")
