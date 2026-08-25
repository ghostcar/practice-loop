"""Add pin_hash column to users table for 2FA PIN (ADR-152).

Revision ID: 089_add_user_pin_hash
Revises: 088_add_dynamic_engine
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "089_add_user_pin_hash"
down_revision: str | None = "088_add_dynamic_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("pin_hash", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("users", "pin_hash")
