"""Add training_days table + subtasks column to activity_logs."""

from collections.abc import Sequence

from sqlalchemy import Column, Date, DateTime, String, Text, func
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "005_add_training"
down_revision: str | None = "004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # TrainingDay table
    op.create_table(
        "training_days",
        Column("id", postgresql.UUID(), primary_key=True),
        Column(
            "user_id",
            postgresql.UUID(),
            nullable=False,
            index=True,
        ),
        Column("target_date", Date, nullable=False),
        Column("status", String(20), nullable=False, server_default="planned"),
        Column("plan_summary", Text, nullable=True),
        Column("analysis_summary", Text, nullable=True),
        Column("next_day_suggestion", Text, nullable=True),
        Column(
            "created_at",
            DateTime(timezone=True),
            server_default=func.now(),
            nullable=False,
        ),
        Column("completed_at", DateTime(timezone=True), nullable=True),
        Column("analyzed_at", DateTime(timezone=True), nullable=True),
    )

    # Add training_day_id FK to activity_logs
    op.add_column(
        "activity_logs",
        Column("training_day_id", postgresql.UUID(), nullable=True, index=True),
    )
    op.create_foreign_key(
        "fk_activity_logs_training_day",
        "activity_logs",
        "training_days",
        ["training_day_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Add subtasks JSON column to activity_logs
    op.add_column(
        "activity_logs",
        Column("subtasks", String, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("activity_logs", "subtasks")
    op.drop_column("activity_logs", "training_day_id")
    op.drop_table("training_days")
