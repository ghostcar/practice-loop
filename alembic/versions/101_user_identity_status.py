"""User identity, role taxonomy, and status tags (ADR-196).

Revision ID: 101_user_identity_and_status_tags
Revises: 100_wear_open_ended_events
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "101_user_identity_status"
down_revision: str | None = "100_wear_open_ended_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def upgrade() -> None:
    json_t = _json_type()

    op.add_column("users", sa.Column("portal_name", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("ai_designation", sa.String(100), nullable=True))
    op.add_column("users", sa.Column("primary_role", sa.String(50), server_default="submissive", nullable=False))
    op.add_column("users", sa.Column("portal_roles", json_t, server_default="[]", nullable=False))
    op.add_column(
        "users",
        sa.Column(
            "status_tags",
            json_t,
            server_default='{"permanent": [], "standing": [], "dynamic": []}',
            nullable=False,
        ),
    )
    op.add_column(
        "users",
        sa.Column("ai_identity_locked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("users", sa.Column("physiology", sa.String(30), server_default="male", nullable=False))
    op.add_column("users", sa.Column("ai_status_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "ai_status_reason")
    op.drop_column("users", "physiology")
    op.drop_column("users", "ai_identity_locked")
    op.drop_column("users", "status_tags")
    op.drop_column("users", "portal_roles")
    op.drop_column("users", "primary_role")
    op.drop_column("users", "ai_designation")
    op.drop_column("users", "portal_name")
