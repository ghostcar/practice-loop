"""Add training_days.user_id FK, opt-in unique constraint, active session constraint.

Revision ID: 013
Revises: 012
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "013"
down_revision: str | None = "012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Add FK to training_days.user_id
    op.create_foreign_key(
        "fk_training_days_user_id",
        "training_days",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    # 2. Add unique constraint on user_entity_opt_ins (user_id, entity_id)
    op.create_unique_constraint("uq_user_entity_opt_in", "user_entity_opt_ins", ["user_id", "entity_id"])

    # 3. Add partial unique index for one active session per user
    op.create_index(
        "ix_activity_sessions_one_active",
        "activity_sessions",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('created', 'active')"),
    )


def downgrade() -> None:
    op.drop_index("ix_activity_sessions_one_active", table_name="activity_sessions")
    op.drop_constraint("uq_user_entity_opt_in", "user_entity_opt_ins", type_="unique")
    op.drop_constraint("fk_training_days_user_id", "training_days", type_="foreignkey")
