"""064_inventory_nomenklatura_erp — 1C/ERP Nomenklatura Master Data catalog expansion for InventoryItems.

Adds group_type, manufacturer, model_name, material, size_color,
maintenance_interval_days, last_serviced_at, extra_properties columns.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "064_inventory_nomenklatura_erp"
down_revision: str | None = "9c8d7e6f5a4b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("inventory_items", sa.Column("group_type", sa.String(length=50), server_default="equipment", nullable=False))
    op.create_index(op.f("ix_inventory_items_group_type"), "inventory_items", ["group_type"], unique=False)
    op.add_column("inventory_items", sa.Column("manufacturer", sa.String(length=200), nullable=True))
    op.add_column("inventory_items", sa.Column("model_name", sa.String(length=200), nullable=True))
    op.add_column("inventory_items", sa.Column("material", sa.String(length=100), nullable=True))
    op.add_column("inventory_items", sa.Column("size_color", sa.String(length=100), nullable=True))
    op.add_column("inventory_items", sa.Column("maintenance_interval_days", sa.Integer(), nullable=True))
    op.add_column("inventory_items", sa.Column("last_serviced_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("inventory_items", sa.Column("extra_properties", JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    op.drop_column("inventory_items", "extra_properties")
    op.drop_column("inventory_items", "last_serviced_at")
    op.drop_column("inventory_items", "maintenance_interval_days")
    op.drop_column("inventory_items", "size_color")
    op.drop_column("inventory_items", "material")
    op.drop_column("inventory_items", "model_name")
    op.drop_column("inventory_items", "manufacturer")
    op.drop_index(op.f("ix_inventory_items_group_type"), table_name="inventory_items")
    op.drop_column("inventory_items", "group_type")
