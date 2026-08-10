"""Drag&drop ordering, inventory images, photo attachments, diets.

Adds:
- inventory_items.sort_order, inventory_items.image_path
- schedule_rules.sort_order, availability_windows.sort_order
- training_days.name (multiple plans per date)
- attachments table (photo reports for any section)
- diets + diet_items tables (combinable diet plans)

Revision ID: 018
Revises: 017_fix_jsonb_columns
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "018"
down_revision: str | None = "017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── Ordering / images on existing tables ──
    op.add_column("inventory_items", sa.Column("sort_order", sa.Integer, server_default="0", nullable=False))
    op.add_column("inventory_items", sa.Column("image_path", sa.String(500), nullable=True))
    op.add_column("schedule_rules", sa.Column("sort_order", sa.Integer, server_default="0", nullable=False))
    op.add_column("availability_windows", sa.Column("sort_order", sa.Integer, server_default="0", nullable=False))
    op.add_column("training_days", sa.Column("name", sa.String(200), nullable=True))

    # ── Attachments (photo reports) ──
    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("owner_type", sa.String(50), nullable=False, index=True),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("caption", sa.String(500), nullable=True),
        sa.Column("sort_order", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # ── Diets ──
    op.create_table(
        "diets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("goal", sa.String(500), nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "diet_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=sa.text("gen_random_uuid()")),
        sa.Column(
            "diet_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("diets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(300), nullable=False),
        sa.Column("quantity", sa.Float, nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("meal_time", sa.String(30), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("sort_order", sa.Integer, server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("diet_items")
    op.drop_table("diets")
    op.drop_table("attachments")
    op.drop_column("training_days", "name")
    op.drop_column("availability_windows", "sort_order")
    op.drop_column("schedule_rules", "sort_order")
    op.drop_column("inventory_items", "image_path")
    op.drop_column("inventory_items", "sort_order")
