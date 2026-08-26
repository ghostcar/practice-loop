"""Add source column to social_publications (auto vs manual origin).

Revision ID: 071_social_pub_source
Revises: 089_add_user_pin_hash
Create Date: 2026-08-26
"""

import sqlalchemy as sa

from alembic import op

revision: str = "071_social_pub_source"
down_revision: str | None = "089_add_user_pin_hash"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "social_publications",
        sa.Column("source", sa.String(20), server_default="manual", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("social_publications", "source")
