"""Add llm_mode to llm_provider_configs + fix column types.

Revision ID: 012
Revises: 011
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "012"
down_revision: str | None = "011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add llm_mode
    op.add_column("llm_provider_configs", sa.Column("llm_mode", sa.String(20), nullable=False, server_default="full"))

    # Fix subtasks: String → JSON
    op.alter_column("activity_logs", "subtasks", type_=postgresql.JSON, postgresql_using="subtasks::json")

    # Fix next_day_suggestion: Text → JSON
    op.alter_column(
        "training_days", "next_day_suggestion", type_=postgresql.JSON, postgresql_using="next_day_suggestion::json"
    )


def downgrade() -> None:
    op.alter_column("training_days", "next_day_suggestion", type_=sa.Text, postgresql_using="next_day_suggestion::text")
    op.alter_column("activity_logs", "subtasks", type_=sa.String, postgresql_using="subtasks::text")
    op.drop_column("llm_provider_configs", "llm_mode")
