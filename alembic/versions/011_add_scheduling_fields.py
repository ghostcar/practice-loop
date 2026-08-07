"""Add scheduling fields to user_entity_opt_ins.

Revision ID: 011
Revises: 010
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "011"
down_revision: str | None = "010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("user_entity_opt_ins", sa.Column("next_due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_entity_opt_ins", sa.Column("retry_not_before_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("user_entity_opt_ins", "retry_not_before_at")
    op.drop_column("user_entity_opt_ins", "next_due_at")
