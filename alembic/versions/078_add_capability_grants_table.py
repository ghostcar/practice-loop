"""Capability Grants creation for full D/s delegation (Step 69 / ADR-129).

Revision ID: 078_capability_grants
Revises: 077_ds_suite_tables
Create Date: 2026-08-20 02:54:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "078_capability_grants"
down_revision: Union[str, None] = "077_ds_suite_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "capability_grants",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("sub_user_id", sa.Uuid(), nullable=False),
        sa.Column("top_user_id", sa.Uuid(), nullable=True),
        sa.Column("invite_code", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="pending"),
        sa.Column("scope_chastity", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("scope_tasks", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("scope_training", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("scope_medication", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("scope_aftercare", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("scope_inventory", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("scope_health_view", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["sub_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["top_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_capability_grants_sub_user_id"), "capability_grants", ["sub_user_id"], unique=False)
    op.create_index(op.f("ix_capability_grants_top_user_id"), "capability_grants", ["top_user_id"], unique=False)
    op.create_index(op.f("ix_capability_grants_invite_code"), "capability_grants", ["invite_code"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_capability_grants_invite_code"), table_name="capability_grants")
    op.drop_index(op.f("ix_capability_grants_top_user_id"), table_name="capability_grants")
    op.drop_index(op.f("ix_capability_grants_sub_user_id"), table_name="capability_grants")
    op.drop_table("capability_grants")
