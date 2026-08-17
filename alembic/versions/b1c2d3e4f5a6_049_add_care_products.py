"""049_add_care_products — каталог средств/косметики для ухода (Шаг 16b, ADR-092).

Каталог средств/косметики Personal Care (PRODUCT_OVERVIEW §8) с привязкой
к инвентарю:

- ``care_products`` — позиция средства: name, category (cleanser/toner/serum/
  moisturizer/mask/exfoliant/sun/body/hair/other), brand, notes,
  inventory_item_id (FK inventory_items, SET NULL — остаток/список покупок
  ведётся в инвентаре);
- ``care_entry_products`` — many-to-many: какие средства использованы в записи
  ухода (care_entries ↔ care_products, оба CASCADE).

Relief-only (PD-013): справочник без игровой интеграции.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b1c2d3e4f5a6"
down_revision: str | None = "a0b1c2d3e4f5"  # 048_add_activity_catalog
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "care_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("category", sa.String(30), nullable=False, server_default="other"),
        sa.Column("brand", sa.String(120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "inventory_item_id",
            sa.Uuid(),
            sa.ForeignKey("inventory_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_care_products_user_id", "care_products", ["user_id"])
    op.create_index("ix_care_products_inventory_item_id", "care_products", ["inventory_item_id"])

    op.create_table(
        "care_entry_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "entry_id", sa.Uuid(), sa.ForeignKey("care_entries.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "product_id", sa.Uuid(), sa.ForeignKey("care_products.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_care_entry_products_entry_id", "care_entry_products", ["entry_id"])
    op.create_index("ix_care_entry_products_product_id", "care_entry_products", ["product_id"])


def downgrade() -> None:
    op.drop_index("ix_care_entry_products_product_id", table_name="care_entry_products")
    op.drop_index("ix_care_entry_products_entry_id", table_name="care_entry_products")
    op.drop_table("care_entry_products")
    op.drop_index("ix_care_products_inventory_item_id", table_name="care_products")
    op.drop_index("ix_care_products_user_id", table_name="care_products")
    op.drop_table("care_products")
