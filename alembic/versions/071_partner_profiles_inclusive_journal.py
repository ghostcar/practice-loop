"""071_partner_profiles_inclusive_journal — Inclusive Partner Profiles and Sexual Journal Analytics.

Adds roles, identity_notes, hard_limits, soft_limits, safewords, aftercare_preferences to sj_partners.
Adds partner_id to sj_entries.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "071_partner_profiles_journal"
down_revision: str | None = "070_health_adapt_aftercare"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Upgrade sj_partners
    op.add_column("sj_partners", sa.Column("roles", JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("sj_partners", sa.Column("identity_notes", sa.Text(), nullable=True))
    op.add_column("sj_partners", sa.Column("hard_limits", JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("sj_partners", sa.Column("soft_limits", JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("sj_partners", sa.Column("safewords", JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("sj_partners", sa.Column("aftercare_preferences", sa.Text(), nullable=True))

    # Upgrade sj_entries
    op.add_column(
        "sj_entries",
        sa.Column(
            "partner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("sj_partners.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("sj_entries", "partner_id")

    op.drop_column("sj_partners", "aftercare_preferences")
    op.drop_column("sj_partners", "safewords")
    op.drop_column("sj_partners", "soft_limits")
    op.drop_column("sj_partners", "hard_limits")
    op.drop_column("sj_partners", "identity_notes")
    op.drop_column("sj_partners", "roles")
