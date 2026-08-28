"""Add optional TOTP 2FA fields to users.

Revision ID: 091_add_totp_2fa
Revises: 090_add_missing_user_columns
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "091_add_totp_2fa"
down_revision: str | None = "090_add_missing_user_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("totp_secret_encrypted", sa.String(length=512), nullable=True))
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_secret_encrypted")
