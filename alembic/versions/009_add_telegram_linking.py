"""Add Telegram linking fields to users table.

Revision ID: 009
Revises: 008
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "009"
down_revision: str | None = "008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
    op.create_index("ix_users_telegram_chat_id", "users", ["telegram_chat_id"], unique=True)
    op.add_column("users", sa.Column("telegram_link_code", sa.String(12), nullable=True))
    op.add_column("users", sa.Column("telegram_link_code_expires", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "telegram_link_code_expires")
    op.drop_column("users", "telegram_link_code")
    op.drop_index("ix_users_telegram_chat_id", "users")
    op.drop_column("users", "telegram_chat_id")
