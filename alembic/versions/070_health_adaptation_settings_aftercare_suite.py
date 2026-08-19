"""070_health_adaptation_settings_aftercare_suite — User health adaptation preferences and Aftercare suite expansion.

Adds health_adaptation_mode and health_adaptation_sensitivity to users.
Adds aftercare_trigger_drop and medication_ids to care_routines.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "070_health_adapt_aftercare"
down_revision: str | None = "069_train_discipline_equip"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Upgrade users table
    op.add_column("users", sa.Column("health_adaptation_mode", sa.String(length=30), server_default="auto_reduce", nullable=False))
    op.add_column("users", sa.Column("health_adaptation_sensitivity", sa.String(length=30), server_default="moderate", nullable=False))

    # Upgrade care_routines
    op.add_column("care_routines", sa.Column("aftercare_trigger_drop", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("care_routines", sa.Column("medication_ids", JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("care_routines", "medication_ids")
    op.drop_column("care_routines", "aftercare_trigger_drop")

    op.drop_column("users", "health_adaptation_sensitivity")
    op.drop_column("users", "health_adaptation_mode")
