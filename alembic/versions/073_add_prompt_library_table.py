"""Prompt Library table creation (Step 49 / ADR-124).

Revision ID: 073_prompt_library_table
Revises: 072_quests_user_quests
Create Date: 2026-08-20 02:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "073_prompt_library_table"
down_revision: Union[str, None] = "072_quests_user_quests"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prompt_library",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("library_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("template_content", sa.Text(), nullable=False),
        sa.Column("is_customized", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key", name="uq_prompt_library_key"),
    )
    op.create_index(op.f("ix_prompt_library_key"), "prompt_library", ["key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_prompt_library_key"), table_name="prompt_library")
    op.drop_table("prompt_library")
