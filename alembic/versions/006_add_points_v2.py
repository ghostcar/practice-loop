"""Points v2: gamification config, hierarchy, schedule, measurements, inventory.

Revision ID: 006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers
revision: str = "006"
down_revision: str | None = "005_add_training"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Existing table changes
    # entities: add parent_id, level, gamification_config
    op.add_column("entities", sa.Column("parent_id", postgresql.UUID(), nullable=True))
    op.add_column("entities", sa.Column("level", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("entities", sa.Column("gamification_config", sa.Text(), nullable=True))

    # activity_logs: add planned_value, actual_value, points_awarded
    op.add_column("activity_logs", sa.Column("planned_value", sa.String(255), nullable=True))
    op.add_column("activity_logs", sa.Column("actual_value", sa.String(255), nullable=True))
    op.add_column(
        "activity_logs",
        sa.Column("points_awarded", sa.Integer(), nullable=False, server_default="0"),
    )

    # user_progress: add points_balance
    op.add_column(
        "user_progress",
        sa.Column("points_balance", sa.Integer(), nullable=False, server_default="0"),
    )

    # 2. New tables
    op.create_table(
        "points_transactions",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("transaction_type", sa.String(30), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "entity_id",
            postgresql.UUID(),
            sa.ForeignKey("entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "activity_log_id",
            postgresql.UUID(),
            sa.ForeignKey("activity_logs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("meta", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "points_profiles",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("config", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "schedule_rules",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column(
            "entity_id",
            postgresql.UUID(),
            sa.ForeignKey("entities.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("day_of_week", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=True),
        sa.Column("task_type", sa.String(30), nullable=False, server_default="mandatory"),
        sa.Column("recurring", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "body_measurements",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("measured_date", sa.Date(), nullable=False),
        sa.Column("time_of_day", sa.String(10), nullable=False, server_default="morning"),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("chest", sa.Float(), nullable=True),
        sa.Column("under_chest", sa.Float(), nullable=True),
        sa.Column("waist", sa.Float(), nullable=True),
        sa.Column("hips", sa.Float(), nullable=True),
        sa.Column("thigh", sa.Float(), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_table(
        "inventory_items",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("user_id", postgresql.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("description", sa.String(2000), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("quantity_needed", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_shopping_list", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="need"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
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
    op.drop_table("inventory_items")
    op.drop_table("body_measurements")
    op.drop_table("schedule_rules")
    op.drop_table("points_profiles")
    op.drop_table("points_transactions")
    op.drop_column("user_progress", "points_balance")
    op.drop_column("activity_logs", "points_awarded")
    op.drop_column("activity_logs", "actual_value")
    op.drop_column("activity_logs", "planned_value")
    op.drop_column("entities", "gamification_config")
    op.drop_column("entities", "level")
    op.drop_column("entities", "parent_id")
