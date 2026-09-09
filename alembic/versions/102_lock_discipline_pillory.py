"""Lock session discipline policy, verification protocol, and pillory mode (ADR-197).

Revision ID: 102_lock_discipline_pillory
Revises: 101_user_identity_status
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "102_lock_discipline_pillory"
down_revision: str | None = "101_user_identity_status"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    json_t = _json_type()

    op.add_column(
        "lock_sessions",
        sa.Column("discipline_policy", json_t, server_default="{}", nullable=False),
    )
    op.add_column(
        "lock_sessions",
        sa.Column("verification_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "lock_sessions",
        sa.Column("verification_frequency_hours", sa.Integer(), server_default="24", nullable=False),
    )
    op.add_column(
        "lock_sessions",
        sa.Column("verification_mode", sa.String(30), server_default="ai_vision", nullable=False),
    )
    op.add_column(
        "lock_sessions",
        sa.Column("pillory_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column(
        "lock_sessions",
        sa.Column("pillory_auto_extend", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("lock_sessions", "pillory_auto_extend")
    op.drop_column("lock_sessions", "pillory_enabled")
    op.drop_column("lock_sessions", "verification_mode")
    op.drop_column("lock_sessions", "verification_frequency_hours")
    op.drop_column("lock_sessions", "verification_required")
    op.drop_column("lock_sessions", "discipline_policy")
