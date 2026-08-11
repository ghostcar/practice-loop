"""026_add_lock_llm_proposals

Revision ID: c4a67950ab23
Revises: 18554078c9da
Create Date: 2026-08-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a67950ab23"
down_revision: str | None = "18554078c9da"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "lock_llm_proposals",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("lock_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("user_brief", sa.Text, nullable=True),
        sa.Column(
            "items",
            sa.JSON,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "llm_provider_config_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("llm_provider_configs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("llm_model", sa.String(100), nullable=True),
        sa.Column("llm_prompt_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("llm_completion_tokens", sa.Integer, nullable=False, server_default="0"),
        sa.Column("llm_cost", sa.Numeric(14, 6), nullable=False, server_default="0"),
        sa.Column("raw_response_encrypted", sa.Text, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_table("lock_llm_proposals")
