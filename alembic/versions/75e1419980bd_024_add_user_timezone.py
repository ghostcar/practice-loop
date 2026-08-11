"""024_add_user_timezone — User.timezone for LockTimer composition (ADR-043, PL-CMP-005).

Revision ID: 75e1419980bd
Revises: 023
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "75e1419980bd"
down_revision: str | None = "023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "timezone",
            sa.String(64),
            nullable=False,
            server_default="UTC",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "timezone_confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "timezone_confirmed_at")
    op.drop_column("users", "timezone")
