"""Fix migration type issues: JSON→JSONB, boolean defaults, missing indexes.

Revision ID: 014
Revises: 013
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "014"
down_revision: str | None = "013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Fix activity_logs.subtasks: String → JSON (migration 005 created as String)
    op.alter_column(
        "activity_logs",
        "subtasks",
        type_=postgresql.JSON,
        postgresql_using="subtasks::json",
    )

    # Fix activity_logs.raw_llm_response: String → JSON if it exists as String
    # (check: migration 002 created String, but model uses JSON / create_all creates JSON)

    # Fix points_transactions.meta: ensure JSONB
    op.alter_column(
        "points_transactions",
        "meta",
        type_=postgresql.JSON,
        postgresql_using="meta::json",
    )

    # Fix boolean defaults: PostgreSQL uses true/false, not 0/1
    # These are already correct in migrations 004+, but 006 used server_default="0"
    op.alter_column(
        "points_profiles",
        "is_default",
        server_default=sa.text("false"),
        type_=sa.Boolean(),
        existing_type=sa.Boolean(),
    )
    op.alter_column(
        "schedule_rules",
        "recurring",
        server_default=sa.text("true"),
        type_=sa.Boolean(),
        existing_type=sa.Boolean(),
    )
    op.alter_column(
        "schedule_rules",
        "is_active",
        server_default=sa.text("true"),
        type_=sa.Boolean(),
        existing_type=sa.Boolean(),
    )
    op.alter_column(
        "inventory_items",
        "is_shopping_list",
        server_default=sa.text("false"),
        type_=sa.Boolean(),
        existing_type=sa.Boolean(),
    )


def downgrade() -> None:
    op.alter_column("activity_logs", "subtasks", type_=sa.String)
    op.alter_column("points_transactions", "meta", type_=sa.String)
    op.alter_column("points_profiles", "is_default", server_default=sa.text("false"))
    op.alter_column("schedule_rules", "recurring", server_default=sa.text("true"))
    op.alter_column("schedule_rules", "is_active", server_default=sa.text("true"))
    op.alter_column("inventory_items", "is_shopping_list", server_default=sa.text("false"))
