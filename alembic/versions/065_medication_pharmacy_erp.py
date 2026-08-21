"""065_medication_pharmacy_erp — Pharmacy Catalog & Generics ERP expansion for Medications.

Adds active_ingredient, analogues, form, strength, manufacturer,
prescription_required, storage_conditions columns.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "065_medication_pharmacy_erp"
down_revision: str | None = "064_inventory_nomenklatura_erp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("medications", sa.Column("analogues", JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("medications", sa.Column("manufacturer", sa.String(length=200), nullable=True))
    op.add_column("medications", sa.Column("prescription_required", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("medications", sa.Column("storage_conditions", sa.String(length=200), nullable=True))

    # active_ingredient, form, strength were already nullable in baseline model — ensure index on active_ingredient
    op.create_index(op.f("ix_medications_active_ingredient"), "medications", ["active_ingredient"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_medications_active_ingredient"), table_name="medications")
    op.drop_column("medications", "storage_conditions")
    op.drop_column("medications", "prescription_required")
    op.drop_column("medications", "manufacturer")
    op.drop_column("medications", "analogues")
