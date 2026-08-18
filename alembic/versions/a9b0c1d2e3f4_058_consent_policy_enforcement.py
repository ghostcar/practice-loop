"""058_consent_policy_enforcement — durable versioned consent constraints."""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: str | None = "f8a9b0c1d2e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "consent_records",
        sa.Column("terms_version", sa.String(length=20), server_default="1", nullable=False),
    )
    op.create_check_constraint("ck_consent_version_positive", "consent_records", "version > 0")
    op.create_unique_constraint(
        "uq_consent_user_type_version",
        "consent_records",
        ["user_id", "consent_type", "version"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_consent_user_type_version", "consent_records", type_="unique")
    op.drop_constraint("ck_consent_version_positive", "consent_records", type_="check")
    op.drop_column("consent_records", "terms_version")
