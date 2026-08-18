"""059_add_user_disabled_at — account administration lock state."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "b0c1d2e3f4a5"
down_revision: str | None = "a9b0c1d2e3f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_users_disabled_at", "users", ["disabled_at"])


def downgrade() -> None:
    op.drop_index("ix_users_disabled_at", table_name="users")
    op.drop_column("users", "disabled_at")
