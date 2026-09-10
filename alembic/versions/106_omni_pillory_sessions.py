"""Universal Omni-Pillory entries table (ADR-206).

Revision ID: 106_omni_pillory_sessions
Revises: 105_lock_session_title_number
Create Date: 2026-09-09
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "106_omni_pillory_sessions"
down_revision: str | None = "105_lock_session_title_number"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pillory_entries",
        sa.Column("id", sa.UUID(), nullable=False, primary_key=True),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("lock_session_id", sa.UUID(), sa.ForeignKey("lock_sessions.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("trigger", sa.String(50), nullable=False, server_default="manual"),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("reason", sa.String(1000), nullable=False),
        sa.Column("initial_duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("current_duration_minutes", sa.Integer(), nullable=False, server_default="60"),
        sa.Column("extensions_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("softens_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("freeze_timer_minutes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(30), nullable=False, server_default="active", index=True),
        sa.Column("requires_repentance_photo", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("repentance_photo_url", sa.String(500), nullable=True),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )


def downgrade() -> None:
    op.drop_table("pillory_entries")
