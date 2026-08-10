"""ActivityLog.completed_at, unique points ledger, diet_consumptions.

- activity_logs.completed_at (nullable) — when a task was actually completed
  (audit: import used a nonexistent field; now the column exists and is set by
  the atomic completion guard).
- Unique partial index on points_transactions(activity_log_id) — prevents a
  double-award ledger entry from concurrent complete requests.
- diet_consumptions table — actual (fact) side of diets for LLM evaluation.

Revision ID: 019
Revises: 018_add_dnd_uploads_diets
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "019"
down_revision: str | None = "018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("activity_logs", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))

    # Diet direction (why the diet exists) + LLM evaluation snapshot.
    op.add_column("diets", sa.Column("direction", sa.String(50), nullable=True))
    op.add_column("diets", sa.Column("last_evaluation", postgresql.JSON, nullable=True))
    op.add_column("diets", sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True))

    # Unique ledger: at most one points_transaction per activity log.
    op.create_index(
        "uq_points_txn_activity_log",
        "points_transactions",
        ["activity_log_id"],
        unique=True,
        postgresql_where=sa.text("activity_log_id IS NOT NULL"),
    )

    op.create_table(
        "diet_consumptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "diet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("diets.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column(
            "item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("diet_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("quantity", sa.Float, nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("meal_time", sa.String(30), nullable=True),
        sa.Column("consumed_date", sa.Date, nullable=False, index=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("diet_consumptions")
    op.drop_index("uq_points_txn_activity_log", table_name="points_transactions")
    op.drop_column("activity_logs", "completed_at")
    op.drop_column("diets", "direction")
    op.drop_column("diets", "last_evaluation")
    op.drop_column("diets", "evaluated_at")
