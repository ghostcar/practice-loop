"""043_med_migration_source — one-time inventory→medicine migration (Шаг 12).

Adds:
- ``medications.source_inventory_id`` — nullable FK to inventory_items, so a
  medication created by the one-time migration keeps its provenance (idempotent
  re-runs skip already-migrated items).
- ``inventory_items.migrated_to_medication`` — bool marker so migrated items can
  be filtered out of the active inventory list and the migration is honest.

No data backfill — the migration runs from the UI/endpoint.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"  # 042_add_med_adherence_achievements
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "medications",
        sa.Column(
            "source_inventory_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("inventory_items.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
    )
    op.add_column(
        "inventory_items",
        sa.Column(
            "migrated_to_medication",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("inventory_items", "migrated_to_medication")
    op.drop_column("medications", "source_inventory_id")
