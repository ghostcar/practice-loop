"""add risk_level to entities

Revision ID: 021
Revises: 020_add_diet_history_reviews
Create Date: 2026-08-11

REM §5.2: risk_level enum (not_assessed / low / elevated / high) drives the
LLM automation gate — not_assessed and high are never auto-selected, elevated
requires confirmation. Existing rows default to not_assessed (safe default:
nothing is automated until explicitly assessed).
"""

import sqlalchemy as sa

from alembic import op

revision: str = "021"
down_revision: str | None = "020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entities",
        sa.Column("risk_level", sa.String(length=20), nullable=False, server_default="not_assessed"),
    )
    op.create_index("ix_entities_risk_level", "entities", ["risk_level"])


def downgrade() -> None:
    op.drop_index("ix_entities_risk_level", table_name="entities")
    op.drop_column("entities", "risk_level")
