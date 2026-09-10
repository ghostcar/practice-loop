"""Add title and session_number to lock_sessions (ADR-203).

Revision ID: 105_lock_session_title_number
Revises: 104_lock_timer_freeze
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "105_lock_session_title_number"
down_revision: str | None = "104_lock_timer_freeze"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "lock_sessions",
        sa.Column("title", sa.String(200), nullable=True),
    )
    op.add_column(
        "lock_sessions",
        sa.Column("session_number", sa.Integer(), nullable=True),
    )

    # Backfill session_number for existing sessions per user by created_at
    conn = op.get_bind()
    conn.execute(
        sa.text("""
        WITH numbered AS (
            SELECT id, ROW_NUMBER() OVER (PARTITION BY owner_id ORDER BY created_at ASC) as num
            FROM lock_sessions
        )
        UPDATE lock_sessions
        SET session_number = numbered.num
        FROM numbered
        WHERE lock_sessions.id = numbered.id AND lock_sessions.session_number IS NULL;
    """)
    )


def downgrade() -> None:
    op.drop_column("lock_sessions", "session_number")
    op.drop_column("lock_sessions", "title")
