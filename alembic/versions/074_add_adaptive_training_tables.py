"""Adaptive Training Program tables creation (Step 54 / ADR-125).

Revision ID: 074_adaptive_training_tables
Revises: 073_prompt_library_table
Create Date: 2026-08-20 02:14:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "074_adaptive_training_tables"
down_revision: Union[str, None] = "073_prompt_library_table"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "adaptive_programs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("focus_domain", sa.String(length=50), nullable=False),
        sa.Column("total_days", sa.Integer(), nullable=False, server_default="14"),
        sa.Column("current_day", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("difficulty_level", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
        sa.Column("adaptive_rules", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_adaptive_programs_user_id"), "adaptive_programs", ["user_id"], unique=False)

    op.create_table(
        "adaptive_program_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("program_id", sa.Uuid(), nullable=False),
        sa.Column("day_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("target_parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("actual_feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="{}"),
        sa.Column("ai_adjustment_reason", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.ForeignKeyConstraint(["program_id"], ["adaptive_programs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_adaptive_program_steps_program_id"), "adaptive_program_steps", ["program_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_adaptive_program_steps_program_id"), table_name="adaptive_program_steps")
    op.drop_table("adaptive_program_steps")
    op.drop_index(op.f("ix_adaptive_programs_user_id"), table_name="adaptive_programs")
    op.drop_table("adaptive_programs")
