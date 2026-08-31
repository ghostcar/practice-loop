"""Add portal_provider_id to llm_user_selections.

Env-backed portal providers (PORTAL_LLM_PROVIDERS_JSON) are identified by a
string id (``portal:<n>:<name>``) and have no DB row, so they cannot be stored
in the existing UUID global_provider_id FK. Add a nullable string column to
hold the portal provider id alongside the existing catalog/BYOK references.

Revision ID: 093_portal_selection
Revises: 092_llm_catalog
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "093_portal_selection"
down_revision: str | None = "092_llm_catalog"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "llm_user_selections",
        sa.Column("portal_provider_id", sa.String(length=200), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llm_user_selections", "portal_provider_id")
