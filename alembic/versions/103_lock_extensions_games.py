"""Lock session extensions state and game actions history (ADR-198).

Revision ID: 103_lock_extensions_games
Revises: 102_lock_discipline_pillory
Create Date: 2026-09-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "103_lock_extensions_games"
down_revision: str | None = "102_lock_discipline_pillory"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _json_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.JSONB(astext_type=sa.Text())
    return sa.JSON()


def _uuid_type():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        return postgresql.UUID(as_uuid=True)
    return sa.Uuid()


def upgrade() -> None:
    json_t = _json_type()
    uuid_t = _uuid_type()

    op.add_column(
        "lock_sessions",
        sa.Column("extensions_state", json_t, server_default="{}", nullable=False),
    )

    op.create_table(
        "lock_game_actions",
        sa.Column("id", uuid_t, primary_key=True, nullable=False),
        sa.Column(
            "session_id",
            uuid_t,
            sa.ForeignKey("lock_sessions.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            uuid_t,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("extension_type", sa.String(40), nullable=False, index=True),
        sa.Column("action_title", sa.String(120), nullable=False),
        sa.Column("result_code", sa.String(60), nullable=False),
        sa.Column("result_display", sa.String(255), nullable=False),
        sa.Column("time_modifier_seconds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("xp_modifier", sa.Integer(), server_default="0", nullable=False),
        sa.Column("payload", json_t, server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("lock_game_actions")
    op.drop_column("lock_sessions", "extensions_state")
