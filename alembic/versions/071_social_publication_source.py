"""Add source column to social_publications (auto vs manual origin).

Revision ID: 071_social_pub_source
Revises: 070_health_adapt_aftercare
Create Date: 2026-08-26
"""

import sqlalchemy as sa

from alembic import op

revision: str = "071_social_pub_source"
down_revision: str | None = "070_health_adapt_aftercare"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "social_publications",
        sa.Column("source", sa.String(20), server_default="manual", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("social_publications", "source")
