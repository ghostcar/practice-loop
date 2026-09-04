"""Add global LLM catalog and per-user capability selections.

Revision ID: 092
Revises: 091
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "092_llm_catalog"
down_revision: str | None = "091_add_totp_2fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_global_providers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("api_base_url", sa.String(500), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("supports_text", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("supports_vision", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "llm_global_models",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llm_global_providers.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("supports_text", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("supports_vision", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.UniqueConstraint("provider_id", "model_name", name="uq_llm_global_model_provider_name"),
    )
    op.create_index("ix_llm_global_models_provider_id", "llm_global_models", ["provider_id"])
    op.create_table(
        "llm_user_selections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("capability", sa.String(20), nullable=False),
        sa.Column(
            "user_config_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llm_provider_configs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "global_provider_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llm_global_providers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.UniqueConstraint("user_id", "capability", name="uq_llm_user_selection_capability"),
    )
    op.create_index("ix_llm_user_selections_user_id", "llm_user_selections", ["user_id"])


def downgrade() -> None:
    op.drop_table("llm_user_selections")
    op.drop_index("ix_llm_global_models_provider_id", table_name="llm_global_models")
    op.drop_table("llm_global_models")
    op.drop_table("llm_global_providers")
