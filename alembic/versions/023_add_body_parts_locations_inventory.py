"""add body parts, locations, inventory categories, task links (update2.md)

Revision ID: 023
Revises: 022
Create Date: 2026-08-11

update2.md — normalised references and task-level links:

1. body_parts — hierarchical body zone reference (39 seed records).
2. task_body_targets — task → body zone links with role/side/intensity/snapshot.
3. task_locations — system + user-custom location reference (16 seed).
4. task_location_usages — task → location links with role/snapshot.
5. inventory_categories — normalised inventory category reference (15 seed).
6. task_inventory_usages — task → inventory item links with role/quantity/snapshot.
7. activity_body_part_requirements — activity-level body part constraints.
8. activity_location_requirements — activity-level location constraints.
9. activity_inventory_requirements — activity-level inventory constraints.
10. inventory_items — +inventory_category_id FK, +inventory_status column.

Non-destructive: all new tables/columns are additive. Downgrade drops them.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "023"
down_revision: str | None = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. body_parts (hierarchical body zone reference) -----------------------
    op.create_table(
        "body_parts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title_ru", sa.String(length=200), nullable=False),
        sa.Column("title_en", sa.String(length=200), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column(
            "body_system",
            sa.String(length=20),
            nullable=False,
            server_default="general",
        ),
        sa.Column("is_sensitive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["parent_id"], ["body_parts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_body_parts_slug", "body_parts", ["slug"], unique=True)
    op.create_index("ix_body_parts_parent_id", "body_parts", ["parent_id"])

    # 2. task_body_targets ----------------------------------------------------
    op.create_table(
        "task_body_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("body_part_id", sa.Uuid(), nullable=True),
        sa.Column("target_role", sa.String(length=30), nullable=False, server_default="primary_target"),
        sa.Column("side", sa.String(length=10), nullable=False, server_default="both"),
        sa.Column("planned_intensity", sa.Integer(), nullable=True),
        sa.Column("actual_intensity", sa.Integer(), nullable=True),
        sa.Column("planned_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("actual_duration_seconds", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("body_part_name_snapshot", sa.String(length=200), nullable=False),
        sa.Column("planned_notes", sa.Text(), nullable=True),
        sa.Column("actual_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["body_part_id"], ["body_parts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["activity_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_body_targets_task_id", "task_body_targets", ["task_id"])
    op.create_index("ix_task_body_targets_body_part_id", "task_body_targets", ["body_part_id"])

    # 3. task_locations (system + user-custom) --------------------------------
    op.create_table(
        "task_locations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title_ru", sa.String(length=200), nullable=False),
        sa.Column("title_en", sa.String(length=200), nullable=True),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("parent_id", sa.Uuid(), nullable=True),
        sa.Column(
            "location_type",
            sa.String(length=20),
            nullable=False,
            server_default="other",
        ),
        sa.Column(
            "privacy_level",
            sa.String(length=10),
            nullable=False,
            server_default="private",
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_custom", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["task_locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_locations_slug", "task_locations", ["slug"], unique=True)
    op.create_index("ix_task_locations_parent_id", "task_locations", ["parent_id"])
    op.create_index("ix_task_locations_owner_id", "task_locations", ["owner_id"])
    op.create_index(
        "ix_task_locations_type_privacy_active",
        "task_locations",
        ["location_type", "privacy_level", "is_active"],
    )

    # 4. task_location_usages -------------------------------------------------
    op.create_table(
        "task_location_usages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("location_role", sa.String(length=30), nullable=False, server_default="primary_location"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("location_name_snapshot", sa.String(length=200), nullable=False),
        sa.Column("planned_notes", sa.Text(), nullable=True),
        sa.Column("actual_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["location_id"], ["task_locations.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["activity_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_location_usages_task_id", "task_location_usages", ["task_id"])
    op.create_index("ix_task_location_usages_location_id", "task_location_usages", ["location_id"])

    # 5. inventory_categories -------------------------------------------------
    op.create_table(
        "inventory_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_inventory_categories_slug", "inventory_categories", ["slug"], unique=True)

    # 6. task_inventory_usages ------------------------------------------------
    op.create_table(
        "task_inventory_usages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_item_id", sa.Uuid(), nullable=True),
        sa.Column("usage_role", sa.String(length=30), nullable=False, server_default="primary_tool"),
        sa.Column("planned_quantity", sa.Numeric(10, 2), nullable=True),
        sa.Column("actual_quantity", sa.Numeric(10, 2), nullable=True),
        sa.Column("unit", sa.String(length=30), nullable=True),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("inventory_name_snapshot", sa.String(length=300), nullable=False),
        sa.Column("inventory_category_snapshot", sa.String(length=100), nullable=True),
        sa.Column("planned_notes", sa.Text(), nullable=True),
        sa.Column("actual_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["activity_logs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_inventory_usages_task_id", "task_inventory_usages", ["task_id"])
    op.create_index("ix_task_inventory_usages_item_id", "task_inventory_usages", ["inventory_item_id"])

    # 7. activity_body_part_requirements --------------------------------------
    op.create_table(
        "activity_body_part_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("body_part_id", sa.Uuid(), nullable=True),
        sa.Column("target_role", sa.String(length=30), nullable=False, server_default="primary_target"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("allow_side_selection", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["activity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["body_part_id"], ["body_parts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_abpr_activity_id", "activity_body_part_requirements", ["activity_id"])

    # 8. activity_location_requirements ---------------------------------------
    op.create_table(
        "activity_location_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("location_type", sa.String(length=20), nullable=True),
        sa.Column("location_id", sa.Uuid(), nullable=True),
        sa.Column("location_role", sa.String(length=30), nullable=False, server_default="primary_location"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["activity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["location_id"], ["task_locations.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_alr_activity_id", "activity_location_requirements", ["activity_id"])

    # 9. activity_inventory_requirements --------------------------------------
    op.create_table(
        "activity_inventory_requirements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("activity_id", sa.Uuid(), nullable=False),
        sa.Column("inventory_category_id", sa.Uuid(), nullable=True),
        sa.Column("inventory_item_id", sa.Uuid(), nullable=True),
        sa.Column("usage_role", sa.String(length=30), nullable=False, server_default="primary_tool"),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("min_count", sa.Integer(), nullable=True),
        sa.Column("max_count", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["activity_id"], ["entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["inventory_category_id"], ["inventory_categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["inventory_item_id"], ["inventory_items.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ainvr_activity_id", "activity_inventory_requirements", ["activity_id"])

    # 10. inventory_items — add FK + operational status -----------------------
    op.add_column(
        "inventory_items",
        sa.Column("inventory_category_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        "ix_inventory_items_category_id",
        "inventory_items",
        ["inventory_category_id"],
    )
    op.create_foreign_key(
        "fk_inventory_items_category_id",
        "inventory_items",
        "inventory_categories",
        ["inventory_category_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "inventory_items",
        sa.Column(
            "inventory_status",
            sa.String(length=20),
            nullable=False,
            server_default="available",
        ),
    )


def downgrade() -> None:
    # inventory_items column drops
    op.drop_column("inventory_items", "inventory_status")
    op.drop_constraint("fk_inventory_items_category_id", "inventory_items", type_="foreignkey")
    op.drop_index("ix_inventory_items_category_id", table_name="inventory_items")
    op.drop_column("inventory_items", "inventory_category_id")

    # Drop requirement tables
    op.drop_index("ix_ainvr_activity_id", table_name="activity_inventory_requirements")
    op.drop_table("activity_inventory_requirements")
    op.drop_index("ix_alr_activity_id", table_name="activity_location_requirements")
    op.drop_table("activity_location_requirements")
    op.drop_index("ix_abpr_activity_id", table_name="activity_body_part_requirements")
    op.drop_table("activity_body_part_requirements")

    # Drop task link tables
    op.drop_index("ix_task_inventory_usages_item_id", table_name="task_inventory_usages")
    op.drop_index("ix_task_inventory_usages_task_id", table_name="task_inventory_usages")
    op.drop_table("task_inventory_usages")
    op.drop_index("ix_task_location_usages_location_id", table_name="task_location_usages")
    op.drop_index("ix_task_location_usages_task_id", table_name="task_location_usages")
    op.drop_table("task_location_usages")
    op.drop_index("ix_task_body_targets_body_part_id", table_name="task_body_targets")
    op.drop_index("ix_task_body_targets_task_id", table_name="task_body_targets")
    op.drop_table("task_body_targets")

    # Drop reference tables
    op.drop_index("ix_inventory_categories_slug", table_name="inventory_categories")
    op.drop_table("inventory_categories")
    op.drop_index("ix_task_locations_type_privacy_active", table_name="task_locations")
    op.drop_index("ix_task_locations_owner_id", table_name="task_locations")
    op.drop_index("ix_task_locations_parent_id", table_name="task_locations")
    op.drop_index("ix_task_locations_slug", table_name="task_locations")
    op.drop_table("task_locations")
    op.drop_index("ix_body_parts_parent_id", table_name="body_parts")
    op.drop_index("ix_body_parts_slug", table_name="body_parts")
    op.drop_table("body_parts")
