"""069_training_discipline_equipment — Training equipment linking and health-adaptive discipline expansion.

Adds equipment_item_ids, discipline_notes, and adapted_for_health to training_days and training_log_entries.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "069_training_discipline_equipment"
down_revision: str | None = "068_chastity_keyholder_suite"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Upgrade training_days
    op.add_column("training_days", sa.Column("equipment_item_ids", JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("training_days", sa.Column("discipline_notes", sa.Text(), nullable=True))
    op.add_column("training_days", sa.Column("adapted_for_health", sa.Boolean(), server_default="false", nullable=False))

    # Upgrade training_log_entries
    op.add_column("training_log_entries", sa.Column("equipment_item_ids", JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("training_log_entries", "equipment_item_ids")

    op.drop_column("training_days", "adapted_for_health")
    op.drop_column("training_days", "discipline_notes")
    op.drop_column("training_days", "equipment_item_ids")
