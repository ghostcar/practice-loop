"""036_add_prompt_templates — user prompt templates (Step 6, ADR-070).

Adds:
- prompt_templates (user_id, name, description, template_type text|task,
  system_prompt, params_schema JSONB, is_active, source_key, usage_count,
  last_used_at, created_at, updated_at)
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f6a7b8c9d0e"
down_revision: str | None = "e5f6a7b8c9d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("template_type", sa.String(20), nullable=False, server_default="text"),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("params_schema", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source_key", sa.String(50), nullable=True),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_prompt_templates_user_id", "prompt_templates", ["user_id"])


def downgrade() -> None:
    op.drop_index("ix_prompt_templates_user_id", table_name="prompt_templates")
    op.drop_table("prompt_templates")
