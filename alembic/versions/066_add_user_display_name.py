"""066 — add users.display_name (abstract/anonymous display name).

ADR-110: the UI must not show the user's email in the shell header. A user-chosen
display name (defaulting to a neutral fallback) is shown instead.

Revision ID: 066_add_user_display_name
Revises: 065_medication_pharmacy_erp
Create Date: 2026-08-19
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "066_add_user_display_name"
down_revision: str | None = "065_medication_pharmacy_erp"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("display_name", sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "display_name")
