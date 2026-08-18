"""051_care_products_cross_module — доработка каталога средств + кросс-модуль (Шаг 17b, ADR-094).

Каталог средств/косметики (Шаг 16b) дорабатывается и связывается с другими
модулями личного контура:

- ``care_products``: + ``quantity`` (остаток), ``expiry_date`` (срок),
  ``catalog_item_id`` (FK activity_catalog, SET NULL — связь с универсальным
  каталогом, домен care);
- ``care_routine_products`` — many-to-many care_routines ↔ care_products
  (рекомендуемые средства для процедуры, оба CASCADE);
- ``lock_slot_rules.care_product_ids`` — средства для окна таймера (JSON,
  мягкие ссылки по ID, DATA_LIFECYCLE.md);
- ``entities.care_product_ids`` — средства для трекер-задачи (JSON, мягкие);
- ``sj_entries.care_product_ids`` — использованные средства в записи журнала
  (JSON, мягкие).

Relief-only (PD-013): без игровой интеграции.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d3e4f5a6b7c8"
down_revision: str | None = "c2d3e4f5a6b7"  # 050_add_personal_insights
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # care_products: остаток, срок, связь с универсальным каталогом
    op.add_column("care_products", sa.Column("quantity", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("care_products", sa.Column("expiry_date", sa.Date(), nullable=True))
    op.add_column("care_products", sa.Column("catalog_item_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_care_products_catalog_item",
        "care_products",
        "activity_catalog",
        ["catalog_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_care_products_catalog_item_id", "care_products", ["catalog_item_id"])

    # рекомендуемые средства для процедуры
    op.create_table(
        "care_routine_products",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("routine_id", sa.Uuid(), sa.ForeignKey("care_routines.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Uuid(), sa.ForeignKey("care_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_care_routine_products_routine_id", "care_routine_products", ["routine_id"])
    op.create_index("ix_care_routine_products_product_id", "care_routine_products", ["product_id"])

    # кросс-модульные мягкие ссылки (JSON, по ID без FK — DATA_LIFECYCLE.md)
    op.add_column("lock_slot_rules", sa.Column("care_product_ids", sa.JSON(), nullable=True))
    op.add_column("entities", sa.Column("care_product_ids", sa.JSON(), nullable=True))
    op.add_column("sj_entries", sa.Column("care_product_ids", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("sj_entries", "care_product_ids")
    op.drop_column("entities", "care_product_ids")
    op.drop_column("lock_slot_rules", "care_product_ids")

    op.drop_index("ix_care_routine_products_product_id", table_name="care_routine_products")
    op.drop_index("ix_care_routine_products_routine_id", table_name="care_routine_products")
    op.drop_table("care_routine_products")

    op.drop_index("ix_care_products_catalog_item_id", table_name="care_products")
    op.drop_constraint("fk_care_products_catalog_item", "care_products", type_="foreignkey")
    op.drop_column("care_products", "catalog_item_id")
    op.drop_column("care_products", "expiry_date")
    op.drop_column("care_products", "quantity")
